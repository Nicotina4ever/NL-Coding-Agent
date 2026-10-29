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
    <title>NL Chat</title>
</head>
<body>
    <header class="nl-header">
        <span class="nl-brand">NL Chat</span>
        <span id="status" class="nl-status" role="status" aria-live="polite">Starting…</span>
    </header>
    <main id="messages" class="nl-messages" role="log" aria-live="polite" aria-label="Conversation"></main>
    <form id="composer" class="nl-composer" autocomplete="off">
        <label class="nl-visually-hidden" for="input">Message NL Coding Agent</label>
        <textarea id="input" rows="3" placeholder="Ask NL Coding Agent… (Enter to send, Shift+Enter for a new line)"></textarea>
        <div class="nl-composer-actions">
            <span id="hint" class="nl-hint"></span>
            <button id="send" type="submit">Send</button>
        </div>
    </form>
    <script src="${escapeHtml(assets.scriptUri)}"></script>
</body>
</html>`;
}
