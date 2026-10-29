/**
 * Reusable connection to the existing NL Coding Engine MCP server.
 *
 * The extension never owns models, missions, permissions or persistence: it
 * spawns `nl_agent.py mcp serve --project <workspace folder>` and speaks the
 * Model Context Protocol over stdio using the official TypeScript SDK.
 *
 * This module deliberately has no dependency on the `vscode` module so the
 * same connection code can be reused by a future standalone Code - OSS build
 * and exercised from plain Node integration tests.
 */
import * as fs from 'fs';
import * as path from 'path';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import type { Tool } from '@modelcontextprotocol/sdk/types.js';

const DEFAULT_TIMEOUT_MS = 180_000;
const CONNECT_TIMEOUT_MS = 60_000;
const LIST_TOOLS_TIMEOUT_MS = 30_000;

/** Environment variables the engine reads for data/workspace/model overrides. */
const ENGINE_ENV_KEYS = ['NL_DATA_DIR', 'NL_WORKSPACE_DIR', 'NL_MODELS_CONFIG', 'NL_ENGINE_ROOT'] as const;

export type ConnectionState = 'idle' | 'connecting' | 'ready' | 'failed' | 'closed';

export class EngineError extends Error {
    constructor(readonly code: string, message: string) {
        super(message);
        this.name = 'EngineError';
    }
}

export interface EngineLocation {
    engineRoot: string;
    pythonPath: string;
    nlAgentPath: string;
}

export interface EngineConnectionOptions {
    /** Explicit engine folder (setting or NL_ENGINE_ROOT). Empty means: resolve from the extension location. */
    engineRoot?: string;
    /** Optional python.exe override. */
    pythonPath?: string;
    /** Directory of the installed extension (used only as a search start point). */
    extensionPath?: string;
    /** Active workspace folder; the engine binds exactly one project per process. */
    projectRoot?: string;
    /** Extra environment values merged over the inherited process environment. */
    env?: Record<string, string>;
    requestTimeoutMs?: number;
    log?: (line: string) => void;
}

export interface ProjectInfo {
    id: number;
    name?: string;
    root: string;
    [key: string]: unknown;
}

export interface ProjectContext {
    project: ProjectInfo;
    execution_enabled?: boolean;
    engine?: string;
    state?: string;
}

export interface ConverseMessage {
    role: string;
    content: string;
    [key: string]: unknown;
}

export interface ConverseResult {
    ok?: boolean;
    reply?: string;
    messages?: ConverseMessage[];
    error?: { type?: string; message?: string };
    tool_activity?: string;
    [key: string]: unknown;
}

export interface AttachmentInput {
    name?: string;
    extracted_text?: string;
}

interface ToolCallPayload {
    content?: Array<{ type?: string; text?: string }>;
    structuredContent?: unknown;
    isError?: boolean;
}

function isFile(candidate: string): boolean {
    try {
        return fs.statSync(candidate).isFile();
    } catch {
        return false;
    }
}

function dedupe(values: string[]): string[] {
    const seen = new Set<string>();
    const result: string[] = [];
    for (const value of values) {
        const key = value.toLowerCase();
        if (seen.has(key)) {
            continue;
        }
        seen.add(key);
        result.push(value);
    }
    return result;
}

/**
 * Resolve the engine installation independently of the project the user opens.
 *
 * The engine is a separate installation (repository checkout or bundled app),
 * never a path inside the user's project. Resolution order:
 *   1. explicit setting / NL_ENGINE_ROOT
 *   2. this extension's own directory and its parents (repository or bundle layout)
 */
export function resolveEngineLocation(options: EngineConnectionOptions): EngineLocation {
    const explicit = (options.engineRoot || '').trim();
    if (explicit) {
        // An explicit installation path is authoritative: never silently fall
        // back to a different engine, so a misconfiguration is visible.
        const root = path.resolve(explicit);
        const pythonPath = (options.pythonPath || '').trim()
            ? path.resolve(options.pythonPath as string)
            : path.join(root, 'python', 'python.exe');
        const nlAgentPath = path.join(root, 'nl_agent.py');
        if (isFile(nlAgentPath) && isFile(pythonPath)) {
            return { engineRoot: root, pythonPath, nlAgentPath };
        }
        throw new EngineError(
            'engine-invalid',
            `The configured NL engine folder is not a usable installation: ${root}. ` +
            'Expected nl_agent.py and python\\python.exe inside it.'
        );
    }
    const candidates: string[] = [];
    const start = options.extensionPath ? path.resolve(options.extensionPath) : path.resolve(__dirname, '..');
    let directory = start;
    for (let depth = 0; depth < 5; depth += 1) {
        candidates.push(directory);
        const parent = path.dirname(directory);
        if (parent === directory) {
            break;
        }
        directory = parent;
    }
    const attempted: string[] = [];
    for (const root of dedupe(candidates)) {
        const pythonPath = (options.pythonPath || '').trim()
            ? path.resolve(options.pythonPath as string)
            : path.join(root, 'python', 'python.exe');
        const nlAgentPath = path.join(root, 'nl_agent.py');
        attempted.push(root);
        if (isFile(nlAgentPath) && isFile(pythonPath)) {
            return { engineRoot: root, pythonPath, nlAgentPath };
        }
    }
    throw new EngineError(
        'engine-not-found',
        'Could not locate the NL Coding Engine installation. Searched: ' + attempted.join('; ') +
        '. Set "nlCodingAgent.engineRoot" (or NL_ENGINE_ROOT) to the folder that contains ' +
        'nl_agent.py and python\\python.exe.'
    );
}

function collectEnvironment(overrides?: Record<string, string>): Record<string, string> {
    const env: Record<string, string> = {};
    for (const key of ENGINE_ENV_KEYS) {
        const value = (overrides && overrides[key]) || process.env[key];
        if (value) {
            env[key] = value;
        }
    }
    if (overrides) {
        for (const [key, value] of Object.entries(overrides)) {
            env[key] = value;
        }
    }
    return env;
}

function contentText(payload: ToolCallPayload): string {
    const blocks = payload.content || [];
    return blocks
        .map(block => (typeof block.text === 'string' ? block.text : ''))
        .filter((text): text is string => text.length > 0)
        .join('\n');
}

/**
 * One reusable client/child-process pair bound to one project.
 *
 * `connect()` is idempotent and safe to call concurrently. `close()` asks the
 * SDK transport to end stdin, which lets the Python server exit cleanly; the
 * transport escalates to SIGTERM/SIGKILL if needed.
 */
export class EngineConnection {
    state: ConnectionState = 'idle';
    projectRoot: string;

    private client: Client | undefined;
    private transport: StdioClientTransport | undefined;
    private connecting: Promise<void> | undefined;
    private tools: Tool[] = [];
    private serverInfo: { name?: string; version?: string } | undefined;
    private lastError: string | undefined;
    private readonly timeoutMs: number;
    private readonly log: (line: string) => void;

    constructor(private readonly options: EngineConnectionOptions) {
        this.projectRoot = options.projectRoot || '';
        this.timeoutMs = options.requestTimeoutMs || DEFAULT_TIMEOUT_MS;
        this.log = options.log || (() => undefined);
    }

    /** PID of the spawned Python engine, while connected. */
    get childPid(): number | undefined {
        const pid = this.transport?.pid;
        return typeof pid === 'number' ? pid : undefined;
    }

    get engineInfo(): { name?: string; version?: string } | undefined {
        return this.serverInfo;
    }

    get lastErrorMessage(): string | undefined {
        return this.lastError;
    }

    get engineLocation(): EngineLocation | undefined {
        try {
            return resolveEngineLocation({ ...this.options, projectRoot: this.projectRoot });
        } catch {
            return undefined;
        }
    }

    setProjectRoot(root: string): boolean {
        const next = (root || '').trim();
        if (next === this.projectRoot) {
            return false;
        }
        this.projectRoot = next;
        return true;
    }

    async connect(): Promise<void> {
        if (this.state === 'ready' && this.client) {
            return;
        }
        if (this.connecting) {
            return this.connecting;
        }
        this.connecting = this.doConnect().finally(() => {
            this.connecting = undefined;
        });
        return this.connecting;
    }

    private async doConnect(): Promise<void> {
        if (this.state === 'closed') {
            throw new EngineError('closed', 'The engine connection has been closed.');
        }
        if (!this.projectRoot) {
            throw new EngineError(
                'no-workspace',
                'Open a folder before using NL Chat: the engine binds one project per connection.'
            );
        }
        this.state = 'connecting';
        this.lastError = undefined;
        const location = resolveEngineLocation({ ...this.options, projectRoot: this.projectRoot });
        const env = collectEnvironment(this.options.env);
        this.log(`starting engine: "${location.pythonPath}" "${location.nlAgentPath}" mcp serve --project "${this.projectRoot}"`);
        let client: Client | undefined;
        let transport: StdioClientTransport | undefined;
        try {
            transport = new StdioClientTransport({
                command: location.pythonPath,
                args: [location.nlAgentPath, 'mcp', 'serve', '--project', this.projectRoot],
                cwd: location.engineRoot,
                env,
                stderr: 'pipe'
            });
            transport.stderr?.on('data', (chunk: Buffer | string) => {
                for (const line of chunk.toString().split(/\r?\n/)) {
                    if (line.trim()) {
                        this.log('engine: ' + line);
                    }
                }
            });
            client = new Client(
                { name: 'nl-coding-agent-vscode', version: '0.1.0' },
                { capabilities: {} }
            );
            await client.connect(transport, { timeout: CONNECT_TIMEOUT_MS });
            const listed = await client.listTools(undefined, { timeout: LIST_TOOLS_TIMEOUT_MS });
            this.client = client;
            this.transport = transport;
            this.tools = listed.tools || [];
            this.serverInfo = client.getServerVersion() as { name?: string; version?: string } | undefined;
            this.state = 'ready';
            this.log(
                `engine ready: ${this.serverInfo?.name || 'unknown'} ${this.serverInfo?.version || ''} · ` +
                `${this.tools.length} tools · pid ${transport.pid ?? '?'}`
            );
        } catch (error) {
            this.state = 'failed';
            this.lastError = error instanceof Error ? error.message : String(error);
            try {
                if (client) {
                    await client.close();
                }
            } catch (closeError) {
                this.log('engine cleanup after failure: ' + String(closeError));
            }
            if (error instanceof EngineError) {
                throw error;
            }
            throw new EngineError('connect-failed', this.lastError || 'Failed to connect to the NL Coding Engine.');
        }
    }

    private async disposeResources(): Promise<void> {
        const client = this.client;
        this.client = undefined;
        this.transport = undefined;
        this.tools = [];
        if (client) {
            try {
                await client.close();
            } catch (error) {
                this.log('engine close error: ' + String(error));
            }
        }
    }

    /** Close the MCP session and release the Python child process. */
    async close(): Promise<void> {
        this.state = 'closed';
        await this.disposeResources();
    }

    /** Drop the current session and start a new one (workspace folder changed, manual retry). */
    async restart(): Promise<void> {
        await this.disposeResources();
        this.state = 'idle';
        this.serverInfo = undefined;
        this.lastError = undefined;
        await this.connect();
    }

    async listTools(): Promise<Tool[]> {
        await this.connect();
        return this.tools;
    }

    private async requiredClient(): Promise<Client> {
        await this.connect();
        if (!this.client) {
            throw new EngineError('not-connected', 'The NL Coding Engine is not connected.');
        }
        return this.client;
    }

    private async callTool(
        name: string,
        args: Record<string, unknown>,
        timeoutMs?: number
    ): Promise<ToolCallPayload> {
        const client = await this.requiredClient();
        let raw: unknown;
        try {
            raw = await client.callTool({ name, arguments: args }, undefined, {
                timeout: timeoutMs || this.timeoutMs
            });
        } catch (error) {
            const detail = error instanceof Error ? error.message : String(error);
            this.lastError = detail;
            throw new EngineError('tool-request-failed', `Calling "${name}" failed: ${detail}`);
        }
        if (raw && typeof raw === 'object' && 'toolResult' in (raw as Record<string, unknown>)) {
            throw new EngineError('tool-result-unsupported', `Tool "${name}" returned a compatibility result shape.`);
        }
        const payload = raw as ToolCallPayload;
        if (payload.isError) {
            const text = contentText(payload);
            throw new EngineError('tool-error', text || `The engine rejected "${name}".`);
        }
        return payload;
    }

    /** Call an engine tool whose result is a JSON object serialized into a text block. */
    async callJson<T>(name: string, args: Record<string, unknown>, timeoutMs?: number): Promise<T> {
        const payload = await this.callTool(name, args, timeoutMs);
        const text = contentText(payload);
        if (!text) {
            throw new EngineError('empty-result', `Tool "${name}" returned no text content.`);
        }
        try {
            return JSON.parse(text) as T;
        } catch {
            throw new EngineError('invalid-json', `Tool "${name}" returned content that is not JSON.`);
        }
    }

    /** Identify the project the engine process is bound to. */
    async projectContext(): Promise<ProjectContext> {
        const context = await this.callJson<ProjectContext>('project_context', {}, LIST_TOOLS_TIMEOUT_MS);
        if (!context || typeof context !== 'object' || !context.project ||
            typeof context.project.id !== 'number' || typeof context.project.root !== 'string') {
            throw new EngineError('invalid-context', 'project_context returned an unexpected shape.');
        }
        return context;
    }

    /**
     * One chat turn through the existing backend conversation service.
     * `projectId` must be the id reported by project_context for this process:
     * the server validates it against the project it was started for.
     */
    async converse(
        projectId: number,
        text: string,
        attachments: AttachmentInput[] = [],
        timeoutMs?: number
    ): Promise<ConverseResult> {
        if (!Number.isInteger(projectId) || projectId <= 0) {
            throw new EngineError('invalid-project', 'A valid project id from project_context is required.');
        }
        const message = String(text || '').trim();
        if (!message) {
            throw new EngineError('empty-message', 'The message is empty.');
        }
        const result = await this.callJson<ConverseResult>(
            'nlc_converse',
            { project_id: projectId, text: message, attachments, history: [] },
            timeoutMs || this.timeoutMs
        );
        if (!result || result.ok !== true || typeof result.reply !== 'string') {
            const detail = (result && (result.reply || (result.error && result.error.message))) ||
                'The engine could not produce a reply.';
            throw new EngineError('chat-failed', detail);
        }
        return result;
    }
}
