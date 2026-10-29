/**
 * NL Chat webview controller.
 *
 * The provider owns no business logic: every turn is forwarded to the bound
 * Python engine through EngineConnection. Model output is only ever posted as
 * data; the webview renders it with textContent.
 */
import * as path from 'path';
import * as vscode from 'vscode';
import { AttachmentInput, EngineConnection, EngineError, ProjectContext } from './backend';
import { buildChatHtml } from './webview';

const MAX_SELECTION_CHARS = 8000;
const MAX_RECORDED_MESSAGES = 200;

export interface ChatDebugState {
    resolved: boolean;
    busy: boolean;
    posted: Array<Record<string, unknown>>;
}

export class ChatProvider implements vscode.WebviewViewProvider {
    public static readonly viewType = 'nlCodingAgent.chat';

    private view: vscode.WebviewView | undefined;
    private busy = false;
    private readyAnnounced = false;
    private disposed = false;
    private lastHtml: string | undefined;
    private readonly posted: Array<Record<string, unknown>> = [];

    constructor(
        private readonly extensionUri: vscode.Uri,
        private readonly connection: EngineConnection,
        private readonly output: vscode.OutputChannel,
        private readonly requestTimeoutMs: number
    ) {}

    /** Test-only inspection of what the webview actually received. */
    get debugState(): ChatDebugState {
        return { resolved: Boolean(this.view), busy: this.busy, posted: this.posted.slice() };
    }

    get isResolved(): boolean {
        return Boolean(this.view);
    }

    /** Test-only: the exact HTML handed to the webview. */
    get renderedHtml(): string | undefined {
        return this.lastHtml;
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

    /** Connect (or verify the connection) and post real project/tool identity to the webview. */
    async announceStatus(): Promise<void> {
        if (!this.view || this.disposed) {
            return;
        }
        this.post({ type: 'status', state: 'connecting', label: 'Connecting to NL Coding Engine…' });
        try {
            await this.connection.connect();
            const context = await this.connection.projectContext();
            const tools = await this.connection.listTools();
            const engine = this.connection.engineInfo;
            this.post({
                type: 'status',
                state: 'ready',
                label: `Connected · project #${context.project.id} · ${tools.length} tools`
            });
            if (!this.readyAnnounced) {
                this.readyAnnounced = true;
                this.post({
                    type: 'message',
                    role: 'system',
                    text: [
                        'Connected to the existing NL Coding Engine.',
                        `Project: #${context.project.id}${context.project.name ? ' ' + context.project.name : ''}`,
                        `Workspace: ${context.project.root}`,
                        `Engine: ${engine?.name || 'NL Coding Engine'}${engine?.version ? ' ' + engine.version : ''}`,
                        `Tools (${tools.length}): ${tools.map(tool => tool.name).join(', ')}`
                    ].join('\n')
                });
            }
            this.output.appendLine(
                `[connected] project #${context.project.id} ${context.project.root} · ` +
                `${engine?.name || ''} ${engine?.version || ''} · pid ${this.connection.childPid ?? '?'}`
            );
        } catch (error) {
            this.reportError(error, 'connect');
        }
    }

    /** One chat turn. Public so the extension-host acceptance test can drive the same path as the webview. */
    async handleUserMessage(text: string, attachment?: AttachmentInput | null): Promise<void> {
        const message = String(text || '').trim();
        if (!message) {
            return;
        }
        if (this.busy) {
            this.post({ type: 'message', role: 'error', text: 'A reply is already running for this project.' });
            return;
        }
        this.busy = true;
        this.post({ type: 'busy', value: true });
        try {
            await this.connection.connect();
            const context = await this.requireBoundProject();
            const attachments = attachment && attachment.extracted_text && attachment.extracted_text.trim()
                ? [attachment]
                : [];
            const result = await this.connection.converse(context.project.id, message, attachments, this.requestTimeoutMs);
            this.post({ type: 'message', role: 'assistant', text: result.reply || '' });
            this.output.appendLine(
                `[chat] project #${context.project.id}: ${message.length} chars in, ` +
                `${(result.reply || '').length} chars out`
            );
        } catch (error) {
            this.reportError(error, 'chat');
        } finally {
            this.busy = false;
            this.post({ type: 'busy', value: false });
        }
    }

    /** Ask the webview to focus its composer (used after the chat view is revealed). */
    async focusComposer(): Promise<void> {
        await this.waitForView(5000);
        if (this.view) {
            // The webview document loads asynchronously after the view resolves.
            await new Promise((resolve) => setTimeout(resolve, 600));
            this.post({ type: 'focus' });
        }
    }

    private async waitForView(timeoutMs: number): Promise<void> {
        const deadline = Date.now() + timeoutMs;
        while (!this.view && Date.now() < deadline) {
            await new Promise((resolve) => setTimeout(resolve, 100));
        }
    }

    dispose(): void {
        this.disposed = true;
        this.view = undefined;
    }

    private async onMessage(message: unknown): Promise<void> {
        if (!message || typeof message !== 'object') {
            return;
        }
        const data = message as { type?: string; text?: unknown };
        if (data.type === 'ready') {
            await this.announceStatus();
            return;
        }
        if (data.type === 'send') {
            await this.handleUserMessage(
                typeof data.text === 'string' ? data.text : '',
                this.readSelection()
            );
        }
    }

    private async requireBoundProject(): Promise<ProjectContext> {
        const context = await this.connection.projectContext();
        const expected = this.connection.projectRoot;
        if (!expected) {
            throw new EngineError('no-workspace', 'Open a folder before using NL Chat.');
        }
        if (path.resolve(context.project.root).toLowerCase() !== path.resolve(expected).toLowerCase()) {
            throw new EngineError(
                'project-mismatch',
                `The engine is bound to "${context.project.root}", not the open workspace "${expected}". ` +
                'Run "NL Coding Agent: Reconnect Backend".'
            );
        }
        return context;
    }

    private readSelection(): AttachmentInput | null {
        const editor = vscode.window.activeTextEditor;
        if (!editor || editor.selection.isEmpty) {
            return null;
        }
        const text = editor.document.getText(editor.selection);
        if (!text.trim()) {
            return null;
        }
        return {
            name: path.basename(editor.document.fileName),
            extracted_text: text.slice(0, MAX_SELECTION_CHARS)
        };
    }

    private post(message: Record<string, unknown>): void {
        this.posted.push(message);
        if (this.posted.length > MAX_RECORDED_MESSAGES) {
            this.posted.shift();
        }
        void this.view?.webview.postMessage(message);
    }

    private reportError(error: unknown, phase: string): void {
        const code = error instanceof EngineError ? error.code : 'error';
        const detail = error instanceof Error ? error.message : String(error);
        this.output.appendLine(`[${phase}-error] ${code}: ${detail}`);
        this.post({
            type: 'status',
            state: 'error',
            label: phase === 'connect' ? 'Engine unavailable' : 'Chat failed'
        });
        this.post({ type: 'message', role: 'error', text: detail });
    }
}
