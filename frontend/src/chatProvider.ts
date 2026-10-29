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
    CandidateDiff,
    EngineConnection,
    EngineError,
    EngineSettings,
    MissionDetail,
    MissionRow,
    ProjectContext
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
    chatModel: string;
    missionModels: { developerModel: string; reviewerModel: string };
    modelOptions: ModelOption[];
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
    private chatModel = '';
    private missionModels = { developerModel: '', reviewerModel: '' };
    private monitorTimer: NodeJS.Timeout | undefined;
    private errorMessage: string | undefined;

    constructor(
        private readonly extensionUri: vscode.Uri,
        private readonly connection: EngineConnection,
        private readonly output: vscode.OutputChannel,
        private readonly requestTimeoutMs: number
    ) {}

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
    postNavigation(tab: 'chat' | 'missions' | 'engine'): void {
        this.post({ type: 'navigate', tab });
    }

    /** Connect, load engine state/missions and post the first full snapshot. */
    async initialize(): Promise<void> {
        if (!this.view || this.disposed) {
            return;
        }
        this.post({ type: 'status', state: 'connecting', label: 'Connecting to NL Coding Engine…' });
        try {
            await this.refreshAll(false);
            if (!this.readyAnnounced) {
                this.readyAnnounced = true;
                this.postChat('system', [
                    'Connected to the existing NL Coding Engine.',
                    `Project: #${this.projectContext?.project.id}${this.projectContext?.project.name ? ' ' + this.projectContext.project.name : ''}`,
                    `Workspace: ${this.projectContext?.project.root}`,
                    `Execution: ${this.connection.executionAllowed ? 'missions enabled' : 'read-only'}`
                ].join('\n'));
            }
            this.post({ type: 'status', state: 'ready', label: this.statusLabel() });
        } catch (error) {
            this.reportError(error, 'connect');
        }
    }

    /** Backwards-compatible entry point used by commands/tests. */
    async announceStatus(): Promise<void> {
        this.readyAnnounced = false;
        await this.initialize();
    }

    /** One chat turn; the webview appends the user message locally. */
    async handleUserMessage(text: string, attachment?: AttachmentInput | null): Promise<void> {
        const message = String(text || '').trim();
        if (!message) {
            return;
        }
        if (this.busyChat) {
            this.postChat('error', 'A reply is already running for this project.');
            return;
        }
        this.busyChat = true;
        this.postState();
        try {
            await this.connection.connect();
            const context = await this.requireBoundProject();
            const attachments = attachment && attachment.extracted_text && attachment.extracted_text.trim()
                ? [attachment]
                : [];
            const result = await this.connection.converse(
                context.project.id, message, attachments, this.requestTimeoutMs,
                this.chatModel || undefined
            );
            this.postChat('assistant', result.reply || '');
            this.output.appendLine(`[chat] project #${context.project.id}: ${message.length} chars in, ${(result.reply || '').length} chars out`);
        } catch (error) {
            this.reportError(error, 'chat');
        } finally {
            this.busyChat = false;
            this.postState();
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

    async refreshMissions(): Promise<void> {
        try {
            this.missions = await this.connection.missionList();
        } catch (error) {
            this.output.appendLine('[missions] ' + this.errorText(error));
        }
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
        if (!this.missionModels.developerModel) {
            this.missionModels = {
                developerModel: this.settings.mission_defaults.developer_model,
                reviewerModel: this.settings.mission_defaults.reviewer_model
            };
        }
        if (!this.chatModel) {
            this.chatModel = this.settings.models.chat_default_spec || '';
        }
        await this.refreshMissions();
        this.errorMessage = undefined;
        this.postState();
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
                    await this.refreshModels();
                    break;
                case 'toggleExecution':
                    await this.toggleExecution();
                    break;
                case 'setChatModel':
                    this.chatModel = String(payload.value || '');
                    this.postState();
                    break;
                case 'setMissionModels':
                    this.missionModels = {
                        developerModel: String(payload.developerModel || this.missionModels.developerModel),
                        reviewerModel: String(payload.reviewerModel || this.missionModels.reviewerModel)
                    };
                    this.postState();
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
            throw new EngineError('no-workspace', 'Open a folder before using NL Chat.');
        }
        if (path.resolve(context.project.root).toLowerCase() !== path.resolve(expected).toLowerCase()) {
            throw new EngineError(
                'project-mismatch',
                `The engine is bound to "${context.project.root}", not the open workspace "${expected}". Run "NL Coding Agent: Reconnect Backend".`
            );
        }
        return context;
    }

    private modelOptions(): ModelOption[] {
        const options: ModelOption[] = [{ value: '', label: 'Engine default', group: 'default', loaded: false }];
        const seen = new Set<string>(['']);
        const add = (value: string, label: string, group: string, loaded = false) => {
            if (!value || seen.has(value)) {
                return;
            }
            seen.add(value);
            options.push({ value, label, group, loaded });
        };
        const settings = this.settings;
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
                add(`${provider.provider_id}/${model.name}`, `${model.name}${model.loaded ? ' (loaded)' : ''}`, provider.label, Boolean(model.loaded));
            }
        }
        return options;
    }

    private buildState(): DashboardState {
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
            settings: this.settings,
            missions: this.missions,
            selected: this.selected,
            activeMissionId: this.activeMissionId,
            busyChat: this.busyChat,
            busyMission: this.busyMission,
            chatModel: this.chatModel,
            missionModels: this.missionModels,
            modelOptions: this.modelOptions(),
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
        this.view = undefined;
    }
}
