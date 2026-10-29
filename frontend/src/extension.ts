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
    connect(): Promise<void>;
    shutdown(): Promise<void>;
    getStatus(): Promise<StatusReport>;
    refresh(): Promise<void>;
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
let output: vscode.OutputChannel | undefined;
let timeoutMs = 180000;

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

export async function activate(context: vscode.ExtensionContext): Promise<NlCodingAgentApi> {
    output = vscode.window.createOutputChannel('NL Coder');
    context.subscriptions.push(output);
    output.appendLine('NL Coder extension activated.');

    const config = vscode.workspace.getConfiguration('nlCodingAgent');
    const timeoutSeconds = Math.max(30, config.get<number>('requestTimeoutSeconds', 180));
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

    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider(ChatProvider.viewType, chat, {
            webviewOptions: { retainContextWhenHidden: true }
        })
    );

    const revealChat = async (tab?: 'chat' | 'missions' | 'engine') => {
        await vscode.commands.executeCommand('workbench.view.extension.nlCodingAgent');
        await vscode.commands.executeCommand('nlCodingAgent.chat.focus');
        if (tab) {
            chat?.postNavigation(tab);
        }
        await chat?.focusComposer();
    };

    const api: NlCodingAgentApi = {
        connection,
        chat,
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
        },
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
