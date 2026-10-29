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
            <span class="nl-brand">NL Coder</span>
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
            <button type="button" class="nl-tab-button" data-tab="engine">Engine</button>
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
                    <div id="model-bar" class="nl-model-bar">
                        <label class="nl-field nl-field-small">Provider
                            <select id="provider-select"></select>
                        </label>
                        <label class="nl-field nl-field-small">Model
                            <select id="chat-model"></select>
                        </label>
                        <label class="nl-check"><input id="auto-model" type="checkbox"> Automatic</label>
                        <span id="model-current" class="nl-muted"></span>
                    </div>

                    <label class="nl-visually-hidden" for="input">Message NL Coder</label>
                    <textarea id="input" rows="3" placeholder="Ask NL Coder…  (/mission &lt;objective&gt; starts a mission)"></textarea>

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
            <div id="mission-list" class="nl-list"></div>
            <div id="mission-detail" class="nl-detail hidden"></div>
        </section>

        <section id="tab-engine" class="nl-tab-panel">
            <div class="nl-section-head">
                <strong>Engine</strong>
                <span class="nl-actions">
                    <button id="refresh-models" type="button">Probe models</button>
                    <button id="refresh-engine" type="button">Refresh</button>
                </span>
            </div>
            <div id="engine-content" class="nl-detail"></div>
        </section>
    </main>
    <script src="${escapeHtml(assets.scriptUri)}"></script>
</body>
</html>`;
}
