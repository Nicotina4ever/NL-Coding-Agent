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
    /** Start the MCP server with --allow-execution so mission start/cancel is permitted. */
    allowExecution?: boolean;
    /** Owner-selected research auto-review profile (manual | trusted-auto-review). */
    researchProfile?: string;
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
    tool_trace?: Array<{ tool?: string; status?: string; [key: string]: unknown }>;
    route?: ChatRoute;
    [key: string]: unknown;
}

export interface ChatQueueItem {
    id: string;
    text: string;
    attachment_ids?: number[];
    mode?: 'queue' | 'steer';
    created_at?: number;
}

export interface ChatQueueResult {
    ok: boolean;
    items?: ChatQueueItem[];
    count?: number;
    item?: ChatQueueItem;
    removed?: string;
    [key: string]: unknown;
}

export interface ChatSession {
    id: string;
    project_id: number;
    title: string;
    archived_at?: string | null;
    created_at?: string;
    updated_at?: string;
    message_count?: number;
}

export interface ChatSessionsResult {
    ok: boolean;
    sessions: ChatSession[];
}

export interface GenerationParametersResult {
    effective: Record<string, number | string | boolean>;
    configured: Array<{
        id?: number;
        scope: string;
        provider_id: string;
        model_name: string;
        role: string;
        params: Record<string, number | string | boolean>;
        updated_at?: string;
    }>;
}

export interface ModelCapabilityProbe {
    model: string;
    provider_id: string;
    tool_calling: string;
    structured_output: string;
    patch_quality: string;
    patch_score: number;
    capabilities: Record<string, QueryableCapability>;
}

export interface QueryableCapability {
    capability: string;
    state: string;
    metadata?: Record<string, unknown>;
    [key: string]: unknown;
}

export interface StorageItem {
    id: string;
    category: string;
    path: string;
    bytes: number;
    files: number;
    deletable: boolean;
    reason: string;
}

export interface StorageScanResult {
    root: string;
    data_root: string;
    items: StorageItem[];
    total_bytes: number;
    never_delete: string[];
}

export interface AutonomySettings {
    ok: boolean;
    mode: string;
    max_missions_per_run: number;
    max_attempts_per_requirement: number;
    max_wall_time_s: number;
    mission_wall_time_s: number;
    pipeline: string;
    modes?: string[];
    [key: string]: unknown;
}

export interface AttachmentInput {
    name?: string;
    extracted_text?: string;
}

export interface AttachmentView {
    id: number;
    project_id: number;
    name: string;
    kind: string;
    mime: string;
    size_bytes: number;
    sha256?: string;
    source?: string;
    extraction_status: string;
    text_chars: number;
    has_text: boolean;
    metadata: Record<string, unknown>;
    error?: string | null;
    created_at?: string;
    preview?: string;
    preview_truncated?: boolean;
}

export interface AttachmentIngestResult {
    ok: boolean;
    attachments: AttachmentView[];
    errors: Array<{ name?: string; error?: string; code?: string }>;
    total_bytes: number;
    limits: Record<string, number>;
}

export interface HistoryAttachment {
    id: number;
    name: string;
    kind: string;
    mime: string;
    size_bytes: number;
    extraction_status: string;
    text_chars: number;
    has_text: boolean;
    error?: string | null;
}

export interface HistoryMessage {
    index: number;
    role: string;
    content: string;
    content_truncated?: boolean;
    created_at?: string;
    attachments?: HistoryAttachment[];
    model?: string;
    provider_id?: string;
    automatic?: boolean;
    run_id?: string;
    tool_activity?: boolean;
}

export interface ChatHistoryResult {
    ok: boolean;
    project_id: number;
    thread: string;
    count: number;
    offset: number;
    returned: number;
    has_more: boolean;
    messages: HistoryMessage[];
}

export interface ResearchFetchResult {
    ok: boolean;
    outcome?: string;
    capability?: string;
    reason?: string;
    url?: string;
    title?: string;
    text?: string;
    text_truncated?: boolean;
    metadata?: Record<string, unknown>;
    provenance?: Record<string, unknown>;
    redirects?: string[];
    source_id?: number;
    citation_id?: number;
    untrusted: boolean;
    injection_warnings?: unknown[];
    offline?: boolean;
    permission_needed?: unknown;
    denied?: boolean;
    error?: unknown;
}

export interface ChatRoute {
    provider_id: string;
    model: string;
    requested_spec: string;
    automatic: boolean;
}

export interface BackgroundJob {
    id: string;
    label: string;
    argv: string[];
    status: string;
    exit_code?: number | null;
    started_at?: number;
    pid?: number | null;
    [key: string]: unknown;
}

export interface CustomAgent {
    id?: string;
    name: string;
    provider?: string;
    model?: string;
    role?: string;
    instructions?: string;
    tools?: string[];
    permissions?: string[];
    enabled?: boolean;
    kind?: string;
    [key: string]: unknown;
}

export interface EngineSettings {
    schema_version: number;
    project: { id: number; root: string };
    execution_enabled: boolean;
    models: {
        config_path: string;
        config_exists: boolean;
        ollama: Record<string, unknown>;
        providers: Array<{
            provider_id: string;
            kind: string;
            label: string;
            base_url: string;
            enabled: boolean;
            api_key_env?: string;
        }>;
        roles: Record<string, { model?: string; temperature?: number; enabled?: boolean }>;
        chat_role: string;
        chat_default_spec: string;
        cloud_escalation_enabled: boolean;
        discovered: null | {
            reachable?: boolean;
            errors?: string[];
            providers: Array<{
                provider_id: string;
                label: string;
                reachable: boolean;
                error?: string;
                elapsed_ms?: number;
                models: Array<{
                    name: string;
                    size_gb?: number;
                    loaded?: boolean;
                    family?: string;
                    capabilities?: string[];
                }>;
            }>;
        };
    };
    mission_defaults: { developer_model: string; reviewer_model: string; debug_model: string };
    research?: {
        profile: string;
        status?: string;
        offline?: boolean;
        network_configured?: boolean;
        network_granted?: boolean;
        permission_guidance?: string;
    };
    agents: {
        roles: Array<{ role: string; model: string; kind: string; note?: string }>;
        custom_agents: CustomAgent[];
    };
    permissions: {
        scopes: string[];
        policy: Record<string, boolean>;
        cloud_escalation_enabled?: boolean;
        error?: string;
    };
    runtime: Record<string, unknown>;
}

export interface MissionRow {
    id: number;
    project_id: number;
    title: string;
    goal: string;
    status: string;
    created_at?: string;
    updated_at?: string;
    started_at?: string | null;
    finished_at?: string | null;
    result_summary?: string | null;
    review_verdict?: string | null;
    diff_stat?: string | null;
    changed_paths?: string | string[] | null;
    staging_dir?: string | null;
    harness_version?: number | null;
    promotion_status?: string | null;
    resume_count?: number;
    archived_at?: string | null;
}

export interface MissionProgress {
    total: number;
    completed: number;
    failed: number;
    running: number;
    pending: number;
    percent: number;
}

export interface MissionTask {
    id: number;
    title: string;
    status: string;
    agent_role: string;
    attempts?: number;
    last_error?: string | null;
    depends_on?: number[];
    write_paths?: string[];
    created_at?: string;
    started_at?: string | null;
    finished_at?: string | null;
}

export interface MissionHandoff {
    id: number;
    from_role: string;
    to_role: string;
    summary: string;
    created_at?: string;
    payload: Record<string, unknown>;
}

export interface VerificationRun {
    id: number;
    task_id?: number | null;
    command: string;
    exit_code: number;
    passed: boolean;
    created_at?: string;
    stdout?: string;
    stderr?: string;
}

export interface MissionAttempt {
    id: number;
    task_id?: number;
    task_title?: string;
    agent_role?: string;
    status?: string;
    started_at?: string;
    finished_at?: string;
    error?: string;
    output?: string;
    metadata?: {
        model?: string;
        provider?: string;
        duration_s?: number | null;
        tools_used?: string[];
        usage?: Record<string, unknown>;
        [key: string]: unknown;
    };
}

export interface MissionModelBinding {
    role?: string;
    provider_id?: string;
    model_name?: string;
    source?: string;
    config_sha256?: string;
    [key: string]: unknown;
}

export interface MissionExecutionError {
    id?: number;
    kind?: string;
    record_key?: string;
    created_at?: string;
    source?: string | null;
    method?: string | null;
    flow_id?: string | null;
    task_id?: number | null;
    exception_type?: string | null;
    message?: string | null;
    traceback?: string | null;
    traceback_truncated?: boolean;
    pid?: number | null;
    reason?: string | null;
    previous_status?: string | null;
    new_status?: string | null;
}

export interface MissionToolInvocation {
    id?: number;
    tool_name?: string;
    source?: string;
    status?: string;
    role?: string | null;
    model?: string | null;
    arguments?: unknown;
    result?: unknown;
    error?: string | null;
    duration_ms?: number | null;
    call_id?: string | null;
    created_at?: string;
}

export interface MissionDetail {
    mission: MissionRow;
    tasks: MissionTask[];
    handoffs: MissionHandoff[];
    verification_runs: VerificationRun[];
    attempts: MissionAttempt[];
    execution_errors?: MissionExecutionError[];
    tool_invocations?: MissionToolInvocation[];
    model_bindings?: Record<string, MissionModelBinding>;
    progress: MissionProgress;
}

export interface CandidateDiff {
    ok: boolean;
    mission_id?: number;
    diff?: string;
    changed_paths?: string[];
    stat?: string;
    status?: string;
    verdict?: string | null;
    promotion_status?: string | null;
    retained?: boolean;
    error?: string;
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

    /** Whether the spawned server is allowed to start/cancel missions. */
    get executionAllowed(): boolean {
        return Boolean(this.options.allowExecution);
    }

    /** Update the execution flag; call restart() to spawn the server with the new arg. */
    setAllowExecution(value: boolean): void {
        this.options.allowExecution = Boolean(value);
    }

    get researchProfile(): string {
        return this.options.researchProfile === 'trusted-auto-review' ? 'trusted-auto-review' : 'manual';
    }

    setResearchProfile(value: string): void {
        this.options.researchProfile = value === 'trusted-auto-review' ? 'trusted-auto-review' : 'manual';
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
                'Open a folder before using NL Coder: the engine binds one project per connection.'
            );
        }
        this.state = 'connecting';
        this.lastError = undefined;
        const location = resolveEngineLocation({ ...this.options, projectRoot: this.projectRoot });
        const env = collectEnvironment(this.options.env);
        const args = [location.nlAgentPath, 'mcp', 'serve', '--project', this.projectRoot];
        if (this.options.allowExecution) {
            args.push('--allow-execution');
        }
        const researchProfile = this.options.researchProfile === 'trusted-auto-review'
            ? 'trusted-auto-review' : 'manual';
        args.push('--research-profile', researchProfile);
        this.log(`starting engine: "${location.pythonPath}" ${args.join(' ')}`);
        let client: Client | undefined;
        let transport: StdioClientTransport | undefined;
        try {
            transport = new StdioClientTransport({
                command: location.pythonPath,
                args,
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
        timeoutMs?: number,
        modelSpec?: string,
        attachmentIds: number[] = [],
        allowCoding = false
    ): Promise<ConverseResult> {
        if (!Number.isInteger(projectId) || projectId <= 0) {
            throw new EngineError('invalid-project', 'A valid project id from project_context is required.');
        }
        const message = String(text || '').trim();
        if (!message) {
            throw new EngineError('empty-message', 'The message is empty.');
        }
        const params: Record<string, unknown> = {
            project_id: projectId,
            text: message,
            attachments: attachmentIds.length ? [] : attachments,
            history: []
        };
        if (attachmentIds.length) {
            params.attachment_ids = attachmentIds.map((value) => Number(value)).filter((value) => Number.isInteger(value) && value > 0);
        }
        if (modelSpec && modelSpec.trim()) {
            params.model_spec = modelSpec.trim();
        }
        if (allowCoding) {
            params.allow_coding = true;
        }
        const result = await this.callJson<ConverseResult>('nlc_converse', params, timeoutMs || this.timeoutMs);
        if (!result || result.ok !== true || typeof result.reply !== 'string') {
            const detail = (result && (result.reply || (result.error && result.error.message))) ||
                'The engine could not produce a reply.';
            throw new EngineError('chat-failed', detail);
        }
        return result;
    }

    /** Ingest explicit files (or text) through the engine attachment pipeline. */
    async attachmentIngest(input: { paths?: string[]; text?: string; name?: string }): Promise<AttachmentIngestResult> {
        const params: Record<string, unknown> = {};
        if (input.paths && input.paths.length) {
            params.paths = input.paths;
        }
        if (input.text) {
            params.text = input.text;
            params.name = input.name || 'pasted-context.txt';
        }
        const result = await this.callJson<AttachmentIngestResult>('attachment_ingest', params, 60_000);
        if (!result || typeof result !== 'object') {
            throw new EngineError('attachment-failed', 'attachment_ingest returned an unexpected shape.');
        }
        return result;
    }

    /** Read one persisted conversation session (default: latest active). */
    async chatHistory(limit = 200, beforeIndex?: number, sessionId?: string): Promise<ChatHistoryResult> {
        const params: Record<string, unknown> = { limit };
        if (beforeIndex !== undefined) {
            params.before_index = beforeIndex;
        }
        if (sessionId) {
            params.session_id = sessionId;
        }
        return this.callJson<ChatHistoryResult>('chat_history', params, 30_000);
    }

    async chatSessions(includeArchived = false): Promise<ChatSessionsResult> {
        return this.callJson<ChatSessionsResult>(
            'chat_sessions', { include_archived: includeArchived }, 30_000);
    }

    async chatSessionCreate(title = 'New conversation'): Promise<{ ok: boolean; session: ChatSession }> {
        return this.callJson<{ ok: boolean; session: ChatSession }>('chat_session_create', { title, approved: true }, 30_000);
    }

    async chatSessionRename(sessionId: string, title: string): Promise<{ ok: boolean; session: ChatSession }> {
        return this.callJson<{ ok: boolean; session: ChatSession }>('chat_session_rename', {
            session_id: sessionId, title, approved: true
        }, 30_000);
    }

    async chatSessionArchive(sessionId: string): Promise<{ ok: boolean; session: ChatSession }> {
        return this.callJson<{ ok: boolean; session: ChatSession }>('chat_session_archive', {
            session_id: sessionId, approved: true
        }, 30_000);
    }

    async chatSessionDelete(sessionId: string): Promise<{ ok: boolean; session: ChatSession }> {
        return this.callJson<{ ok: boolean; session: ChatSession }>('chat_session_delete', {
            session_id: sessionId, approved: true
        }, 30_000);
    }

    async chatSearch(query: string, limit = 100): Promise<{ ok: boolean; messages: Array<Record<string, unknown>> }> {
        return this.callJson<{ ok: boolean; messages: Array<Record<string, unknown>> }>('chat_search', { query, limit }, 30_000);
    }

    async chatCleanup(scope: 'orphaned' | 'archived' = 'orphaned'): Promise<{
        ok: boolean; result: { scope: string; sessions: number; messages: number };
    }> {
        return this.callJson<{
            ok: boolean; result: { scope: string; sessions: number; messages: number };
        }>('chat_cleanup', { scope, approved: true }, 60_000);
    }

    async jobList(): Promise<{ ok: boolean; jobs: BackgroundJob[] }> {
        return this.callJson<{ ok: boolean; jobs: BackgroundJob[] }>('job_list', {}, 30_000);
    }

    async jobOutput(jobId: string): Promise<{
        ok: boolean; job: BackgroundJob; output: string; truncated: boolean;
    }> {
        return this.callJson<{
            ok: boolean; job: BackgroundJob; output: string; truncated: boolean;
        }>('job_output', { job_id: jobId }, 30_000);
    }

    async jobStop(jobId: string): Promise<{ ok: boolean; job: BackgroundJob }> {
        return this.callJson<{ ok: boolean; job: BackgroundJob }>('job_stop', {
            job_id: jobId, approved: true
        }, 30_000);
    }

    async generationParameters(modelName = '', role = '', providerId = 'ollama'): Promise<GenerationParametersResult> {
        return this.callJson<GenerationParametersResult>('generation_parameters', {
            model_name: modelName, role, provider_id: providerId
        }, 30_000);
    }

    async saveGenerationParameters(params: Record<string, number | string | boolean | null>,
                                   scope: 'global' | 'role' | 'model',
                                   modelName = '', role = ''): Promise<{ ok: boolean; saved: Record<string, unknown> }> {
        return this.callJson<{ ok: boolean; saved: Record<string, unknown> }>('save_generation_parameters', {
            parameters: params, scope, model_name: modelName, role,
            provider_id: 'ollama', approved: true
        }, 30_000);
    }

    async saveProviderSettings(providerId: string, settings: {
        enabled?: boolean; baseUrl?: string; label?: string; kind?: string;
        apiKeyEnv?: string;
    }): Promise<{ ok: boolean; provider: string; changes: Record<string, unknown> }> {
        return this.callJson<{ ok: boolean; provider: string; changes: Record<string, unknown> }>('save_provider_settings', {
            provider_id: providerId, enabled: settings.enabled,
            base_url: settings.baseUrl, label: settings.label,
            kind: settings.kind, api_key_env: settings.apiKeyEnv, approved: true
        }, 30_000);
    }

    async saveRoleSettings(role: string, settings: {
        model?: string; temperature?: number;
    }): Promise<{ ok: boolean; role: string; changes: Record<string, unknown> }> {
        return this.callJson<{ ok: boolean; role: string; changes: Record<string, unknown> }>('save_role_settings', {
            role, model: settings.model, temperature: settings.temperature,
            approved: true
        }, 30_000);
    }

    async saveCloudEscalation(enabled: boolean): Promise<{ ok: boolean }> {
        return this.callJson<{ ok: boolean }>('set_cloud_escalation', { enabled, approved: true }, 30_000);
    }

    async savePermissionScope(scope: string, granted: boolean): Promise<{ ok: boolean; permissions: EngineSettings['permissions'] }> {
        return this.callJson<{ ok: boolean; permissions: EngineSettings['permissions'] }>('save_permission_scope', {
            scope, granted, approved: true
        }, 30_000);
    }

    async probeModelCapabilities(model: string, timeoutS = 90): Promise<ModelCapabilityProbe> {
        return this.callJson<ModelCapabilityProbe>('probe_model_capabilities', {
            model, timeout_s: timeoutS, approved: true
        }, Math.max(120_000, timeoutS * 1000 + 30_000));
    }

    async autonomySettings(): Promise<AutonomySettings> {
        return this.callJson<AutonomySettings>('autonomy_settings', {}, 30_000);
    }

    async saveAutonomySettings(input: {
        mode?: string; maxMissions?: number; attempts?: number;
        maxWallTimeS?: number; missionWallTimeS?: number;
    }): Promise<AutonomySettings> {
        return this.callJson<AutonomySettings>('save_autonomy_settings', {
            mode: input.mode, max_missions: input.maxMissions, attempts: input.attempts,
            max_wall_time_s: input.maxWallTimeS,
            mission_wall_time_s: input.missionWallTimeS, approved: true
        }, 30_000);
    }

    async customAgents(): Promise<{ ok: boolean; agents: CustomAgent[] }> {
        return this.callJson<{ ok: boolean; agents: CustomAgent[] }>('custom_agents', {}, 30_000);
    }

    async saveCustomAgent(agent: CustomAgent): Promise<{ ok: boolean; agent: CustomAgent }> {
        return this.callJson<{ ok: boolean; agent: CustomAgent }>('save_custom_agent', {
            agent_id: agent.id,
            name: agent.name,
            provider: agent.provider || 'ollama',
            model: agent.model || '',
            role: agent.role || 'assistant',
            instructions: agent.instructions || '',
            tools: agent.tools || [],
            permissions: agent.permissions || [],
            enabled: agent.enabled !== false,
            approved: true
        }, 30_000);
    }

    async deleteCustomAgent(agentId: string): Promise<{ ok: boolean }> {
        return this.callJson<{ ok: boolean }>('delete_custom_agent', {
            agent_id: agentId, approved: true
        }, 30_000);
    }

    async duplicateCustomAgent(agentId: string, name?: string): Promise<{ ok: boolean; agent: CustomAgent }> {
        return this.callJson<{ ok: boolean; agent: CustomAgent }>('duplicate_custom_agent', {
            agent_id: agentId, name, approved: true
        }, 30_000);
    }

    async mcpServers(): Promise<{ ok: boolean; config: Record<string, unknown> }> {
        return this.callJson<{ ok: boolean; config: Record<string, unknown> }>('mcp_servers', {}, 30_000);
    }

    async saveMcpServers(config: Record<string, unknown>): Promise<{ ok: boolean; servers: string[] }> {
        return this.callJson<{ ok: boolean; servers: string[] }>('save_mcp_servers', { config, approved: true }, 30_000);
    }

    async storageScan(): Promise<StorageScanResult> {
        return this.callJson<StorageScanResult>('storage_scan', {}, 60_000);
    }

    async storagePurge(selectedIds: string[]): Promise<{ ok: boolean; removed: string[]; freed_bytes: number }> {
        return this.callJson<{ ok: boolean; removed: string[]; freed_bytes: number }>('storage_purge', {
            selected_ids: selectedIds, confirm: true, approved: true
        }, 120_000);
    }

    async storageVacuum(): Promise<{ ok: boolean; freed_bytes: number; error?: string }> {
        return this.callJson<{ ok: boolean; freed_bytes: number; error?: string }>('storage_vacuum', { confirm: true, approved: true }, 180_000);
    }

    async chatQueue(): Promise<ChatQueueResult> {
        return this.callJson<ChatQueueResult>('chat_queue', {}, 30_000);
    }

    async chatEnqueue(text: string, attachmentIds: number[] = [], mode: 'queue' | 'steer' = 'queue'): Promise<ChatQueueResult> {
        return this.callJson<ChatQueueResult>('chat_enqueue', {
            text, attachment_ids: attachmentIds, mode
        }, 30_000);
    }

    async chatSteer(text: string): Promise<ChatQueueResult> {
        return this.callJson<ChatQueueResult>('chat_steer', { text }, 30_000);
    }

    async chatQueueRemove(itemId: string): Promise<ChatQueueResult> {
        return this.callJson<ChatQueueResult>('chat_queue_remove', { item_id: itemId }, 30_000);
    }

    async chatQueueReorder(ids: string[]): Promise<ChatQueueResult> {
        return this.callJson<ChatQueueResult>('chat_queue_reorder', { ids }, 30_000);
    }

    async chatCancel(): Promise<Record<string, unknown>> {
        return this.callJson<Record<string, unknown>>('chat_cancel', {}, 30_000);
    }

    async missionSteer(missionId: number, text: string): Promise<Record<string, unknown>> {
        return this.callJson<Record<string, unknown>>('mission_steer', {
            mission_id: missionId, text
        }, 30_000);
    }

    /** Fetch one URL through the existing Research service/permissions. */
    async researchFetch(url: string): Promise<ResearchFetchResult> {
        return this.callJson<ResearchFetchResult>('research_fetch_url', { url }, 120_000);
    }

    /** Read-only engine model/agent/permission configuration (optionally probe local models). */
    async engineSettings(includeModels = false, timeoutS = 2.5): Promise<EngineSettings> {
        return this.callJson<EngineSettings>(
            'engine_settings',
            { include_models: includeModels, timeout_s: timeoutS },
            30_000
        );
    }

    /** Persisted missions of the bound project, newest first. */
    async missionList(options: { includeArchived?: boolean; status?: string; query?: string } = {}): Promise<MissionRow[]> {
        const result = await this.callJson<{ missions?: MissionRow[] }>('mission_list', {
            include_archived: options.includeArchived !== false,
            status: options.status, query: options.query
        }, 30_000);
        return Array.isArray(result.missions) ? result.missions : [];
    }

    async archiveMission(missionId: number): Promise<{ ok: boolean; mission: MissionRow }> {
        return this.callJson<{ ok: boolean; mission: MissionRow }>('archive_mission', { mission_id: missionId, approved: true }, 30_000);
    }

    async unarchiveMission(missionId: number): Promise<{ ok: boolean; mission: MissionRow }> {
        return this.callJson<{ ok: boolean; mission: MissionRow }>('unarchive_mission', { mission_id: missionId, approved: true }, 30_000);
    }

    async deleteMission(missionId: number): Promise<{ ok: boolean; mission: MissionRow }> {
        return this.callJson<{ ok: boolean; mission: MissionRow }>('delete_mission', { mission_id: missionId, approved: true }, 30_000);
    }

    async missionStatus(missionId: number): Promise<MissionRow> {
        return this.callJson<MissionRow>('mission_status', { mission_id: missionId }, 30_000);
    }

    /** Full persisted mission view (tasks, handoffs, attempts, verification runs). */
    async missionDetail(missionId: number): Promise<MissionDetail> {
        const detail = await this.callJson<MissionDetail>('mission_detail', { mission_id: missionId }, 30_000);
        if (!detail || typeof detail !== 'object' || !detail.mission) {
            throw new EngineError('invalid-mission', 'mission_detail returned an unexpected shape.');
        }
        return detail;
    }

    /** Candidate/staged or retained historical diff. `ok:false` is a real answer. */
    async candidateDiff(missionId: number): Promise<CandidateDiff> {
        return this.callJson<CandidateDiff>('candidate_diff', { mission_id: missionId }, 30_000);
    }

    /**
     * Start (or resume) a mission through the existing Supervisor/staging engine.
     * The server only accepts this when it was started with --allow-execution and
     * the explicit approval flag is set, so callers must confirm with the human.
     */
    async startMission(input: {
        goal: string;
        developerModel: string;
        reviewerModel: string;
        resumeMissionId?: number;
    }): Promise<{ mission_id: number; dispatch?: string; task_id?: string }> {
        const goal = String(input.goal || '').trim();
        if (!goal) {
            throw new EngineError('empty-goal', 'The mission objective is empty.');
        }
        if (!input.developerModel || !input.reviewerModel) {
            throw new EngineError('missing-model', 'Exact developer and reviewer model routes are required.');
        }
        const params: Record<string, unknown> = {
            goal,
            developer_model: input.developerModel,
            reviewer_model: input.reviewerModel,
            approved: true
        };
        if (input.resumeMissionId !== undefined) {
            params.resume_mission_id = input.resumeMissionId;
        }
        const result = await this.callJson<{ mission_id?: number; dispatch?: string; task_id?: string }>(
            'start_mission', params, 60_000
        );
        if (!result || typeof result.mission_id !== 'number') {
            throw new EngineError('mission-not-started', 'The engine did not return a mission id.');
        }
        return { ...result, mission_id: result.mission_id };
    }

    /** Request a durable cooperative stop at the next safe checkpoint. */
    async cancelMission(missionId: number): Promise<Record<string, unknown>> {
        return this.callJson<Record<string, unknown>>(
            'cancel_mission', { mission_id: missionId, approved: true }, 30_000
        );
    }
}

