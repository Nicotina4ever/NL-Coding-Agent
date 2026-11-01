/**
 * Webview HTML construction. Kept free of the `vscode` module so it can be
 * syntax- and structure-tested from plain Node.
 *
 * Security: no dynamic or model-generated text is interpolated into the HTML.
 * Only extension-owned resource URIs are inserted, and every dynamic value is
 * escaped. The webview script is an external file allowed by the CSP source
 * instead of inline code, so there is no `'unsafe-inline'` script policy.
 */

export interface WebviewAssets {
    scriptUri: string;
    styleUri: string;
    cspSource: string;
}

/** Escape text for safe interpolation into HTML markup. */
export function escapeHtml(value: string): string {
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

export function buildChatHtml(assets: WebviewAssets): string {
    const contentSecurityPolicy = [
        "default-src 'none'",
        `img-src ${assets.cspSource} data:`,
        `style-src ${assets.cspSource}`,
        `script-src ${assets.cspSource}`,
        `font-src ${assets.cspSource}`,
        "base-uri 'none'",
        "form-action 'none'"
    ].join('; ');

    return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="Content-Security-Policy" content="${escapeHtml(contentSecurityPolicy)}">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="${escapeHtml(assets.styleUri)}">
    <title>NL Coder</title>
</head>
<body>
    <header class="nl-header">
        <div class="nl-header-row">
            <span class="nl-brand">NL Code</span>
            <span id="status" class="nl-status" role="status" aria-live="polite">Starting…</span>
        </div>
        <div class="nl-header-row nl-header-meta">
            <span id="project-badge" class="nl-chip">no project</span>
            <span id="model-badge" class="nl-chip nl-chip-soft">model: —</span>
            <button id="exec-toggle" class="nl-chip nl-chip-button" type="button" title="Toggle mission execution for this engine session">read-only</button>
        </div>
        <nav class="nl-tabs" aria-label="Sections">
            <button type="button" class="nl-tab-button active" data-tab="chat">Chat</button>
            <button type="button" class="nl-tab-button" data-tab="missions">Missions</button>
            <button type="button" class="nl-tab-button" data-tab="agents">Agents</button>
            <button type="button" class="nl-tab-button" data-tab="engine">Settings</button>
        </nav>
    </header>

    <div id="notice" class="nl-notice hidden" role="alert"></div>

    <main class="nl-main">
        <section id="tab-chat" class="nl-tab-panel active">
            <div id="mission-banner" class="nl-mission-banner hidden">
                <div class="nl-mission-banner-head">
                    <span id="banner-title" class="nl-mission-title">Mission</span>
                    <span id="banner-status" class="nl-status-chip">—</span>
                </div>
                <div class="nl-progress" aria-hidden="true"><div id="banner-progress-bar" class="nl-progress-bar"></div></div>
                <div id="banner-counts" class="nl-muted"></div>
                <div class="nl-actions">
                    <button id="btn-banner-stop" type="button">Stop</button>
                    <button id="btn-banner-resume" type="button" class="hidden">Resume</button>
                    <button id="btn-banner-details" type="button">Details</button>
                </div>
            </div>

            <div id="research-card" class="nl-research-card hidden">
                <div class="nl-research-head">
                    <span class="nl-chip nl-chip-soft">UNTRUSTED web page</span>
                    <span id="research-outcome" class="nl-status-chip"></span>
                    <span id="research-title" class="nl-research-title"></span>
                </div>
                <div id="research-url" class="nl-research-url"></div>
                <div id="research-meta" class="nl-muted"></div>
                <pre id="research-text" class="nl-output"></pre>
                <div id="research-warnings" class="nl-warning hidden"></div>
                <div class="nl-actions">
                    <button id="research-use" type="button">Use as chat context</button>
                    <button id="research-dismiss" type="button">Dismiss</button>
                </div>
            </div>

            <div id="messages" class="nl-messages" role="log" aria-live="polite" aria-label="Conversation"></div>

            <div class="nl-session-bar">
                <select id="chat-session" aria-label="Conversation session"></select>
                <button id="session-new" type="button">New</button>
                <button id="session-rename" type="button">Rename</button>
                <button id="session-archive" type="button">Archive</button>
                <button id="session-delete" type="button">Delete</button>
                <button id="session-search" type="button">Search</button>
                <label class="nl-check"><input id="session-archived-toggle" type="checkbox"> archived</label>
            </div>
            <div id="chat-queue" class="nl-queue" aria-label="Persistent chat queue"></div>

            <div id="drop-overlay" class="nl-drop-overlay hidden">Drop workspace files to attach them</div>

            <form id="composer" class="nl-composer" autocomplete="off">
                <div id="context-strip" class="nl-context-strip">
                    <div id="editor-context" class="nl-editor-context"></div>
                    <div id="attachment-chips" class="nl-chips"></div>
                    <div class="nl-context-actions">
                        <button id="attach-files" type="button" title="Attach workspace files">＋ File</button>
                        <button id="attach-current" type="button" title="Attach the active editor content">Current file</button>
                        <button id="attach-selection" type="button" title="Attach the active editor selection">Selection</button>
                    </div>
                </div>

                <div class="nl-composer-shell">
                    <div class="nl-composer-toggle-row">
                        <button id="chat-controls-toggle" type="button" class="nl-collapse-button">▾ model controls</button>
                        <button id="context-toggle" type="button" class="nl-collapse-button">▾ attachments</button>
                    </div>
                    <div id="model-bar" class="nl-model-bar">
                        <label class="nl-field nl-field-small">Provider
                            <select id="provider-select"></select>
                        </label>
                        <label class="nl-field nl-field-small">Model
                            <select id="chat-model"></select>
                        </label>
                        <label class="nl-check"><input id="auto-model" type="checkbox"> Automatic</label>
                        <button id="chat-refresh-models" type="button" title="Probe providers and refresh the model dropdown">↻ models</button>
                        <label class="nl-check" title="Let Chat delegate an explicit coding goal to a verified mission when execution is enabled">
                            <input id="auto-coding" type="checkbox"> Auto-code
                        </label>
                        <span id="model-current" class="nl-muted"></span>
                    </div>

                    <label class="nl-visually-hidden" for="input">Message NL Coder</label>
                    <textarea id="input" rows="3" placeholder="Ask NL Coder…  (/mission &lt;objective&gt; starts a mission)"></textarea>

                    <div class="nl-mission-toggle-row">
                        <button id="mission-fields-toggle" type="button" class="nl-collapse-button hidden">▾ mission model selection</button>
                    </div>
                    <div id="mission-fields" class="nl-field-row hidden">
                        <label class="nl-field">Developer model
                            <select id="dev-model"></select>
                        </label>
                        <label class="nl-field">Reviewer model
                            <select id="reviewer-model"></select>
                        </label>
                    </div>
                    <p id="mission-note" class="nl-hint hidden">The mission runs through the existing Supervisor, staging and verification gates and requires explicit confirmation.</p>

                    <div class="nl-composer-actions">
                        <div class="nl-composer-left">
                            <label class="nl-field nl-field-small">Mode
                                <select id="mode">
                                    <option value="chat">Chat</option>
                                    <option value="mission">Mission</option>
                                </select>
                            </label>
                            <span id="hint" class="nl-hint"></span>
                        </div>
                        <button id="btn-chat-stop" type="button" class="hidden">Stop chat</button>
                        <button id="send" type="submit">Send</button>
                    </div>
                </div>
            </form>
        </section>

        <section id="tab-missions" class="nl-tab-panel">
            <div class="nl-section-head">
                <strong>Persistent missions</strong>
                <span class="nl-actions">
                    <button id="refresh-missions" type="button">Refresh</button>
                </span>
            </div>
            <p class="nl-hint">Only missions belonging to the open project are listed. Switching project switches this list; archived missions remain available under the filter.</p>
            <div class="nl-filter-row">
                <input id="mission-query" type="search" placeholder="Filter title/goal…" aria-label="Mission filter">
                <select id="mission-status-filter" aria-label="Mission status filter">
                    <option value="">all statuses</option>
                    <option value="running">running</option>
                    <option value="pending">pending</option>
                    <option value="completed">completed</option>
                    <option value="failed">failed</option>
                    <option value="blocked">blocked</option>
                    <option value="interrupted">interrupted</option>
                </select>
                <label class="nl-check"><input id="mission-archived-toggle" type="checkbox"> archived</label>
                <button id="mission-apply-filter" type="button">Apply</button>
                <button id="mission-list-toggle" type="button" class="nl-collapse-button">▾ mission list</button>
            </div>
            <div id="mission-list" class="nl-list"></div>
            <div id="mission-detail" class="nl-detail hidden"></div>
        </section>

        <section id="tab-agents" class="nl-tab-panel">
            <div class="nl-section-head">
                <strong>Agents and model assignments</strong>
                <span class="nl-muted">Specialists are engine-owned profiles; every model can serve any role.</span>
            </div>
            <div class="nl-settings-card">
                    <h3>Role model assignment</h3>
                    <div class="nl-filter-row">
                        <select id="role-edit" aria-label="Role to edit">
                            <option value="architect">architect</option>
                            <option value="developer">developer</option>
                            <option value="debugger">debugger</option>
                            <option value="reviewer">reviewer</option>
                            <option value="chat">chat</option>
                        </select>
                        <select id="role-model-edit" aria-label="Role model route"></select>
                        <button id="role-save" type="button">Save role</button>
                    </div>
                    <h3>Specialist agents</h3>
                    <div class="nl-filter-row">
                        <select id="specialist-list" aria-label="Specialist agent to edit"></select>
                        <button id="specialist-new" type="button">New</button>
                        <button id="specialist-generate" type="button" title="Create a recommended team appropriate to the project">Generate team</button>
                        <button id="specialist-duplicate" type="button">Duplicate</button>
                        <button id="specialist-delete" type="button">Delete</button>
                    </div>
                    <div class="nl-filter-row">
                        <input id="specialist-name" type="text" placeholder="agent name" aria-label="Specialist agent name">
                        <select id="specialist-provider" aria-label="Specialist agent provider"></select>
                        <select id="specialist-model" aria-label="Specialist model route"></select>
                        <input id="specialist-role" type="text" placeholder="specialty (e.g. security reviewer)" aria-label="Specialist role">
                    </div>
                    <textarea id="specialist-instructions" rows="3" placeholder="Specialist instructions and boundaries" aria-label="Specialist instructions"></textarea>
                    <div class="nl-filter-row">
                        <input id="specialist-tools" type="text" placeholder="tools: read, edit, terminal" aria-label="Specialist tools">
                        <input id="specialist-permissions" type="text" placeholder="permissions: read-only, project-write" aria-label="Specialist permissions">
                        <label class="nl-check"><input id="specialist-enabled" type="checkbox"> enabled</label>
                        <button id="specialist-save" type="button">Save specialist</button>
                    </div>
            </div>
        </section>

        <section id="tab-engine" class="nl-tab-panel">
            <div class="nl-section-head">
                <strong>Engine settings and Model Hub</strong>
                <span class="nl-actions">
                    <button id="refresh-models" type="button">Probe models</button>
                    <button id="refresh-engine" type="button">Refresh</button>
                </span>
            </div>
            <div class="nl-settings-card">
                <h3>Provider</h3>
                <div class="nl-filter-row">
                    <select id="provider-edit" aria-label="Provider to edit"></select>
                    <label class="nl-check"><input id="provider-enabled" type="checkbox"> enabled</label>
                    <input id="provider-url" type="url" placeholder="http://127.0.0.1:11434" aria-label="Provider URL">
                    <button id="provider-save" type="button">Save provider</button>
                </div>
                <div class="nl-filter-row">
                    <input id="provider-id" type="text" placeholder="new provider id (e.g. lm_studio)" aria-label="Provider id">
                    <select id="provider-kind" aria-label="Provider kind">
                        <option value="openai_compatible">openai_compatible</option>
                        <option value="ollama">ollama</option>
                    </select>
                    <input id="provider-label" type="text" placeholder="label" aria-label="Provider label">
                    <input id="provider-api-key-env" type="text" placeholder="API key env var (optional)" aria-label="API key env var">
                </div>
                <details class="nl-advanced">
                <summary>Advanced generation parameters</summary>
                <div class="nl-filter-row">
                    <select id="generation-scope">
                        <option value="model">model</option>
                        <option value="role">role</option>
                        <option value="global">global</option>
                    </select>
                    <select id="generation-model" aria-label="Generation model"></select>
                    <input id="generation-role" type="text" placeholder="role" aria-label="Generation role">
                </div>
                <div class="nl-filter-row">
                    <input id="generation-temperature" type="number" step="0.01" placeholder="temperature">
                    <input id="generation-top-p" type="number" step="0.01" placeholder="top_p">
                    <input id="generation-top-k" type="number" placeholder="top_k">
                    <input id="generation-min-p" type="number" step="0.01" placeholder="min_p">
                    <input id="generation-repeat" type="number" step="0.01" placeholder="repeat_penalty">
                    <input id="generation-seed" type="number" placeholder="seed">
                    <input id="generation-max" type="number" placeholder="max_tokens">
                    <label class="nl-field">Context
                        <select id="generation-context">
                            <option value="">Application default (Ollama)</option>
                            <option value="4096">4k</option>
                            <option value="8192">8k</option>
                            <option value="16384">16k</option>
                            <option value="32768">32k</option>
                            <option value="65536">64k</option>
                            <option value="131072">128k</option>
                            <option value="262144">256k</option>
                        </select>
                    </label>
                    <button id="generation-save" type="button">Save parameters</button>
                </div>
                </details>
                <h3>Permissions and autonomy</h3>
                <p class="nl-hint"><strong>Mission execution</strong> is the master switch for code-changing missions. Read-only Chat can inspect and plan; enabling execution lets Chat stage a candidate, run verification and ask the reviewer before promotion. Permissions below are narrower grants for read, write, execute, network and cloud. Cloud escalation is opt-in and never runs automatically.</p>
                <div class="nl-filter-row">
                    <select id="permission-scope">
                        <option value="read">read</option>
                        <option value="write">write</option>
                        <option value="execute">execute</option>
                        <option value="network">network</option>
                        <option value="cloud">cloud</option>
                    </select>
                    <button id="permission-grant" type="button">Grant</button>
                    <button id="permission-revoke" type="button">Revoke</button>
                    <label class="nl-check"><input id="cloud-policy" type="checkbox"> cloud policy</label>
                    <button id="cloud-save" type="button">Save cloud</button>
                </div>
                <div class="nl-filter-row">
                    <select id="autonomy-mode">
                        <option value="off">off</option>
                        <option value="assisted">assisted</option>
                        <option value="automatic">automatic</option>
                    </select>
                    <input id="autonomy-missions" type="number" min="1" max="5" placeholder="max missions">
                    <input id="autonomy-attempts" type="number" min="1" placeholder="attempts">
                    <button id="autonomy-save" type="button">Save autonomy</button>
                </div>
                <h3>MCP servers (JSON)</h3>
                <p class="nl-hint">MCP servers are trusted local tools. The <strong>rea</strong> reverse-engineering server is configured with a curated allowlist; discovery is read-only and tool invocation is permission-gated. JSON edits are saved through the engine.</p>
                <textarea id="mcp-json" rows="5" aria-label="MCP servers JSON"></textarea>
                <button id="mcp-save" type="button">Save MCP</button>
                <h3>Model capability probe</h3>
                <div class="nl-filter-row">
                    <select id="probe-model" aria-label="Model to probe"></select>
                    <button id="probe-run" type="button">Probe capabilities</button>
                    <span id="probe-result" class="nl-muted"></span>
                </div>
                <h3>Background jobs</h3>
                <div class="nl-filter-row">
                    <button id="jobs-refresh" type="button">Refresh jobs</button>
                    <span class="nl-muted">Allowlisted project scripts · bounded logs</span>
                </div>
                <div id="jobs-list" class="nl-list"></div>
                <h3>Storage Manager</h3>
                <div class="nl-filter-row">
                    <button id="storage-scan" type="button">Scan storage</button>
                    <button id="storage-purge" type="button">Purge selected</button>
                    <button id="storage-vacuum" type="button">Compact SQLite</button>
                    <button id="storage-cleanup-orphans" type="button">Clean orphan chats</button>
                    <button id="storage-cleanup-archived" type="button">Clean archived chats</button>
                    <span id="storage-total" class="nl-muted"></span>
                </div>
                <div id="storage-list" class="nl-list"></div>
            </div>
            <div id="engine-content" class="nl-detail"></div>
        </section>
    </main>
    <script src="${escapeHtml(assets.scriptUri)}"></script>
</body>
</html>`;
}
