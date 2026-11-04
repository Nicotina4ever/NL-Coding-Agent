/**
 * Activation for the NL Coder VS Code frontend.
 *
 * The extension is a thin client: it locates the existing engine installation,
 * opens one MCP stdio session bound to the active workspace folder, exposes the
 * NL dashboard webview (chat, model choice, persistent missions, verification),
 * and releases the session on deactivation. All mission execution, persistence,
 * staging and verification stay in the Python engine.
 */
import * as vscode from 'vscode';
import {
    CandidateDiff,
    EngineConnection,
    EngineSettings,
    MissionDetail
} from './backend';
import { ChatProvider, StartMissionInput } from './chatProvider';
import { HomeProvider, HomeState } from './homeProvider';

export interface StatusReport {
    state: string;
    pid?: number;
    projectRoot: string;
    engineName?: string;
    engineVersion?: string;
    projectId?: number;
    projectName?: string;
    tools?: string[];
    executionEnabled?: boolean;
    error?: string;
}

export interface NlCodingAgentApi {
    connection: EngineConnection;
    chat: ChatProvider;
    home?: HomeProvider;
    connect(): Promise<void>;
    shutdown(): Promise<void>;
    getStatus(): Promise<StatusReport>;
    refresh(): Promise<void>;
    refreshWorkbench(): Promise<void>;
    startMission(input: StartMissionInput): Promise<{ missionId: number } | undefined>;
    selectMission(missionId: number): Promise<void>;
    getMissionDetail(missionId: number): Promise<MissionDetail>;
    getCandidateDiff(missionId: number): Promise<CandidateDiff>;
    cancelMission(missionId: number): Promise<boolean>;
    resumeMission(missionId: number): Promise<boolean>;
    attachPaths(paths: string[]): Promise<void>;
    attachText(text: string, name: string): Promise<unknown>;
    fetchUrl(url: string, confirmed?: boolean): Promise<unknown>;
    loadHistory(): Promise<void>;
    setChatModel(route: string): void;
}

let connection: EngineConnection | undefined;
let chat: ChatProvider | undefined;
let home: HomeProvider | undefined;
let output: vscode.OutputChannel | undefined;
let timeoutMs = 1_800_000;

export function isNlCodeStandalone(): boolean {
    return vscode.env.uriScheme === 'nl-code' || /(^|\b)NL Code\b/i.test(vscode.env.appName || '');
}

const ENGINE_ENV_KEYS = ['NL_DATA_DIR', 'NL_WORKSPACE_DIR', 'NL_MODELS_CONFIG', 'NL_ENGINE_ROOT'] as const;

function workspaceRoot(): string {
    const folder = vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders[0];
    return folder ? folder.uri.fsPath : '';
}

function engineEnvironment(): Record<string, string> {
    const env: Record<string, string> = {};
    for (const key of ENGINE_ENV_KEYS) {
        const value = process.env[key];
        if (value) {
            env[key] = value;
        }
    }
    return env;
}

function modelPickerOptions(settings: EngineSettings): Array<{ label: string; description: string; route: string }> {
    const seen = new Set<string>();
    const options: Array<{ label: string; description: string; route: string }> = [];
    const add = (route: string, label: string, description: string) => {
        if (!route || seen.has(route)) {
            return;
        }
        seen.add(route);
        options.push({ label, description, route });
    };
    for (const role of ['developer', 'reviewer', 'architect', 'chat']) {
        const model = settings.models.roles[role] && settings.models.roles[role].model;
        if (model) {
            add(model, model, `configured role ${role}`);
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
            add(`${provider.provider_id}/${model.name}`, model.name,
                `${provider.label}${model.loaded ? ' · loaded' : ''}${model.size_gb ? ' · ' + model.size_gb + ' GB' : ''}`);
        }
    }
    return options;
}

async function pickModel(
    settings: EngineSettings,
    role: string,
    fallback: string
): Promise<string | undefined> {
    const options = modelPickerOptions(settings);
    const picked = await vscode.window.showQuickPick(
        options.map((option) => ({
            label: option.label,
            description: option.description,
            detail: option.route === fallback ? 'configured default' : option.route,
            route: option.route
        })),
        {
            title: `NL Coder — ${role} model`,
            placeHolder: fallback || 'Select an exact provider/model route',
            matchOnDescription: true,
            matchOnDetail: true
        }
    );
    return picked ? picked.route : undefined;
}

async function collectHomeState(): Promise<HomeState> {
    const base: HomeState = {
        connected: false,
        connectionState: connection?.state || 'idle',
        projectName: '',
        projectRoot: connection?.projectRoot || '',
        executionEnabled: Boolean(connection?.executionAllowed),
        missionTotal: 0,
        missionActive: 0,
        missionCompleted: 0,
        modelCount: 0,
        configuredModels: [],
        agentCount: 0,
        roleNames: [],
        sessionCount: 0,
        queueCount: 0,
        isStandalone: isNlCodeStandalone()
    };
    if (!connection) {
        return base;
    }
    try {
        const context = await connection.projectContext();
        base.connected = connection.state === 'ready';
        base.projectId = context.project.id;
        base.projectName = context.project.name || '';
        base.projectRoot = context.project.root;
        base.engineName = connection.engineInfo?.name;
        base.engineVersion = connection.engineInfo?.version;
    } catch (error) {
        base.connected = false;
        base.error = error instanceof Error ? error.message : String(error);
    }
    try {
        const settings = await connection.engineSettings(false);
        base.executionEnabled = base.executionEnabled;
        base.configuredModels = Array.from(new Set(
            Object.values(settings.models.roles || {})
                .map((role) => role && role.model)
                .filter((value): value is string => Boolean(value))));
        base.roleNames = Object.keys(settings.models.roles || {});
        base.modelCount = new Set([
            ...base.configuredModels,
            ...(settings.models.discovered?.providers.flatMap((provider) =>
                (provider.models || []).map((model) => `${provider.provider_id}/${model.name}`)) || [])
        ]).size;
        base.agentCount = (settings.agents.roles || []).length +
            (settings.agents.custom_agents || []).length;
    } catch (error) {
        base.error = base.error || (error instanceof Error ? error.message : String(error));
    }
    try {
        const missions = await connection.missionList({ includeArchived: true });
        base.missionTotal = missions.length;
        base.missionActive = missions.filter((mission) =>
            mission.status === 'running' || mission.status === 'pending').length;
        base.missionCompleted = missions.filter((mission) => mission.status === 'completed').length;
    } catch { /* home remains useful with partial state */ }
    try {
        base.resources = await connection.resourceStatus();
    } catch { /* resource HUD is optional */ }
    try {
        const sessions = await connection.chatSessions(false);
        base.sessionCount = (sessions.sessions || []).length;
    } catch { /* optional */ }
    try {
        const queue = await connection.chatQueue();
        base.queueCount = Array.isArray(queue.items) ? queue.items.length : 0;
    } catch { /* optional */ }
    return base;
}

export async function activate(context: vscode.ExtensionContext): Promise<NlCodingAgentApi> {
    output = vscode.window.createOutputChannel('NL Coder');
    context.subscriptions.push(output);
    output.appendLine('NL Coder extension activated.');

    const config = vscode.workspace.getConfiguration('nlCodingAgent');
    const timeoutSeconds = Math.max(30, config.get<number>('requestTimeoutSeconds', 1800));
    timeoutMs = timeoutSeconds * 1000;
    const engineRoot = config.get<string>('engineRoot', '') || process.env.NL_ENGINE_ROOT || '';
    const pythonPath = config.get<string>('pythonPath', '') || process.env.NL_PYTHON_PATH || '';
    const allowExecution = config.get<boolean>('allowExecution', false);
    const researchProfile = config.get<string>('researchProfile', 'manual');
    const projectRoot = workspaceRoot();

    connection = new EngineConnection({
        engineRoot,
        pythonPath,
        extensionPath: context.extensionUri.fsPath,
        projectRoot,
        allowExecution,
        researchProfile,
        env: engineEnvironment(),
        requestTimeoutMs: timeoutMs,
        log: (line: string) => output?.appendLine(line)
    });
    chat = new ChatProvider(context.extensionUri, connection, output, timeoutMs, context);
    // A dead engine must never be shown as "connected": the transport notifies the
    // provider whenever it transitions (ready/failed/closed) and the webview re-renders.
    connection.onStateChange = () => chat?.notifyConnectionState();

    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider(ChatProvider.viewType, chat, {
            webviewOptions: { retainContextWhenHidden: true }
        })
    );

    home = new HomeProvider(context.extensionUri, collectHomeState);

    const refreshWorkbench = async (): Promise<void> => {
        try {
            await home?.refresh();
        } catch { /* home is optional */ }
    };

    const revealChat = async (tab?: 'chat' | 'missions' | 'agents' | 'engine') => {
        await chat?.openPanel();
        if (tab) {
            chat?.postNavigation(tab);
        }
        await chat?.focusComposer();
    };

    const api: NlCodingAgentApi = {
        connection,
        chat,
        home: home || undefined,
        connect: () => connection!.connect(),
        shutdown: async () => {
            await connection!.close();
        },
        getStatus: async () => {
            const status: StatusReport = {
                state: connection!.state,
                pid: connection!.childPid,
                projectRoot: connection!.projectRoot,
                engineName: connection!.engineInfo?.name,
                engineVersion: connection!.engineInfo?.version,
                executionEnabled: connection!.executionAllowed
            };
            try {
                const context = await connection!.projectContext();
                status.projectId = context.project.id;
                status.projectName = context.project.name;
                status.tools = (await connection!.listTools()).map((tool) => tool.name);
            } catch (error) {
                status.error = error instanceof Error ? error.message : String(error);
            }
            return status;
        },
        refresh: async () => {
            await chat!.refreshAll(false);
            await refreshWorkbench();
        },
        refreshWorkbench,
        startMission: (input: StartMissionInput) => chat!.startMission(input, true),
        selectMission: (missionId: number) => chat!.selectMission(missionId),
        getMissionDetail: (missionId: number) => connection!.missionDetail(missionId),
        getCandidateDiff: (missionId: number) => connection!.candidateDiff(missionId),
        cancelMission: (missionId: number) => chat!.cancelMission(missionId, true),
        resumeMission: (missionId: number) => chat!.resumeMission(missionId, true),
        attachPaths: (paths: string[]) => chat!.attachPaths(paths),
        attachText: (text: string, name: string) => chat!.attachText(text, name),
        fetchUrl: (url: string, confirmed = true) => chat!.fetchUrl(url, confirmed),
        loadHistory: () => chat!.loadHistory(),
        setChatModel: (route: string) => chat!.setChatModel(route)
    };

    context.subscriptions.push(
        vscode.commands.registerCommand('nlCodingAgent.startChat', async () => {
            await revealChat('chat');
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('nlCodingAgent.showMissions', async () => {
            await revealChat('missions');
            await chat!.refreshMissions();
            await chat!.refreshAll(false);
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('nlCodingAgent.showEngineSettings', async () => {
            await revealChat('engine');
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('nlCodingAgent.startMission', async () => {
            try {
                await revealChat('chat');
                await connection!.connect();
                const settings = await connection!.engineSettings(true);
                const goal = await vscode.window.showInputBox({
                    title: 'NL Coder — new mission',
                    prompt: 'Describe the code change. Include exact file paths so the engine can scope the candidate.',
                    placeHolder: 'In src/calc.py add sub(a, b) returning a - b. Preserve add and all existing tests.',
                    ignoreFocusOut: true
                });
                if (!goal || !goal.trim()) {
                    return;
                }
                const developerModel = await pickModel(
                    settings, 'developer', settings.mission_defaults.developer_model
                );
                if (!developerModel) {
                    return;
                }
                const reviewerModel = await pickModel(
                    settings, 'reviewer', settings.mission_defaults.reviewer_model
                );
                if (!reviewerModel) {
                    return;
                }
                await chat!.startMission({ goal: goal.trim(), developerModel, reviewerModel }, false);
            } catch (error) {
                const message = error instanceof Error ? error.message : String(error);
                output?.appendLine('[start-mission] ' + message);
                void vscode.window.showErrorMessage('NL Coder: ' + message);
            }
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('nlCodingAgent.openHome', async () => {
            await home?.openPanel();
            await home?.refresh();
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('nlCodingAgent.openModelHub', async () => {
            await revealChat('engine');
            chat?.postNavigation('engine');
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('nlCodingAgent.openAgents', async () => {
            await revealChat('agents');
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('nlCodingAgent.openStorage', async () => {
            await revealChat('engine');
            chat?.postNavigation('engine');
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('nlCodingAgent.selectMission', async (missionId: number) => {
            await revealChat('missions');
            await chat!.selectMission(Number(missionId));
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('nlCodingAgent.askAboutFile', async () => {
            if (!vscode.window.activeTextEditor) {
                void vscode.window.showInformationMessage('Open a file before asking NL Code about it.');
                return;
            }
            await revealChat('chat');
            await chat!.attachActiveEditor(
                vscode.window.activeTextEditor.selection.isEmpty ? 'file' : 'selection');
            await chat!.focusComposer();
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('nlCodingAgent.askAboutPath', async (uri?: vscode.Uri) => {
            if (!uri || uri.scheme !== 'file') {
                return;
            }
            await revealChat('chat');
            await chat!.attachPaths([uri.fsPath]);
            await chat!.focusComposer();
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('nlCodingAgent.reviewChanges', async () => {
            await revealChat('chat');
            await chat!.focusComposer();
            void vscode.window.showInformationMessage(
                'Ask NL Code to review the current changes; the engine can read Git state through its authorized tools.');
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('nlCodingAgent.restoreTheme', async () => {
            const current = vscode.workspace.getConfiguration('workbench').get<string>('colorTheme');
            if (current !== 'NL Code Dark') {
                void vscode.window.showInformationMessage(
                    'The workbench is not using NL Code Dark; no theme change was made.');
                return;
            }
            const choice = await vscode.window.showWarningMessage(
                'Restore the default VS Code dark theme?',
                { modal: true, detail: 'Only workbench.colorTheme changes. NL Code itself keeps its own webview styling.' },
                'Restore theme');
            if (choice !== 'Restore theme') {
                return;
            }
            await vscode.workspace.getConfiguration('workbench').update(
                'colorTheme', 'Default Dark Modern', vscode.ConfigurationTarget.Global);
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('nlCodingAgent.toggleMissionExecution', async () => {
            await chat!.toggleExecution(false);
        })
    );


    context.subscriptions.push(
        vscode.commands.registerCommand('nlCodingAgent.showStatus', async () => {
            try {
                const status = await api.getStatus();
                output!.show(true);
                output!.appendLine('=== NL Coder backend status ===');
                output!.appendLine(`state: ${status.state}${status.pid ? ` (pid ${status.pid})` : ''}`);
                if (status.engineName) {
                    output!.appendLine(`engine: ${status.engineName} ${status.engineVersion || ''}`.trim());
                }
                if (status.projectId !== undefined) {
                    output!.appendLine(
                        `project: #${status.projectId}${status.projectName ? ' ' + status.projectName : ''} — ${status.projectRoot}`
                    );
                } else {
                    output!.appendLine(`workspace: ${status.projectRoot || '(none open)'}`);
                }
                output!.appendLine(`execution: ${status.executionEnabled ? 'enabled' : 'read-only'}`);
                if (status.tools) {
                    output!.appendLine(`tools (${status.tools.length}): ${status.tools.join(', ')}`);
                }
                if (status.error) {
                    output!.appendLine(`error: ${status.error}`);
                    void vscode.window.showErrorMessage(`NL Coder: ${status.error}`);
                } else {
                    void vscode.window.showInformationMessage(
                        `NL Coding Engine ready — project #${status.projectId}, ${status.tools?.length ?? 0} tools, ` +
                        `${status.executionEnabled ? 'missions enabled' : 'read-only'}.`
                    );
                }
                await chat!.refreshAll(false);
            } catch (error) {
                const message = error instanceof Error ? error.message : String(error);
                output?.appendLine('[status-error] ' + message);
                void vscode.window.showErrorMessage('NL Coder status failed: ' + message);
            }
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('nlCodingAgent.steerChat', async () => {
            const instruction = await vscode.window.showInputBox({
                title: 'Steer NL Chat',
                prompt: 'Instruction applied at the next safe checkpoint (running Chat or mission)',
                ignoreFocusOut: true
            });
            if (!instruction || !instruction.trim()) {
                return;
            }
            try {
                await chat!.steerChat(instruction.trim());
            } catch (error) {
                const message = error instanceof Error ? error.message : String(error);
                void vscode.window.showErrorMessage('NL Coder steering failed: ' + message);
            }
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('nlCodingAgent.stopChat', async () => {
            await chat!.stopChat();
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('nlCodingAgent.reconnect', async () => {
            try {
                await connection!.restart();
                await chat!.refreshAll(false);
                await chat!.announceStatus();
                void vscode.window.showInformationMessage('NL Coder backend reconnected.');
            } catch (error) {
                const message = error instanceof Error ? error.message : String(error);
                output?.appendLine('[reconnect-error] ' + message);
                void vscode.window.showErrorMessage('NL Coder reconnection failed: ' + message);
            }
        })
    );

    context.subscriptions.push(
        vscode.workspace.onDidChangeConfiguration(async (event) => {
            if (event.affectsConfiguration('nlCodingAgent.researchProfile')) {
                const profile = vscode.workspace.getConfiguration('nlCodingAgent')
                    .get<string>('researchProfile', 'manual');
                if (connection!.researchProfile !== profile) {
                    connection!.setResearchProfile(profile);
                    output?.appendLine(`researchProfile changed to ${profile}; restarting engine session`);
                    try {
                        await connection!.restart();
                        await chat!.refreshAll(false);
                    } catch (error) {
                        output?.appendLine('[config-change] ' + String(error));
                    }
                }
            }
            if (!event.affectsConfiguration('nlCodingAgent.allowExecution')) {
                return;
            }
            const enabled = vscode.workspace.getConfiguration('nlCodingAgent').get<boolean>('allowExecution', false);
            if (connection!.executionAllowed === enabled) {
                return;
            }
            connection!.setAllowExecution(enabled);
            output?.appendLine(`allowExecution changed to ${enabled}; restarting engine session`);
            try {
                await connection!.restart();
                await chat!.refreshAll(false);
            } catch (error) {
                output?.appendLine('[config-change] ' + String(error));
            }
        })
    );

    context.subscriptions.push(
        vscode.workspace.onDidChangeWorkspaceFolders(async () => {
            const changed = connection!.setProjectRoot(workspaceRoot());
            if (!changed) {
                return;
            }
            output?.appendLine(`Workspace folder changed; rebinding engine to ${workspaceRoot() || '(none)'}`);
            try {
                await connection!.restart();
                await chat!.refreshAll(false);
                await chat!.announceStatus();
            } catch (error) {
                output?.appendLine('[workspace-change] ' + String(error));
            }
        })
    );

    if (!projectRoot) {
        output.appendLine('No folder is open. The engine binds one project per connection; open a folder first.');
    }

    if (isNlCodeStandalone() && config.get<boolean>('showHomeOnStartup', true)) {
        setTimeout(() => {
            void (async () => {
                try {
                    await connection?.connect();
                    await refreshWorkbench();
                    if (projectRoot) { await chat?.openPanel(); }
                    else { await home?.openPanel(); }
                    await vscode.commands.executeCommand('workbench.view.explorer');
                    await chat?.focusComposer();
                } catch (error) {
                    output?.appendLine('[startup-home] ' + String(error));
                }
            })();
        }, 1200);
    }
    return api;
}

export async function deactivate(): Promise<void> {
    try {
        chat?.dispose();
        if (connection) {
            await connection.close();
        }
    } catch (error) {
        console.error('NL Coder shutdown failed', error);
    } finally {
        connection = undefined;
        chat = undefined;
    }
}
