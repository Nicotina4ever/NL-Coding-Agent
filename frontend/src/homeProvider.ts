import * as vscode from 'vscode';

export interface HomeState {
    connected: boolean;
    connectionState: string;
    projectName: string;
    projectRoot: string;
    projectId?: number;
    engineName?: string;
    engineVersion?: string;
    executionEnabled: boolean;
    missionTotal: number;
    missionActive: number;
    missionCompleted: number;
    modelCount: number;
    configuredModels: string[];
    agentCount: number;
    roleNames: string[];
    sessionCount: number;
    queueCount: number;
    isStandalone: boolean;
    error?: string;
}

const COMMANDS: Array<{ id: string; label: string; detail: string; icon: string; kind: string }> = [
    { id: 'nlCodingAgent.startChat', label: 'Chat', detail: 'Talk to the engine and act with tools', icon: '✦', kind: 'primary' },
    { id: 'nlCodingAgent.startMission', label: 'New mission', detail: 'Plan, implement, verify and review', icon: '➜', kind: 'primary' },
    { id: 'nlCodingAgent.showMissions', label: 'Mission Control', detail: 'Live status, handoffs and diffs', icon: '▤', kind: '' },
    { id: 'nlCodingAgent.openModelHub', label: 'Model Hub', detail: 'Providers, roles and capabilities', icon: '◈', kind: '' },
    { id: 'nlCodingAgent.openAgents', label: 'Agents', detail: 'Roles, models and tool policy', icon: '◎', kind: '' },
    { id: 'nlCodingAgent.openStorage', label: 'Storage', detail: 'Scan, compact and clean safely', icon: '▣', kind: '' },
    { id: 'nlCodingAgent.showEngineSettings', label: 'Engine settings', detail: 'Permissions, autonomy and MCP', icon: '⚙', kind: '' }
];

const DEV_COMMANDS: Array<{ id: string; label: string }> = [
    { id: 'workbench.action.files.openFolder', label: 'Open folder' },
    { id: 'workbench.action.terminal.new', label: 'Terminal' },
    { id: 'workbench.view.scm', label: 'Source Control' },
    { id: 'workbench.action.debug.start', label: 'Run & Debug' },
    { id: 'workbench.action.findInFiles', label: 'Search' },
    { id: 'workbench.action.showCommands', label: 'Commands' }
];

export class HomeProvider implements vscode.WebviewViewProvider {
    public static readonly viewType = 'nlCodingAgent.home';
    private view: vscode.WebviewView | undefined;
    private panel: vscode.WebviewPanel | undefined;
    private state: HomeState | undefined;
    private lastHtml: string | undefined;

    constructor(private readonly extensionUri: vscode.Uri,
                private readonly refreshState: () => Promise<HomeState>) {}

    get renderedHtml(): string | undefined { return this.lastHtml; }

    async openPanel(): Promise<void> {
        if (this.panel) {
            this.panel.reveal(vscode.ViewColumn.Active);
            await this.refresh();
            return;
        }
        const media = vscode.Uri.joinPath(this.extensionUri, 'media');
        const panel = vscode.window.createWebviewPanel(
            HomeProvider.viewType,
            'NL Code — Home',
            vscode.ViewColumn.Active,
            { enableScripts: true, retainContextWhenHidden: true, localResourceRoots: [media] }
        );
        this.panel = panel;
        this.attach(panel.webview, media);
        panel.onDidDispose(() => { this.panel = undefined; });
        await this.refresh();
    }

    async resolveWebviewView(view: vscode.WebviewView): Promise<void> {
        this.view = view;
        const media = vscode.Uri.joinPath(this.extensionUri, 'media');
        view.webview.options = { enableScripts: true, localResourceRoots: [media] };
        this.attach(view.webview, media);
        view.onDidDispose(() => { this.view = undefined; });
        await this.refresh();
    }

    private attach(webview: vscode.Webview, media: vscode.Uri): void {
        this.lastHtml = this.html(
            webview.asWebviewUri(vscode.Uri.joinPath(media, 'home.js')).toString(),
            webview.asWebviewUri(vscode.Uri.joinPath(media, 'home.css')).toString(),
            webview.asWebviewUri(vscode.Uri.joinPath(media, 'logo.svg')).toString(),
            webview.cspSource
        );
        webview.html = this.lastHtml;
        webview.onDidReceiveMessage(async (message: unknown) => {
            if (!message || typeof message !== 'object') {
                return;
            }
            const data = message as { type?: string; command?: string };
            if (data.type === 'ready' || data.type === 'refresh') {
                await this.refresh();
            } else if (data.type === 'command' && typeof data.command === 'string') {
                try {
                    await vscode.commands.executeCommand(data.command);
                } catch (error) {
                    void vscode.window.showErrorMessage(
                        'NL Code: ' + (error instanceof Error ? error.message : String(error)));
                }
            }
        });
    }

    async refresh(): Promise<void> {
        try {
            this.state = await this.refreshState();
        } catch (error) {
            this.state = {
                connected: false, connectionState: 'failed', projectName: '', projectRoot: '',
                executionEnabled: false, missionTotal: 0, missionActive: 0, missionCompleted: 0,
                modelCount: 0, configuredModels: [], agentCount: 0, roleNames: [],
                sessionCount: 0, queueCount: 0, isStandalone: false,
                error: error instanceof Error ? error.message : String(error)
            };
        }
        const message = { type: 'homeState', payload: this.state };
        void this.view?.webview.postMessage(message);
        void this.panel?.webview.postMessage(message);
    }

    private html(script: string, style: string, logo: string, csp: string): string {
        const cspContent = ["default-src 'none'", `img-src ${csp} data:`, `style-src ${csp}`,
            `script-src ${csp}`, "base-uri 'none'", "form-action 'none'"].join('; ');
        const cards = COMMANDS.map((command) => `
            <button type="button" class="card ${command.kind}" data-command="${command.id}">
                <span class="card-icon">${command.icon}</span>
                <span class="card-body"><strong>${command.label}</strong><small>${command.detail}</small></span>
                <span class="card-arrow">→</span>
            </button>`).join('');
        const devCards = DEV_COMMANDS.map((command) =>
            `<button type="button" class="dev" data-command="${command.id}">${command.label}</button>`).join('');
        return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="${cspContent}">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="stylesheet" href="${style}">
<title>NL Code</title>
</head>
<body>
<header class="hero">
    <div class="brand-row"><img class="logo" src="${logo}" alt="NL Code"><span class="brand">NL CODE</span><span class="version">1.0</span></div>
    <h1>Local engineering workbench.</h1>
    <p>Chat, missions, models and agents share one local engine. Code, terminal, Git, debugging and extensions stay inside the same workbench.</p>
    <div class="status-row">
        <span id="connection" class="pill">connecting</span>
        <span id="project" class="pill soft">no project</span>
        <span id="execution" class="pill soft">read-only</span>
    </div>
</header>
<main>
    <section class="metrics" aria-label="Engine status">        <div class="metric"><span id="mission-count">0</span><small>missions</small></div>
        <div class="metric"><span id="active-count">0</span><small>active</small></div>
        <div class="metric"><span id="model-count">0</span><small>models</small></div>
        <div class="metric"><span id="agent-count">0</span><small>agents</small></div>
        <div class="metric"><span id="session-count">0</span><small>chats</small></div>
    </section>
    <section class="grid" aria-label="NL Code actions">${cards}</section>
    <section class="panel">
        <div class="panel-head"><h2>Development workbench</h2><span>Everything Code - OSS provides stays available.</span></div>
        <div class="dev-row">${devCards}</div>
    </section>
    <section class="panel details-panel">
        <div class="panel-head"><h2>Live context</h2><button id="refresh" type="button">Refresh</button></div>
        <div id="details" class="details"></div>
        <div id="error" class="error hidden"></div>
    </section>
    <footer>
        <button id="theme" type="button" class="text-button" data-command="nlCodingAgent.applyTheme">Apply NL Code theme</button>
        <span id="standalone" class="muted"></span>
    </footer>
</main>
<script src="${script}"></script>
</body>
</html>`;
    }
}
