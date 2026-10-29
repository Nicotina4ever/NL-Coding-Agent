/**
 * Activation for the NL Coding Agent VS Code frontend.
 *
 * The extension is a thin client: it locates the existing engine installation,
 * opens one MCP stdio session bound to the active workspace folder, exposes the
 * NL Chat webview, and releases the session on deactivation.
 */
import * as vscode from 'vscode';
import { EngineConnection } from './backend';
import { ChatProvider } from './chatProvider';

export interface StatusReport {
    state: string;
    pid?: number;
    projectRoot: string;
    engineName?: string;
    engineVersion?: string;
    projectId?: number;
    projectName?: string;
    tools?: string[];
    error?: string;
}

export interface NlCodingAgentApi {
    connection: EngineConnection;
    chat: ChatProvider;
    connect(): Promise<void>;
    shutdown(): Promise<void>;
    getStatus(): Promise<StatusReport>;
}

let connection: EngineConnection | undefined;
let chat: ChatProvider | undefined;
let output: vscode.OutputChannel | undefined;

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

export async function activate(context: vscode.ExtensionContext): Promise<NlCodingAgentApi> {
    output = vscode.window.createOutputChannel('NL Coding Agent');
    context.subscriptions.push(output);
    output.appendLine('NL Coding Agent extension activated.');

    const config = vscode.workspace.getConfiguration('nlCodingAgent');
    const timeoutSeconds = Math.max(30, config.get<number>('requestTimeoutSeconds', 180));
    const timeoutMs = timeoutSeconds * 1000;
    const engineRoot = config.get<string>('engineRoot', '');
    const pythonPath = config.get<string>('pythonPath', '');
    const projectRoot = workspaceRoot();

    connection = new EngineConnection({
        engineRoot,
        pythonPath,
        extensionPath: context.extensionUri.fsPath,
        projectRoot,
        env: engineEnvironment(),
        requestTimeoutMs: timeoutMs,
        log: (line: string) => output?.appendLine(line)
    });
    chat = new ChatProvider(context.extensionUri, connection, output, timeoutMs);

    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider(ChatProvider.viewType, chat, {
            webviewOptions: { retainContextWhenHidden: true }
        })
    );

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
                engineVersion: connection!.engineInfo?.version
            };
            try {
                const context = await connection!.projectContext();
                status.projectId = context.project.id;
                status.projectName = context.project.name;
                status.tools = (await connection!.listTools()).map(tool => tool.name);
            } catch (error) {
                status.error = error instanceof Error ? error.message : String(error);
            }
            return status;
        }
    };

    context.subscriptions.push(
        vscode.commands.registerCommand('nlCodingAgent.startChat', async () => {
            await vscode.commands.executeCommand('workbench.view.extension.nlCodingAgent');
            await vscode.commands.executeCommand('nlCodingAgent.chat.focus');
            await chat!.focusComposer();
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('nlCodingAgent.showStatus', async () => {
            try {
                const status = await api.getStatus();
                output!.show(true);
                output!.appendLine('=== NL Coding Agent backend status ===');
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
                if (status.tools) {
                    output!.appendLine(`tools (${status.tools.length}): ${status.tools.join(', ')}`);
                }
                if (status.error) {
                    output!.appendLine(`error: ${status.error}`);
                    void vscode.window.showErrorMessage(`NL Coding Agent: ${status.error}`);
                } else {
                    void vscode.window.showInformationMessage(
                        `NL Coding Engine ready — project #${status.projectId}, ${status.tools?.length ?? 0} tools.`
                    );
                }
                await chat!.announceStatus();
            } catch (error) {
                const message = error instanceof Error ? error.message : String(error);
                output?.appendLine('[status-error] ' + message);
                void vscode.window.showErrorMessage('NL Coding Agent status failed: ' + message);
            }
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('nlCodingAgent.reconnect', async () => {
            try {
                await connection!.restart();
                await chat!.announceStatus();
                void vscode.window.showInformationMessage('NL Coding Agent backend reconnected.');
            } catch (error) {
                const message = error instanceof Error ? error.message : String(error);
                output?.appendLine('[reconnect-error] ' + message);
                void vscode.window.showErrorMessage('NL Coding Agent reconnection failed: ' + message);
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
        if (connection) {
            await connection.close();
        }
    } catch (error) {
        console.error('NL Coding Agent shutdown failed', error);
    } finally {
        connection = undefined;
        chat = undefined;
    }
}
