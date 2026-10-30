/**
 * NL dashboard webview controller: chat, model choice, persistent missions,
 * mission progress/agents/verification/diff, approvals and engine settings.
 *
 * The controller contains presentation state only. Missions, persistence,
 * staging, verification and promotion always run inside the Python engine; this
 * file calls the existing MCP tools and never writes engine state directly.
 */
import * as path from 'path';
import * as vscode from 'vscode';
import {
    AttachmentInput,
    AttachmentView,
    AutonomySettings,
    CandidateDiff,
    ChatHistoryResult,
    ChatQueueItem,
    ChatRoute,
    ChatSession,
    CustomAgent,
    EngineConnection,
    EngineError,
    EngineSettings,
    GenerationParametersResult,
    HistoryMessage,
    MissionDetail,
    MissionRow,
    ModelCapabilityProbe,
    ProjectContext,
    ResearchFetchResult,
    StorageScanResult
} from './backend';
import { buildChatHtml } from './webview';

const MAX_SELECTION_CHARS = 8000;
const MAX_RECORDED_MESSAGES = 200;
const POLL_INTERVAL_MS = 2000;
const TERMINAL_STATUSES = new Set(['completed', 'failed', 'blocked', 'interrupted']);

export interface ModelOption {
    value: string;
    label: string;
    group: string;
    loaded: boolean;
    provider: string;
    model: string;
    automatic?: boolean;
}

export interface EditorContext {
    path?: string;
    relativePath?: string;
    languageId?: string;
    hasSelection: boolean;
    selectionLines: number;
    dirty: boolean;
}

export interface MissionSelection {
    detail: MissionDetail;
    diff?: CandidateDiff;
}

export interface DashboardState {
    connected: boolean;
    connectionState: string;
    project?: { id: number; root: string; name?: string };
    engine?: { name?: string; version?: string };
    executionEnabled: boolean;
    settings?: EngineSettings;
    missions: MissionRow[];
    selected?: MissionSelection;
    activeMissionId?: number;
    busyChat: boolean;
    busyMission: boolean;
    busyPhase: string;
    chatModel: string;
    missionModels: { developerModel: string; reviewerModel: string };
    modelOptions: ModelOption[];
    providers: Array<{ id: string; label: string; kind: string; enabled: boolean }>;
    defaultChatSpec: string;
    chatRole: string;
    attachments: AttachmentView[];
    editor?: EditorContext;
    lastRoute?: ChatRoute;
    chatQueue?: ChatQueueItem[];
    queueCount?: number;
    chatSessions?: ChatSession[];
    currentSessionId?: string;
    showArchivedSessions?: boolean;
    missionShowArchived?: boolean;
    missionStatusFilter?: string;
    missionQuery?: string;
    generationParams?: GenerationParametersResult;
    autonomy?: AutonomySettings;
    storage?: StorageScanResult;
    capabilityProbe?: ModelCapabilityProbe;
    mcpConfig?: Record<string, unknown>;
    research?: ResearchFetchResult;
    researchProfile: string;
    historyCount: number;
    historyLoaded: boolean;
    error?: string;
}

export interface StartMissionInput {
    goal: string;
    developerModel: string;
    reviewerModel: string;
    resumeMissionId?: number;
}

export interface ChatDebugState {
    resolved: boolean;
    busy: boolean;
    posted: Array<Record<string, unknown>>;
}

export class ChatProvider implements vscode.WebviewViewProvider {
    public static readonly viewType = 'nlCodingAgent.chat';

    private view: vscode.WebviewView | undefined;
    private disposed = false;
    private readyAnnounced = false;
    private lastHtml: string | undefined;
    private readonly posted: Array<Record<string, unknown>> = [];

    private projectContext: ProjectContext | undefined;
    private settings: EngineSettings | undefined;
    private missions: MissionRow[] = [];
    private selected: MissionSelection | undefined;
    private activeMissionId: number | undefined;
    private busyChat = false;
    private busyMission = false;
    private busyPhase = 'idle';
    private chatModel = '';
    private missionModels = { developerModel: '', reviewerModel: '' };
    private attachments: AttachmentView[] = [];
    private history: HistoryMessage[] = [];
    private historyCount = 0;
    private historyLoaded = false;
    private chatQueue: ChatQueueItem[] = [];
    private chatSessions: ChatSession[] = [];
    private currentSessionId: string | undefined;
    private showArchivedSessions = false;
    private missionShowArchived = false;
    private missionStatusFilter = '';
    private missionQuery = '';
    private generationParams: GenerationParametersResult | undefined;
    private autonomy: AutonomySettings | undefined;
    private storage: StorageScanResult | undefined;
    private capabilityProbe: ModelCapabilityProbe | undefined;
    private mcpConfig: Record<string, unknown> | undefined;
    private editorContext: EditorContext | undefined;
    private lastEditor: vscode.TextEditor | undefined;
    private lastRoute: ChatRoute | undefined;
    private research: ResearchFetchResult | undefined;
    private monitorTimer: NodeJS.Timeout | undefined;
    private errorMessage: string | undefined;
    private editorDisposables: vscode.Disposable[] = [];
    private editorTimer: NodeJS.Timeout | undefined;
    private readonly workspaceState: vscode.Memento | undefined;

    constructor(
        private readonly extensionUri: vscode.Uri,
        private readonly connection: EngineConnection,
        private readonly output: vscode.OutputChannel,
        private readonly requestTimeoutMs: number,
        context?: vscode.ExtensionContext
    ) {
        this.workspaceState = context?.workspaceState;
    }

    get debugState(): ChatDebugState {
        return { resolved: Boolean(this.view), busy: this.busyChat || this.busyMission, posted: this.posted.slice() };
    }

    get isResolved(): boolean {
        return Boolean(this.view);
    }

    get renderedHtml(): string | undefined {
        return this.lastHtml;
    }

    get activeMission(): number | undefined {
        return this.activeMissionId;
    }

    resolveWebviewView(webviewView: vscode.WebviewView): void {
        this.view = webviewView;
        this.readyAnnounced = false;
        const mediaRoot = vscode.Uri.joinPath(this.extensionUri, 'media');
        webviewView.webview.options = { enableScripts: true, localResourceRoots: [mediaRoot] };
        this.lastHtml = buildChatHtml({
            scriptUri: webviewView.webview.asWebviewUri(vscode.Uri.joinPath(mediaRoot, 'main.js')).toString(),
            styleUri: webviewView.webview.asWebviewUri(vscode.Uri.joinPath(mediaRoot, 'style.css')).toString(),
            cspSource: webviewView.webview.cspSource
        });
        webviewView.webview.html = this.lastHtml;
        webviewView.webview.onDidReceiveMessage((message: unknown) => {
            void this.onMessage(message);
        });
        webviewView.onDidDispose(() => {
            if (this.view === webviewView) {
                this.view = undefined;
            }
        });
    }

    /** Ask the webview to switch section (used by commands). */
    postNavigation(tab: 'chat' | 'missions' | 'agents' | 'engine'): void {
        this.post({ type: 'navigate', tab });
    }

    /** Connect, load engine state/missions/history and post the first snapshot. */
    async initialize(): Promise<void> {
        if (!this.view || this.disposed) {
            return;
        }
        this.post({ type: 'status', state: 'connecting', label: 'Connecting to NL Coding Engine…' });
        try {
            const savedModel = this.workspaceState?.get<string>('nlCodingAgent.chatModel');
            if (typeof savedModel === 'string') {
                this.chatModel = savedModel;
            }
            this.setupEditorTracking();
            await this.refreshAll(true);
            await this.loadSessions();
            await this.loadHistory();
            await this.refreshQueue(false);
            if (!this.readyAnnounced) {
                this.readyAnnounced = true;
                this.postChat('system', [
                    'Connected to the existing NL Coding Engine.',
                    `Project: #${this.projectContext?.project.id}${this.projectContext?.project.name ? ' ' + this.projectContext.project.name : ''}`,
                    `Workspace: ${this.projectContext?.project.root}`,
                    `Execution: ${this.connection.executionAllowed ? 'missions enabled' : 'read-only'}`,
                    `Research profile: ${this.connection.researchProfile}`
                ].join('\n'));
            }
            this.post({ type: 'status', state: 'ready', label: this.statusLabel() });
            this.postState();
        } catch (error) {
            this.reportError(error, 'connect');
        }
    }

    /** Backwards-compatible entry point used by commands/tests. */
    async announceStatus(): Promise<void> {
        this.readyAnnounced = false;
        await this.initialize();
    }

    /** One chat turn; the webview appends the user message locally until history reload. */
    async handleUserMessage(text: string, attachment?: AttachmentInput | null,
                            queuedAttachmentIds: number[] = []): Promise<void> {
        const message = String(text || '').trim();
        if (!message) {
            return;
        }
        const pendingAttachments = this.attachments.slice();
        const attachmentIds = queuedAttachmentIds.length
            ? queuedAttachmentIds.slice()
            : pendingAttachments.map((item) => item.id);
        if (this.busyChat || this.busyMission) {
            if (/^\/steer\s+/i.test(message)) {
                await this.steerChat(message.replace(/^\/steer\s+/i, ''));
                return;
            }
            if (this.busyMission && this.activeMissionId) {
                await this.connection.missionSteer(this.activeMissionId, message);
                this.postChat('system', 'Message sent as steering to mission #' + this.activeMissionId +
                    '; it applies at the next safe agent stage.');
                return;
            }
            const queued = await this.connection.chatEnqueue(message, attachmentIds, 'queue');
            this.attachments = [];
            this.postChat('system', 'Queued while the current reply runs' +
                (typeof queued.count === 'number' ? ' (' + queued.count + ')' : '') +
                '. It will be sent after this turn; use /steer to redirect the running turn.');
            await this.refreshQueue(false);
            return;
        }
        this.busyChat = true;
        this.busyPhase = 'thinking';
        this.postState();
        try {
            await this.connection.connect();
            const context = await this.requireBoundProject();
            const legacyAttachments = !attachmentIds.length && attachment && attachment.extracted_text &&
                attachment.extracted_text.trim()
                ? [attachment]
                : [];
            const result = await this.connection.converse(
                context.project.id, message, legacyAttachments, this.requestTimeoutMs,
                this.chatModel || undefined, attachmentIds
            );
            if (result.route) {
                this.lastRoute = result.route;
            }
            this.attachments = [];
            this.postChat('assistant', result.reply || '');
            if (Array.isArray(result.tool_trace) && result.tool_trace.length) {
                const names = result.tool_trace
                    .filter((item) => item.status === 'completed')
                    .map((item) => String(item.tool || ''));
                if (names.length) {
                    this.postChat('system', 'Tools used: ' + Array.from(new Set(names)).join(', '));
                }
            }
            await this.loadHistory();
            await this.refreshQueue(false);
            this.output.appendLine(`[chat] project #${context.project.id}: ${message.length} chars in, ` +
                `${(result.reply || '').length} chars out, route ${result.route?.provider_id || '?'}/${result.route?.model || '?'}`);
        } catch (error) {
            this.reportError(error, 'chat');
        } finally {
            this.busyChat = false;
            this.busyPhase = this.busyMission ? 'mission' : 'idle';
            this.postState();
            // A queued turn is dispatched only after this one is genuinely idle.
            void this.refreshQueue(true);
        }
    }

    /** Ingest explicit workspace files through the engine attachment pipeline. */
    async attachPaths(paths: string[]): Promise<void> {
        if (!paths.length) {
            return;
        }
        const root = this.connection.projectRoot;
        const accepted: string[] = [];
        for (const value of paths) {
            const resolved = path.resolve(String(value));
            if (!root || !this.isInsideRoot(resolved, root)) {
                this.postChat('error', `Attachment rejected: "${value}" is outside the opened project.`);
                continue;
            }
            accepted.push(resolved);
        }
        if (!accepted.length) {
            return;
        }
        this.busyPhase = 'attaching';
        this.postState();
        try {
            const result = await this.connection.attachmentIngest({ paths: accepted });
            for (const item of result.attachments || []) {
                this.attachments.push(item);
            }
            if (result.errors && result.errors.length) {
                for (const error of result.errors) {
                    this.postChat('error', `Attachment ${error.name || ''}: ${error.error || 'rejected'}`);
                }
            }
            if (!result.ok) {
                this.postChat('error', 'No attachment could be extracted. Check the supported type/size.');
            }
            this.postState();
        } catch (error) {
            this.reportError(error, 'attachments');
        } finally {
            this.busyPhase = 'idle';
            this.postState();
        }
    }

    /** Ingest text (editor selection, fetched page) as a project-scoped attachment. */
    async attachText(text: string, name: string): Promise<AttachmentView | undefined> {
        const body = String(text || '');
        if (!body.trim()) {
            this.postChat('error', 'The selected text is empty.');
            return undefined;
        }
        if (body.length > 200_000) {
            this.postChat('error', 'Text attachment is too large (limit 200,000 characters).');
            return undefined;
        }
        this.busyPhase = 'attaching';
        this.postState();
        try {
            const result = await this.connection.attachmentIngest({ text: body, name });
            const item = (result.attachments || [])[0];
            if (item) {
                this.attachments.push(item);
                this.postState();
                return item;
            }
            this.postChat('error', 'The engine could not ingest the text attachment.');
        } catch (error) {
            this.reportError(error, 'attachments');
        } finally {
            this.busyPhase = 'idle';
            this.postState();
        }
        return undefined;
    }

    /** Attach the active editor file or its current selection (VS Code document API only). */
    async attachActiveEditor(kind: 'file' | 'selection'): Promise<void> {
        const editor = this.currentEditor();
        if (!editor) {
            this.postChat('error', 'No active editor. Open a file first.');
            return;
        }
        const document = editor.document;
        const root = this.connection.projectRoot || '';
        if (root && !this.isInsideRoot(document.uri.fsPath, root)) {
            this.postChat('error', 'The active file is outside the opened project and cannot be attached.');
            return;
        }
        const relative = vscode.workspace.asRelativePath(document.uri, false);
        if (kind === 'selection') {
            const selection = editor.selection;
            if (selection.isEmpty) {
                this.postChat('error', 'There is no selected text in the active editor.');
                return;
            }
            const lines = `${selection.start.line + 1}-${selection.end.line + 1}`;
            await this.attachText(document.getText(selection), `${relative} (selection ${lines})`);
            return;
        }
        await this.attachText(document.getText(), relative || document.uri.fsPath);
    }

    /** Pick one or more workspace files; the engine re-validates containment/types. */
    async attachWorkspaceFiles(): Promise<void> {
        const root = this.connection.projectRoot;
        if (!root) {
            this.postChat('error', 'Open a project folder before attaching files.');
            return;
        }
        const picked = await vscode.window.showOpenDialog({
            defaultUri: vscode.Uri.file(root),
            canSelectFiles: true,
            canSelectFolders: false,
            canSelectMany: true,
            openLabel: 'Attach to NL Coder',
            filters: {
                'Supported text/data': ['txt', 'md', 'markdown', 'json', 'yaml', 'yml', 'toml',
                    'py', 'ts', 'tsx', 'js', 'jsx', 'css', 'html', 'xml', 'csv', 'log',
                    'sql', 'sh', 'ps1', 'bat', 'pdf', 'xlsx'],
                'All files': ['*']
            }
        });
        if (!picked || !picked.length) {
            return;
        }
        await this.attachPaths(picked.filter((uri) => uri.scheme === 'file').map((uri) => uri.fsPath));
    }

    /** Handle drag & drop URIs from the Explorer into the webview. */
    async dropUris(uris: string[]): Promise<void> {
        const paths: string[] = [];
        for (const raw of uris) {
            try {
                const uri = vscode.Uri.parse(String(raw).trim());
                if (uri.scheme === 'file') {
                    paths.push(uri.fsPath);
                }
            } catch {
                // ignore malformed URI lines
            }
        }
        await this.attachPaths(paths);
    }

    removeAttachment(attachmentId: number): void {
        this.attachments = this.attachments.filter((item) => item.id !== attachmentId);
        this.postState();
    }

    /** Load the engine's persisted thread; never an extension-side archive. */
    async loadHistory(limit = 200): Promise<void> {
        try {
            if (!this.currentSessionId) {
                await this.loadSessions();
            }
            const history: ChatHistoryResult = await this.connection.chatHistory(
                limit, undefined, this.currentSessionId);
            this.history = history.messages || [];
            this.historyCount = Number(history.count || 0);
            this.historyLoaded = true;
            this.post({ type: 'history', payload: history });
        } catch (error) {
            this.historyLoaded = false;
            this.output.appendLine('[history] ' + this.errorText(error));
            this.postChat('error', 'Conversation history could not be loaded: ' + this.errorText(error));
        }
    }

    async loadSessions(selectId?: string): Promise<void> {
        try {
            const result = await this.connection.chatSessions(this.showArchivedSessions);
            this.chatSessions = result.sessions || [];
            const saved = this.workspaceState?.get<string>('nlCodingAgent.chatSession');
            const preferred = selectId || this.currentSessionId ||
                (typeof saved === 'string' ? saved : undefined);
            const selected = this.chatSessions.find((item) => item.id === preferred) ||
                this.chatSessions.find((item) => !item.archived_at) ||
                this.chatSessions[0];
            this.currentSessionId = selected?.id;
            await this.workspaceState?.update('nlCodingAgent.chatSession', this.currentSessionId || '');
            this.postState();
        } catch (error) {
            this.output.appendLine('[sessions] ' + this.errorText(error));
        }
    }

    async switchSession(sessionId: string): Promise<void> {
        this.currentSessionId = String(sessionId || '');
        await this.workspaceState?.update('nlCodingAgent.chatSession', this.currentSessionId);
        await this.loadHistory();
        this.postState();
    }

    async newChatSession(): Promise<void> {
        const title = await vscode.window.showInputBox({
            prompt: 'New conversation title',
            value: 'New conversation'
        });
        if (title === undefined) {
            return;
        }
        const result = await this.connection.chatSessionCreate(title || 'New conversation');
        await this.loadSessions(result.session.id);
        await this.loadHistory();
        this.postChat('system', 'New conversation created.');
    }

    async renameChatSession(): Promise<void> {
        if (!this.currentSessionId) {
            return;
        }
        const current = this.chatSessions.find((item) => item.id === this.currentSessionId);
        const title = await vscode.window.showInputBox({
            prompt: 'Rename conversation',
            value: current?.title || ''
        });
        if (!title || !title.trim()) {
            return;
        }
        await this.connection.chatSessionRename(this.currentSessionId, title.trim());
        await this.loadSessions(this.currentSessionId);
        this.postState();
    }

    async archiveChatSession(): Promise<void> {
        if (!this.currentSessionId) {
            return;
        }
        const choice = await vscode.window.showWarningMessage(
            'Archive this conversation? Messages are retained.',
            { modal: true }, 'Archive');
        if (choice !== 'Archive') {
            return;
        }
        await this.connection.chatSessionArchive(this.currentSessionId);
        await this.loadSessions();
        await this.loadHistory();
        this.postState();
    }

    async deleteChatSession(): Promise<void> {
        if (!this.currentSessionId) {
            return;
        }
        const current = this.chatSessions.find((item) => item.id === this.currentSessionId);
        if (!current?.archived_at) {
            this.postChat('system', 'Archive the conversation before deleting it.');
            return;
        }
        const choice = await vscode.window.showWarningMessage(
            'Delete this archived conversation and its messages?',
            { modal: true }, 'Delete');
        if (choice !== 'Delete') {
            return;
        }
        await this.connection.chatSessionDelete(this.currentSessionId);
        await this.loadSessions();
        await this.loadHistory();
        this.postState();
    }

    async toggleArchivedSessions(): Promise<void> {
        this.showArchivedSessions = !this.showArchivedSessions;
        await this.loadSessions(this.currentSessionId);
    }

    async searchChat(): Promise<void> {
        const query = await vscode.window.showInputBox({
            prompt: 'Search persisted conversations'
        });
        if (!query || !query.trim()) {
            return;
        }
        const result = await this.connection.chatSearch(query.trim());
        const lines = (result.messages || []).map((item) =>
            `#${String(item['id'])} [${String(item['title'])}] ${String(item['role'])}: ${String(item['content']).slice(0, 240)}`);
        this.postChat('system', lines.length
            ? 'Search results:\n' + lines.join('\n')
            : 'No persisted conversation matched.');
    }

    async removeQueuedItem(itemId: string): Promise<void> {
        await this.connection.chatQueueRemove(String(itemId));
        await this.refreshQueue(false);
        this.postChat('system', 'Queued message removed.');
    }

    /** Read/refresh the persistent queue and optionally drain one item. */
    async refreshQueue(drain = false): Promise<void> {        if (!this.view) {
            return;
        }
        try {
            const result = await this.connection.chatQueue();
            this.chatQueue = Array.isArray(result.items) ? result.items : [];
            this.postState();
            if (drain && !this.busyChat && !this.busyMission && this.chatQueue.length) {
                const next = this.chatQueue[0];
                await this.connection.chatQueueRemove(next.id);
                await this.handleUserMessage(next.text, undefined, next.attachment_ids || []);
            }
        } catch (error) {
            this.output.appendLine('[queue] ' + this.errorText(error));
        }
    }

    async steerChat(text: string): Promise<void> {
        const message = String(text || '').trim();
        if (!message) {
            return;
        }
        if (this.busyMission && this.activeMissionId) {
            await this.connection.missionSteer(this.activeMissionId, message);
            this.postChat('system', 'Steering queued for mission #' + this.activeMissionId +
                '; it applies at the next safe agent stage.');
            return;
        }
        const result = await this.connection.chatSteer(message);
        this.postChat('system', 'Steering queued' +
            (typeof result.count === 'number' ? ' (' + result.count + ' in queue)' : '') +
            '; it applies at the next Chat checkpoint.');
        await this.refreshQueue(false);
    }

    async stopChat(): Promise<void> {
        try {
            const result = await this.connection.chatCancel();
            this.postChat('system', result.ok === false
                ? 'No running Chat turn to stop.'
                : 'Chat stop requested at the next safe checkpoint.');
        } catch (error) {
            this.reportError(error, 'chat-stop');
        }
    }

    /** Fetch a URL through the existing Research service, only on explicit user action. */
    async fetchUrl(url: string, confirmed = false): Promise<ResearchFetchResult | undefined> {
        const target = String(url || '').trim();
        if (!target) {
            return undefined;
        }
        const networkGranted = Boolean(this.settings?.permissions.policy.network);
        if (!networkGranted) {
            this.postChat('error',
                'Research fetch requires the NETWORK permission, which is not granted for this project. ' +
                'Permissions are owner/backend-owned; grant them in the engine settings first.');
            return undefined;
        }
        if (!confirmed) {
            const approved = await vscode.window.showWarningMessage(
                'Fetch this external page?',
                {
                    modal: true,
                    detail: `${target}\n\nThe request goes through the existing Research service and permission boundary. ` +
                        `Research profile: ${this.connection.researchProfile}. Page content is UNTRUSTED and will never be executed.`
                },
                'Fetch page'
            );
            if (approved !== 'Fetch page') {
                return undefined;
            }
        }
        this.busyPhase = 'fetching';
        this.postState();
        try {
            const result = await this.connection.researchFetch(target);
            this.research = result;
            if (!result.ok) {
                this.postChat('error', 'Research fetch not completed: ' +
                    (result.reason || result.outcome || 'unknown') +
                    (result.offline ? ' (Research offline)' : ''));
            } else {
                this.postChat('system', `Fetched: ${result.title || '(no title)'} — ${result.url || target}`);
            }
            this.postState();
            return result;
        } catch (error) {
            this.reportError(error, 'research');
            return undefined;
        } finally {
            this.busyPhase = 'idle';
            this.postState();
        }
    }

    async useResearchAsContext(): Promise<void> {
        const result = this.research;
        if (!result || !result.ok || !result.text) {
            return;
        }
        const item = await this.attachText(result.text, result.url || result.title || 'fetched-page');
        if (item) {
            this.research = undefined;
            this.postChat('system', `Fetched page added as chat context: ${result.title || result.url}`);
            this.postState();
        }
    }

    dismissResearch(): void {
        this.research = undefined;
        this.postState();
    }

    setChatModel(value: string): void {
        const allowed = this.modelOptions().some((option) => option.value === value);
        if (!allowed) {
            this.postChat('error', 'Model route is not available from the engine settings.');
            return;
        }
        this.chatModel = value;
        void this.workspaceState?.update('nlCodingAgent.chatModel', value);
        this.postState();
    }

    async setResearchProfile(profile: string, confirmed = false): Promise<void> {
        const next = profile === 'trusted-auto-review' ? 'trusted-auto-review' : 'manual';
        if (next === this.connection.researchProfile) {
            return;
        }
        if (!confirmed) {
            const choice = await vscode.window.showWarningMessage(
                'Change research auto-review profile?',
                {
                    modal: true,
                    detail: next === 'trusted-auto-review'
                        ? 'The engine restarts with the trusted-auto-review research profile. Network access still requires an explicit NETWORK grant and a web-fetch capability grant; every fetch button click remains an explicit action.'
                        : 'The engine restarts with the manual research profile: external fetches require human approval in the backend and the Fetch button will report needs_approval.'
                },
                'Apply profile'
            );
            if (choice !== 'Apply profile') {
                return;
            }
        }
        this.connection.setResearchProfile(next);
        await vscode.workspace.getConfiguration('nlCodingAgent').update(
            'researchProfile', next, vscode.ConfigurationTarget.Global
        );
        try {
            await this.connection.restart();
            await this.refreshAll(false);
            this.postChat('system', `Research profile: ${next}`);
            this.postState();
        } catch (error) {
            this.reportError(error, 'research');
        }
    }

    /**
     * Start a mission through the existing engine. The UI calls this after an
     * explicit modal confirmation; programmatic callers must pass confirmed=true.
     */
    async startMission(input: StartMissionInput, confirmed = false): Promise<{ missionId: number } | undefined> {
        if (this.busyMission) {
            this.postChat('error', 'A mission is already being started.');
            return undefined;
        }
        const goal = String(input.goal || '').trim();
        if (!goal) {
            this.postChat('error', 'The mission objective is empty.');
            return undefined;
        }
        if (!input.developerModel || !input.reviewerModel) {
            this.postChat('error', 'Select an exact developer and reviewer model route first.');
            return undefined;
        }
        if (!confirmed) {
            const approved = await this.confirm(
                'Start a real coding mission?',
                [
                    `Objective: ${goal.slice(0, 500)}`,
                    `Developer: ${input.developerModel}`,
                    `Reviewer: ${input.reviewerModel}`,
                    input.resumeMissionId ? `Resume mission #${input.resumeMissionId}` : 'New mission',
                    '',
                    'The existing Supervisor will modify the opened project through staging, run candidate/oracle verification and require reviewer approval before promotion.'
                ].join('\n'),
                'Start mission'
            );
            if (!approved) {
                return undefined;
            }
        }
        try {
            await this.ensureExecution();
            await this.connection.connect();
            const context = await this.requireBoundProject();
            this.busyMission = true;
            this.postState();
            const result = await this.connection.startMission({
                goal,
                developerModel: input.developerModel,
                reviewerModel: input.reviewerModel,
                resumeMissionId: input.resumeMissionId
            });
            this.activeMissionId = result.mission_id;
            this.postChat('system', `Mission #${result.mission_id} queued by the engine (${result.dispatch || 'queued'}).`);
            await this.refreshMissions();
            this.postState();
            this.startMonitoring(result.mission_id);
            return { missionId: result.mission_id };
        } catch (error) {
            this.reportError(error, 'mission');
            return undefined;
        } finally {
            this.busyMission = false;
            this.postState();
        }
    }

    /** Stop a mission at the next safe checkpoint (engine-cooperative). */
    async cancelMission(missionId: number, confirmed = false): Promise<boolean> {
        if (!confirmed) {
            const stop = await this.confirm(
                `Stop mission #${missionId}?`,
                'The engine stops at the next safe checkpoint. Staged work is retained and the live project is not modified by the stop.',
                'Stop mission'
            );
            if (!stop) {
                return false;
            }
        }
        try {
            await this.ensureExecution();
            const result = await this.connection.cancelMission(missionId);
            const accepted = result.accepted !== false;
            this.postChat('system', accepted
                ? `Stop requested for mission #${missionId}; waiting for a safe checkpoint.`
                : `Mission #${missionId} is already ${String(result.status || 'finished')}.`);
            return accepted;
        } catch (error) {
            this.reportError(error, 'mission');
            return false;
        }
    }

    /** Resume an interrupted/blocked mission with the same persisted objective. */
    async resumeMission(missionId: number, confirmed = false): Promise<boolean> {
        try {
            const detail = await this.connection.missionDetail(missionId);
            if (detail.mission.harness_version !== 2) {
                this.postChat('error', `Mission #${missionId} was created by a legacy harness and cannot be resumed by this engine.`);
                return false;
            }
            // The resume command can be invoked before the webview has loaded the
            // engine settings; fall back to the engine's configured mission routes.
            if (!this.missionModels.developerModel || !this.missionModels.reviewerModel) {
                const settings = this.settings || await this.connection.engineSettings(false);
                this.settings = settings;
                this.missionModels = {
                    developerModel: settings.mission_defaults.developer_model,
                    reviewerModel: settings.mission_defaults.reviewer_model
                };
            }
            if (!confirmed) {
                const resume = await this.confirm(
                    `Resume mission #${missionId}?`,
                    [
                        `Objective: ${String(detail.mission.goal || '').slice(0, 500)}`,
                        `Developer: ${this.missionModels.developerModel}`,
                        `Reviewer: ${this.missionModels.reviewerModel}`,
                        '',
                        'Resume keeps the existing objective and mission row; the engine re-runs the remaining stages.'
                    ].join('\n'),
                    'Resume mission'
                );
                if (!resume) {
                    return false;
                }
            }
            await this.ensureExecution();
            await this.connection.connect();
            const context = await this.requireBoundProject();
            const result = await this.connection.startMission({
                goal: String(detail.mission.goal || ''),
                developerModel: this.missionModels.developerModel,
                reviewerModel: this.missionModels.reviewerModel,
                resumeMissionId: missionId
            });
            this.activeMissionId = result.mission_id;
            this.postChat('system', `Mission #${result.mission_id} resume dispatched (${result.dispatch || 'queued'}).`);
            await this.refreshMissions();
            this.postState();
            this.startMonitoring(result.mission_id, { resumeFromInterrupted: true });
            return true;
        } catch (error) {
            this.reportError(error, 'resume');
            return false;
        }
    }

    async selectMission(missionId: number): Promise<void> {
        try {
            const detail = await this.connection.missionDetail(missionId);
            let diff: CandidateDiff | undefined;
            try {
                diff = await this.connection.candidateDiff(missionId);
            } catch (error) {
                diff = { ok: false, error: this.errorText(error) };
            }
            this.selected = { detail, diff };
            this.postState();
            this.post({ type: 'navigate', tab: 'missions' });
        } catch (error) {
            this.reportError(error, 'mission');
        }
    }

    async steerMissionById(missionId: number): Promise<void> {
        const text = await vscode.window.showInputBox({
            prompt: 'Steering instruction for mission #' + missionId
        });
        if (!text || !text.trim()) {
            return;
        }
        await this.connection.missionSteer(missionId, text.trim());
        this.postChat('system', 'Steering queued for mission #' + missionId
            + '; it applies at the next safe checkpoint.');
    }

    async refreshMissions(): Promise<void> {
        try {
            this.missions = await this.connection.missionList({
                includeArchived: this.missionShowArchived,
                status: this.missionStatusFilter || undefined,
                query: this.missionQuery || undefined
            });
        } catch (error) {
            this.output.appendLine('[missions] ' + this.errorText(error));
        }
    }

    async setMissionFilter(input: { includeArchived?: boolean; status?: string; query?: string }): Promise<void> {
        if (typeof input.includeArchived === 'boolean') {
            this.missionShowArchived = input.includeArchived;
        }
        if (typeof input.status === 'string') {
            this.missionStatusFilter = input.status;
        }
        if (typeof input.query === 'string') {
            this.missionQuery = input.query;
        }
        await this.refreshMissions();
        this.postState();
    }

    async archiveMissionById(missionId: number): Promise<void> {
        const choice = await vscode.window.showWarningMessage(
            'Archive mission #' + missionId + '? Evidence and diff are retained.',
            { modal: true }, 'Archive');
        if (choice !== 'Archive') {
            return;
        }
        await this.connection.archiveMission(missionId);
        await this.refreshMissions();
        if (this.selected?.detail.mission.id === missionId) {
            await this.selectMission(missionId);
        }
        this.postState();
    }

    async unarchiveMissionById(missionId: number): Promise<void> {
        await this.connection.unarchiveMission(missionId);
        await this.refreshMissions();
        this.postState();
    }

    async deleteMissionById(missionId: number): Promise<void> {
        const choice = await vscode.window.showWarningMessage(
            'Delete archived mission #' + missionId + ' from the mission database? '
            + 'Staged files remain for the Storage Manager.',
            { modal: true }, 'Delete');
        if (choice !== 'Delete') {
            return;
        }
        await this.connection.deleteMission(missionId);
        if (this.selected?.detail.mission.id === missionId) {
            this.selected = undefined;
        }
        await this.refreshMissions();
        this.postState();
    }

    async saveProviderSettings(payload: Record<string, unknown>): Promise<void> {
        const providerId = String(payload.providerId || '').trim();
        if (!/^[a-z][a-z0-9_]*$/.test(providerId)) {
            throw new EngineError('missing-provider',
                'Provider id must be lowercase letters, digits or underscores.');
        }
        await this.connection.saveProviderSettings(providerId, {
            enabled: typeof payload.enabled === 'boolean' ? payload.enabled : undefined,
            baseUrl: typeof payload.baseUrl === 'string' ? payload.baseUrl : undefined,
            label: typeof payload.label === 'string' ? payload.label : undefined,
            kind: typeof payload.kind === 'string' ? payload.kind : undefined,
            apiKeyEnv: typeof payload.apiKeyEnv === 'string' ? payload.apiKeyEnv : undefined
        });
        await this.refreshAll(false);
        this.postChat('system', 'Provider settings saved for ' + providerId + '.');
    }

    async saveRoleSettings(payload: Record<string, unknown>): Promise<void> {
        const role = String(payload.role || '');
        const model = String(payload.model || '');
        if (!role || !model) {
            throw new EngineError('missing-role-model', 'Role and model are required.');
        }
        await this.connection.saveRoleSettings(role, {
            model,
            temperature: typeof payload.temperature === 'number' ? payload.temperature : undefined
        });
        await this.refreshAll(false);
        this.postChat('system', `Role ${role} now uses ${model}.`);
    }

    async saveSpecialistAgent(payload: Record<string, unknown>): Promise<void> {
        const name = String(payload.name || '').trim();
        if (!name) {
            throw new EngineError('missing-agent-name', 'Specialist name is required.');
        }
        const agent: CustomAgent = {
            id: payload.id ? String(payload.id) : undefined,
            name,
            provider: String(payload.provider || 'ollama'),
            model: String(payload.model || '').trim(),
            role: String(payload.role || 'assistant').trim() || 'assistant',
            instructions: String(payload.instructions || '').trim(),
            tools: String(payload.tools || '').split(',').map((item) => item.trim()).filter(Boolean),
            permissions: String(payload.permissions || '').split(',').map((item) => item.trim()).filter(Boolean),
            enabled: payload.enabled !== false
        };
        if (agent.model && agent.model.indexOf('/') === -1 && agent.provider) {
            agent.model = agent.provider + '/' + agent.model;
        }
        const result = await this.connection.saveCustomAgent(agent);
        this.settings = await this.connection.engineSettings(false);
        this.postState();
        this.postChat('system', 'Specialist agent saved: ' + result.agent.name + '.');
    }

    async deleteSpecialistAgent(agentId: string): Promise<void> {
        if (!agentId) {
            return;
        }
        const choice = await vscode.window.showWarningMessage(
            'Delete this specialist agent profile?', { modal: true }, 'Delete');
        if (choice !== 'Delete') {
            return;
        }
        await this.connection.deleteCustomAgent(agentId);
        this.settings = await this.connection.engineSettings(false);
        this.postState();
        this.postChat('system', 'Specialist agent deleted.');
    }

    async duplicateSpecialistAgent(agentId: string): Promise<void> {
        if (!agentId) {
            return;
        }
        await this.connection.duplicateCustomAgent(agentId);
        this.settings = await this.connection.engineSettings(false);
        this.postState();
        this.postChat('system', 'Specialist agent duplicated.');
    }

    async saveGenerationParameters(payload: Record<string, unknown>): Promise<void> {
        const scope = String(payload.scope || 'model') as 'global' | 'role' | 'model';
        const params: Record<string, number | string | boolean | null> = {};
        for (const key of ['temperature', 'top_p', 'top_k', 'min_p', 'repeat_penalty', 'seed', 'max_tokens']) {
            const value = payload[key];
            if (value === '' || value === null || value === undefined) {
                continue;
            }
            const numeric = Number(value);
            if (!Number.isFinite(numeric)) {
                throw new EngineError('invalid-parameter', key + ' must be numeric.');
            }
            params[key] = numeric;
        }
        await this.connection.saveGenerationParameters(
            params, scope, String(payload.modelName || ''), String(payload.role || ''));
        this.generationParams = await this.connection.generationParameters(
            String(payload.modelName || ''), String(payload.role || ''));
        this.postState();
        this.postChat('system', 'Generation parameters saved.');
    }

    async saveCloudPolicy(enabled: boolean): Promise<void> {
        await this.connection.saveCloudEscalation(enabled);
        await this.refreshAll(false);
        this.postChat('system', 'Cloud escalation ' + (enabled ? 'enabled.' : 'disabled.'));
    }

    async savePermission(scope: string, granted: boolean): Promise<void> {
        const choice = await vscode.window.showWarningMessage(
            (granted ? 'Grant ' : 'Revoke ') + scope + ' for this project?',
            { modal: true },
            granted ? 'Grant' : 'Revoke');
        if (!choice) {
            return;
        }
        await this.connection.savePermissionScope(scope, granted);
        await this.refreshAll(false);
        this.postChat('system', `Permission ${scope}: ${granted ? 'granted' : 'revoked'}.`);
    }

    async probeModel(model: string): Promise<void> {
        const choice = await vscode.window.showWarningMessage(
            'Run real capability probes for ' + model + '?',
            {
                modal: true,
                detail: 'This loads the local model and measures tool calling, structured output and patch quality. It can take several minutes on 8 GB VRAM.'
            },
            'Probe');
        if (choice !== 'Probe') {
            return;
        }
        this.capabilityProbe = await this.connection.probeModelCapabilities(model);
        this.postState();
        this.postChat('system',
            `Probe ${model}: tools=${this.capabilityProbe.tool_calling}, `
            + `structured=${this.capabilityProbe.structured_output}, `
            + `patch=${this.capabilityProbe.patch_quality} (${this.capabilityProbe.patch_score.toFixed(2)})`);
    }

    async saveAutonomy(payload: Record<string, unknown>): Promise<void> {
        this.autonomy = await this.connection.saveAutonomySettings({
            mode: typeof payload.mode === 'string' ? payload.mode : undefined,
            maxMissions: typeof payload.maxMissions === 'number' ? payload.maxMissions : undefined,
            attempts: typeof payload.attempts === 'number' ? payload.attempts : undefined
        });
        this.postState();
        this.postChat('system', 'Autonomy settings saved (no run started).');
    }

    async saveMcpConfig(payload: Record<string, unknown>): Promise<void> {
        await this.connection.saveMcpServers(payload);
        await this.refreshAll(false);
        this.postChat('system', 'MCP server configuration saved.');
    }

    async scanStorage(): Promise<void> {
        this.storage = await this.connection.storageScan();
        this.postState();
    }

    async purgeStorage(selectedIds: string[]): Promise<void> {
        if (!selectedIds.length) {
            throw new EngineError('empty-selection', 'Select at least one storage category.');
        }
        const choice = await vscode.window.showWarningMessage(
            'Permanently delete ' + selectedIds.length + ' selected temporary storage item(s)?',
            { modal: true, detail: 'Sources, the live database and attachments are protected.' },
            'Purge');
        if (choice !== 'Purge') {
            return;
        }
        const result = await this.connection.storagePurge(selectedIds);
        await this.scanStorage();
        this.postChat('system', `Storage purge freed ${Math.round(result.freed_bytes / 1024 / 1024 * 100) / 100} MB.`);
    }

    async vacuumStorage(): Promise<void> {
        const choice = await vscode.window.showWarningMessage(
            'Compact the SQLite database now?',
            { modal: true, detail: 'A bounded backup is created first; active missions block compaction.' },
            'Compact');
        if (choice !== 'Compact') {
            return;
        }
        const result = await this.connection.storageVacuum();
        await this.scanStorage();
        this.postChat('system', result.ok
            ? `SQLite compacted; ${Math.round(result.freed_bytes / 1024 / 1024 * 100) / 100} MB freed.`
            : 'SQLite compaction failed: ' + (result.error || 'unknown error'));
    }


    async refreshModels(): Promise<void> {
        try {
            this.settings = await this.connection.engineSettings(true);
            if (!this.missionModels.developerModel) {
                this.missionModels = {
                    developerModel: this.settings.mission_defaults.developer_model,
                    reviewerModel: this.settings.mission_defaults.reviewer_model
                };
            }
            if (this.chatModel && !this.modelOptions().some((option) => option.value === this.chatModel)) {
                this.chatModel = '';
            }
            this.postState();
        } catch (error) {
            this.reportError(error, 'models');
        }
    }

    /** Toggle the --allow-execution engine session flag after an explicit warning. */
    async toggleExecution(confirmed = false): Promise<void> {
        const enable = !this.connection.executionAllowed;
        if (!confirmed) {
            const choice = await vscode.window.showWarningMessage(
                enable ? 'Enable mission execution for this engine session?' : 'Disable mission execution?',
                {
                    modal: true,
                    detail: enable
                        ? 'The extension will restart the engine with --allow-execution. Missions may modify the opened project through the existing Supervisor, staging and reviewer gates. Each start still requires its own confirmation, and READ/WRITE/EXECUTE permissions apply.'
                        : 'The engine restarts read-only. Stop any active mission first: replacing the engine process interrupts its in-process scheduler.'
                },
                enable ? 'Enable execution' : 'Disable execution'
            );
            if (choice !== (enable ? 'Enable execution' : 'Disable execution')) {
                return;
            }
        }
        const config = vscode.workspace.getConfiguration('nlCodingAgent');
        await config.update('allowExecution', enable, vscode.ConfigurationTarget.Global);
        this.connection.setAllowExecution(enable);
        try {
            await this.connection.restart();
            await this.refreshAll(false);
            this.postChat('system', enable ? 'Mission execution enabled for this session.' : 'Engine restarted read-only.');
            this.postState();
        } catch (error) {
            this.reportError(error, 'execution');
        }
    }

    /** Reload settings/missions after a reconnect or workspace change. */
    async refreshAll(probeModels = false): Promise<void> {
        await this.connection.connect();
        this.projectContext = await this.connection.projectContext();
        this.settings = await this.connection.engineSettings(probeModels);
        try {
            this.generationParams = await this.connection.generationParameters(
                this.settings.models.chat_default_spec || '', '');
        } catch (error) {
            this.output.appendLine('[generation-params] ' + this.errorText(error));
        }
        try {
            this.autonomy = await this.connection.autonomySettings();
        } catch (error) {
            this.output.appendLine('[autonomy] ' + this.errorText(error));
        }
        try {
            this.mcpConfig = (await this.connection.mcpServers()).config || {};
        } catch (error) {
            this.output.appendLine('[mcp] ' + this.errorText(error));
        }
        if (!this.missionModels.developerModel) {
            this.missionModels = {
                developerModel: this.settings.mission_defaults.developer_model,
                reviewerModel: this.settings.mission_defaults.reviewer_model
            };
        }
        if (this.chatModel && !this.modelOptions().some((option) => option.value === this.chatModel)) {
            this.chatModel = '';
        }
        this.refreshEditorContext();
        await this.refreshMissions();
        this.errorMessage = undefined;
        this.postState();
    }

    private isInsideRoot(filePath: string, root: string): boolean {
        try {
            const relative = path.relative(path.resolve(root), path.resolve(filePath));
            return relative === '' || (!relative.startsWith('..') && !path.isAbsolute(relative));
        } catch {
            return false;
        }
    }

    /**
     * Keep the last real text editor available when focus moves into the webview.
     * VS Code may report `activeTextEditor === undefined` while the chat view has
     * focus; the attach buttons must still work on the editor the user just used.
     */
    private currentEditor(): vscode.TextEditor | undefined {
        const active = vscode.window.activeTextEditor;
        if (active && !active.document.isClosed) {
            this.lastEditor = active;
        }
        const candidate = this.lastEditor;
        if (candidate && !candidate.document.isClosed) {
            return candidate;
        }
        this.lastEditor = undefined;
        return undefined;
    }

    private setupEditorTracking(): void {
        if (this.editorDisposables.length) {
            return;
        }
        const schedule = () => {
            if (this.editorTimer) {
                clearTimeout(this.editorTimer);
            }
            this.editorTimer = setTimeout(() => {
                this.refreshEditorContext();
                this.postState();
            }, 150);
        };
        this.editorDisposables.push(vscode.window.onDidChangeActiveTextEditor(schedule));
        this.editorDisposables.push(vscode.window.onDidChangeTextEditorSelection(schedule));
        this.refreshEditorContext();
    }

    /** Visible, controllable current-file/selection context (no file content read here). */
    refreshEditorContext(): void {
        const editor = this.currentEditor();
        if (!editor) {
            this.editorContext = undefined;
            return;
        }
        const root = this.connection.projectRoot;
        if (root && !this.isInsideRoot(editor.document.uri.fsPath, root)) {
            this.editorContext = undefined;
            return;
        }
        const selection = editor.selection;
        this.editorContext = {
            path: editor.document.uri.fsPath,
            relativePath: vscode.workspace.asRelativePath(editor.document.uri, false),
            languageId: editor.document.languageId,
            hasSelection: !selection.isEmpty,
            selectionLines: selection.isEmpty ? 0 : selection.end.line - selection.start.line + 1,
            dirty: editor.document.isDirty
        };
    }

    private startMonitoring(missionId: number, options?: { resumeFromInterrupted?: boolean }): void {
        if (this.monitorTimer) {
            clearInterval(this.monitorTimer);
            this.monitorTimer = undefined;
        }
        let waitingForResume = Boolean(options?.resumeFromInterrupted);
        const waitingSince = Date.now();
        const tick = async () => {
            try {
                const detail = await this.connection.missionDetail(missionId);
                this.activeMissionId = missionId;
                if (waitingForResume) {
                    // A resumed mission keeps its previous 'interrupted' row until the
                    // orchestrator starts the new run; do not mistake that stale row
                    // for the resumed run's terminal state.
                    if (detail.mission.status !== 'interrupted' || Number(detail.mission.resume_count) > 0) {
                        waitingForResume = false;
                    } else if (Date.now() - waitingSince > 120000) {
                        waitingForResume = false;
                    }
                }
                this.selected = { detail, diff: this.selected && this.selected.detail.mission.id === missionId ? this.selected.diff : undefined };
                await this.refreshMissions();
                if (!waitingForResume && TERMINAL_STATUSES.has(detail.mission.status)) {
                    if (this.monitorTimer) {
                        clearInterval(this.monitorTimer);
                        this.monitorTimer = undefined;
                    }
                    let diff: CandidateDiff | undefined;
                    try {
                        diff = await this.connection.candidateDiff(missionId);
                    } catch (error) {
                        diff = { ok: false, error: this.errorText(error) };
                    }
                    if (this.selected && this.selected.detail.mission.id === missionId) {
                        this.selected.diff = diff;
                    }
                    this.postChat('system', this.missionSummary(detail, diff));
                    this.postState();
                    return;
                }
                this.postState();
            } catch (error) {
                this.output.appendLine(`[mission #${missionId}] poll failed: ${this.errorText(error)}`);
            }
        };
        void tick();
        this.monitorTimer = setInterval(() => { void tick(); }, POLL_INTERVAL_MS);
    }

    private missionSummary(detail: MissionDetail, diff?: CandidateDiff): string {
        const verdict = detail.mission.review_verdict ? ` · verdict ${detail.mission.review_verdict}` : '';
        const promotion = detail.mission.promotion_status ? ` · ${detail.mission.promotion_status}` : '';
        const changed = Array.isArray(detail.mission.changed_paths) ? detail.mission.changed_paths.length : 0;
        const lines = [
            `Mission #${detail.mission.id} ${detail.mission.status}${verdict}${promotion}.`,
            detail.mission.result_summary || '',
            detail.mission.diff_stat ? `Diff: ${detail.mission.diff_stat}` : '',
            changed ? `Changed paths: ${(detail.mission.changed_paths as string[]).join(', ')}` : '',
            diff && diff.ok === false && diff.error ? `Diff unavailable: ${diff.error}` : ''
        ];
        return lines.filter((line) => line).join('\n');
    }

    private async onMessage(message: unknown): Promise<void> {
        if (!message || typeof message !== 'object') {
            return;
        }
        const data = message as { type?: string; action?: string; payload?: Record<string, unknown>; text?: unknown };
        if (data.type === 'ready') {
            await this.initialize();
            return;
        }
        if (data.type === 'navigate' && typeof data.payload?.tab === 'string') {
            this.post({ type: 'navigate', tab: data.payload.tab });
            return;
        }
        const action = data.action;
        const payload = data.payload || {};
        try {
            switch (action) {
                case 'sendChat':
                    await this.handleUserMessage(String(payload.text || ''));
                    break;
                case 'stopChat':
                    await this.stopChat();
                    break;
                case 'startMission':
                    await this.startMission({
                        goal: String(payload.goal || ''),
                        developerModel: String(payload.developerModel || ''),
                        reviewerModel: String(payload.reviewerModel || '')
                    });
                    break;
                case 'cancelMission':
                    await this.cancelMission(Number(payload.missionId));
                    break;
                case 'resumeMission':
                    await this.resumeMission(Number(payload.missionId));
                    break;
                case 'selectMission':
                    await this.selectMission(Number(payload.missionId));
                    break;
                case 'refreshMissions':
                    await this.refreshMissions();
                    this.postState();
                    break;
                case 'refreshEngine':
                    await this.refreshAll(true);
                    break;
                case 'refreshModels':
                    await this.refreshModels();
                    break;
                case 'refreshHistory':
                    await this.loadHistory();
                    this.postState();
                    break;
                case 'toggleExecution':
                    await this.toggleExecution();
                    break;
                case 'setChatModel':
                    this.setChatModel(String(payload.value || ''));
                    break;
                case 'attachPaths':
                    await this.attachPaths(Array.isArray(payload.paths)
                        ? (payload.paths as unknown[]).map((item) => String(item)) : []);
                    break;
                case 'attachFiles':
                    await this.attachWorkspaceFiles();
                    break;
                case 'attachEditor':
                    await this.attachActiveEditor(payload.kind === 'selection' ? 'selection' : 'file');
                    break;
                case 'dropUris':
                    await this.dropUris(Array.isArray(payload.uris)
                        ? (payload.uris as unknown[]).map((item) => String(item)) : []);
                    break;
                case 'removeAttachment':
                    this.removeAttachment(Number(payload.attachmentId));
                    break;
                case 'fetchUrl':
                    await this.fetchUrl(String(payload.url || ''));
                    break;
                case 'useResearch':
                    await this.useResearchAsContext();
                    break;
                case 'dismissResearch':
                    this.dismissResearch();
                    break;
                case 'setResearchProfile':
                    await this.setResearchProfile(String(payload.profile || 'manual'));
                    break;
                case 'setMissionModels':
                    this.missionModels = {
                        developerModel: String(payload.developerModel || this.missionModels.developerModel),
                        reviewerModel: String(payload.reviewerModel || this.missionModels.reviewerModel)
                    };
                    this.postState();
                    break;
                case 'newChatSession':
                    await this.newChatSession();
                    break;
                case 'renameChatSession':
                    await this.renameChatSession();
                    break;
                case 'archiveChatSession':
                    await this.archiveChatSession();
                    break;
                case 'deleteChatSession':
                    await this.deleteChatSession();
                    break;
                case 'selectChatSession':
                    await this.switchSession(String(payload.sessionId || ''));
                    break;
                case 'toggleArchivedSessions':
                    await this.toggleArchivedSessions();
                    break;
                case 'searchChat':
                    await this.searchChat();
                    break;
                case 'removeQueueItem':
                    await this.removeQueuedItem(String(payload.itemId || ''));
                    break;
                case 'saveProviderSettings':
                    await this.saveProviderSettings(payload);
                    break;
                case 'saveRoleSettings':
                    await this.saveRoleSettings(payload);
                    break;
                case 'saveSpecialistAgent':
                    await this.saveSpecialistAgent(payload);
                    break;
                case 'deleteSpecialistAgent':
                    await this.deleteSpecialistAgent(String(payload.agentId || ''));
                    break;
                case 'duplicateSpecialistAgent':
                    await this.duplicateSpecialistAgent(String(payload.agentId || ''));
                    break;
                case 'saveGenerationParameters':
                    await this.saveGenerationParameters(payload);
                    break;
                case 'saveCloudPolicy':
                    await this.saveCloudPolicy(Boolean(payload.enabled));
                    break;
                case 'savePermission':
                    await this.savePermission(String(payload.scope || ''),
                        Boolean(payload.granted));
                    break;
                case 'probeModel':
                    await this.probeModel(String(payload.model || ''));
                    break;
                case 'saveAutonomy':
                    await this.saveAutonomy(payload);
                    break;
                case 'saveMcpConfig':
                    await this.saveMcpConfig((payload.config || {}) as Record<string, unknown>);
                    break;
                case 'scanStorage':
                    await this.scanStorage();
                    break;
                case 'purgeStorage':
                    await this.purgeStorage(Array.isArray(payload.ids)
                        ? (payload.ids as unknown[]).map(String) : []);
                    break;
                case 'vacuumStorage':
                    await this.vacuumStorage();
                    break;
                case 'setMissionFilter':
                    await this.setMissionFilter({
                        includeArchived: typeof payload.includeArchived === 'boolean'
                            ? payload.includeArchived : undefined,
                        status: typeof payload.status === 'string' ? payload.status : undefined,
                        query: typeof payload.query === 'string' ? payload.query : undefined
                    });
                    break;
                case 'archiveMission':
                    await this.archiveMissionById(Number(payload.missionId));
                    break;
                case 'unarchiveMission':
                    await this.unarchiveMissionById(Number(payload.missionId));
                    break;
                case 'deleteMission':
                    await this.deleteMissionById(Number(payload.missionId));
                    break;
                case 'steerMission':
                    await this.steerMissionById(Number(payload.missionId));
                    break;
                default:
                    break;
            }
        } catch (error) {
            this.reportError(error, action || 'action');
        }
    }

    private async ensureExecution(): Promise<void> {
        if (this.connection.executionAllowed) {
            return;
        }
        const enable = await vscode.window.showWarningMessage(
            'Mission execution is disabled.',
            {
                modal: true,
                detail: 'No mission can start/cancel while the engine is read-only. Enable --allow-execution for this engine session? Every mission start still asks for confirmation.'
            },
            'Enable execution'
        );
        if (enable !== 'Enable execution') {
            throw new EngineError('execution-disabled', 'Mission execution is disabled. Enable it from the Engine tab first.');
        }
        const config = vscode.workspace.getConfiguration('nlCodingAgent');
        await config.update('allowExecution', true, vscode.ConfigurationTarget.Global);
        this.connection.setAllowExecution(true);
        await this.connection.restart();
    }

    private async requireBoundProject(): Promise<ProjectContext> {
        const context = await this.connection.projectContext();
        this.projectContext = context;
        const expected = this.connection.projectRoot;
        if (!expected) {
            throw new EngineError('no-workspace', 'Open a folder before using NL Coder.');
        }
        if (path.resolve(context.project.root).toLowerCase() !== path.resolve(expected).toLowerCase()) {
            throw new EngineError(
                'project-mismatch',
                `The engine is bound to "${context.project.root}", not the open workspace "${expected}". Run "NL Coder: Reconnect Backend".`
            );
        }
        return context;
    }

    private modelOptions(): ModelOption[] {
        const settings = this.settings;
        const defaultSpec = settings?.models.chat_default_spec || '';
        const chatRole = settings?.models.chat_role || '';
        const options: ModelOption[] = [{
            value: '',
            label: defaultSpec
                ? `Automatic — ${defaultSpec}${chatRole ? ' (' + chatRole + ')' : ''}`
                : 'Automatic — engine default',
            group: 'automatic',
            loaded: false,
            provider: '',
            model: '',
            automatic: true
        }];
        const seen = new Set<string>(['']);
        const add = (value: string, label: string, group: string, loaded = false) => {
            if (!value || seen.has(value)) {
                return;
            }
            seen.add(value);
            const slash = value.indexOf('/');
            options.push({
                value,
                label,
                group,
                loaded,
                provider: slash > 0 ? value.slice(0, slash) : '',
                model: slash > 0 ? value.slice(slash + 1) : value
            });
        };
        if (!settings) {
            return options;
        }
        for (const role of ['developer', 'reviewer', 'architect', 'chat']) {
            const model = settings.models.roles[role] && settings.models.roles[role].model;
            if (model) {
                add(model, `${role} · ${model}`, 'configured');
            }
        }
        for (const provider of settings.models.discovered?.providers || []) {
            if (!provider.reachable) {
                continue;
            }
            for (const model of provider.models || []) {
                const caps = model.capabilities || [];
                if (caps.includes('embedding') && !caps.includes('completion')) {
                    continue;
                }
                add(`${provider.provider_id}/${model.name}`,
                    `${model.name}${model.loaded ? ' (loaded)' : ''}`,
                    provider.label, Boolean(model.loaded));
            }
        }
        return options;
    }

    private buildState(): DashboardState {
        const settings = this.settings;
        return {
            connected: this.connection.state === 'ready',
            connectionState: this.connection.state,
            project: this.projectContext ? {
                id: this.projectContext.project.id,
                root: this.projectContext.project.root,
                name: this.projectContext.project.name
            } : undefined,
            engine: this.connection.engineInfo,
            executionEnabled: this.connection.executionAllowed,
            settings,
            missions: this.missions,
            selected: this.selected,
            activeMissionId: this.activeMissionId,
            busyChat: this.busyChat,
            busyMission: this.busyMission,
            busyPhase: this.busyPhase,
            chatModel: this.chatModel,
            missionModels: this.missionModels,
            modelOptions: this.modelOptions(),
            providers: (settings?.models.providers || []).map((provider) => ({
                id: provider.provider_id,
                label: provider.label,
                kind: provider.kind,
                enabled: provider.enabled
            })),
            defaultChatSpec: settings?.models.chat_default_spec || '',
            chatRole: settings?.models.chat_role || '',
            attachments: this.attachments,
            editor: this.editorContext,
            lastRoute: this.lastRoute,
            chatQueue: this.chatQueue.slice(),
            queueCount: this.chatQueue.length,
            chatSessions: this.chatSessions.slice(),
            currentSessionId: this.currentSessionId,
            showArchivedSessions: this.showArchivedSessions,
            missionShowArchived: this.missionShowArchived,
            missionStatusFilter: this.missionStatusFilter,
            missionQuery: this.missionQuery,
            generationParams: this.generationParams,
            autonomy: this.autonomy,
            storage: this.storage,
            capabilityProbe: this.capabilityProbe,
            mcpConfig: this.mcpConfig,
            research: this.research,
            researchProfile: this.connection.researchProfile,
            historyCount: this.historyCount,
            historyLoaded: this.historyLoaded,
            error: this.errorMessage
        };
    }

    private postState(): void {
        this.post({ type: 'state', payload: this.buildState() });
    }

    private statusLabel(): string {
        const project = this.projectContext;
        if (!project) {
            return 'connected';
        }
        return `${this.connection.executionAllowed ? 'missions' : 'read-only'} · project #${project.project.id}`;
    }

    private async confirm(message: string, detail: string, action: string): Promise<boolean> {
        const choice = await vscode.window.showWarningMessage(message, { modal: true, detail }, action);
        return choice === action;
    }

    private postChat(role: string, text: string): void {
        this.post({ type: 'chat', role, text });
    }

    private post(message: Record<string, unknown>): void {
        this.posted.push(message);
        if (this.posted.length > MAX_RECORDED_MESSAGES) {
            this.posted.shift();
        }
        void this.view?.webview.postMessage(message);
    }

    private errorText(error: unknown): string {
        return error instanceof Error ? error.message : String(error);
    }

    private reportError(error: unknown, phase: string): void {
        const code = error instanceof EngineError ? error.code : 'error';
        const detail = this.errorText(error);
        this.errorMessage = detail;
        this.output.appendLine(`[${phase}-error] ${code}: ${detail}`);
        this.post({ type: 'status', state: 'error', label: phase === 'connect' ? 'Engine unavailable' : 'Action failed' });
        this.postChat('error', detail);
        this.postState();
    }

    private async waitForView(timeoutMs: number): Promise<void> {
        const deadline = Date.now() + timeoutMs;
        while (!this.view && Date.now() < deadline) {
            await new Promise((resolve) => setTimeout(resolve, 100));
        }
    }

    async focusComposer(): Promise<void> {
        await this.waitForView(5000);
        if (this.view) {
            await new Promise((resolve) => setTimeout(resolve, 600));
            this.post({ type: 'focus' });
        }
    }

    dispose(): void {
        this.disposed = true;
        if (this.monitorTimer) {
            clearInterval(this.monitorTimer);
            this.monitorTimer = undefined;
        }
        if (this.editorTimer) {
            clearTimeout(this.editorTimer);
            this.editorTimer = undefined;
        }
        for (const disposable of this.editorDisposables) {
            disposable.dispose();
        }
        this.editorDisposables = [];
        this.view = undefined;
    }
}
