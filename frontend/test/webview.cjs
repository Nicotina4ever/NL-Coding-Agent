/**
 * Webview security + behaviour tests.
 *
 * 1. The shipped webview script must be valid JavaScript (the previous
 *    implementation put TypeScript casts inside the webview and broke the page).
 * 2. It must render model text with textContent and never with an HTML sink.
 * 3. The generated HTML must carry a strict CSP with no inline script.
 * 4. Running the script against a minimal DOM must post `ready`, send a message,
 *    and render an assistant reply safely.
 *
 * Usage: node test/webview.cjs
 */
'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const frontendDir = path.resolve(__dirname, '..');
const mediaDir = path.join(frontendDir, 'media');
const mainScript = fs.readFileSync(path.join(mediaDir, 'main.js'), 'utf8');
const { buildChatHtml, escapeHtml } = require(path.join(frontendDir, 'out', 'webview.js'));

function testScriptSyntax() {
    new vm.Script(mainScript, { filename: 'media/main.js' });
    assert(!/\bas\s+HTMLTextAreaElement\b/.test(mainScript), 'webview script must not contain TypeScript casts');
    for (const sink of ['.innerHTML', 'innerHTML =', 'outerHTML', 'document.write', 'eval(']) {
        assert(!mainScript.includes(sink), `webview script must not use ${sink}`);
    }
    assert(mainScript.includes('textContent'), 'webview script renders text with textContent');
    console.log('PASS webview/main.js parses and has no unsafe HTML sink');
}

function testHtml() {
    const rawHtml = buildChatHtml({
        scriptUri: 'vscode-webview://ext/media/main.js',
        styleUri: 'vscode-webview://ext/media/style.css',
        cspSource: 'vscode-webview://ext'
    });
    const html = rawHtml
        .replace(/&#39;/g, "'")
        .replace(/&quot;/g, '"')
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>')
        .replace(/&amp;/g, '&');
    assert(html.includes("default-src 'none'"), 'CSP default-src none');
    assert(html.includes("script-src vscode-webview://ext"), 'CSP allows only the extension script source');
    assert(!html.includes("'unsafe-inline'"), 'CSP must not allow unsafe-inline');
    assert(!html.includes("'unsafe-eval'"), 'CSP must not allow unsafe-eval');
    assert(html.includes("base-uri 'none'"), 'CSP base-uri');
    assert(html.includes('<script src="vscode-webview://ext/media/main.js">'), 'external webview script');
    assert(!/<script>[\s\S]*?<\/script>/.test(html.replace(/<script src=[^>]*><\/script>/g, '')), 'no inline script body');
    assert(!/\son[a-z]+\s*=/.test(html), 'no inline event handlers');
    assert.strictEqual(escapeHtml('<b>&"\'</b>'), '&lt;b&gt;&amp;&quot;&#39;&lt;/b&gt;');
    console.log('PASS generated HTML has a strict CSP, no inline script and escaped assets');
}

class FakeElement {
    constructor(tagName) {
        this.tagName = tagName;
        this.children = [];
        this.listeners = new Map();
        this._text = '';
        this.className = '';
        this.dataset = {};
        this.style = {};
        this.value = '';
        this.disabled = false;
        this.scrollTop = 0;
        this.scrollHeight = 0;
        this.focused = false;
    }
    set textContent(value) { this._text = String(value); }
    get textContent() { return this._text; }
    appendChild(child) { this.children.push(child); return child; }
    addEventListener(type, listener) {
        if (!this.listeners.has(type)) { this.listeners.set(type, []); }
        this.listeners.get(type).push(listener);
    }
    dispatch(type, event) {
        for (const listener of this.listeners.get(type) || []) { listener(event || {}); }
    }
    focus() { this.focused = true; }
}

function testWebviewBehaviour() {
    const elements = {
        status: new FakeElement('span'),
        messages: new FakeElement('main'),
        input: new FakeElement('textarea'),
        send: new FakeElement('button'),
        composer: new FakeElement('form'),
        hint: new FakeElement('span')
    };
    const posted = [];
    const windowListeners = new Map();
    let savedState;
    const sandbox = {
        console,
        acquireVsCodeApi: () => ({
            postMessage: (message) => posted.push(message),
            getState: () => savedState,
            setState: (state) => { savedState = state; }
        }),
        document: {
            getElementById: (id) => elements[id],
            createElement: (tag) => new FakeElement(tag)
        },
        window: {
            addEventListener: (type, listener) => {
                if (!windowListeners.has(type)) { windowListeners.set(type, []); }
                windowListeners.get(type).push(listener);
            }
        },
        setTimeout: (callback) => callback()
    };
    vm.runInNewContext(mainScript, sandbox, { filename: 'media/main.js' });

    assert.strictEqual(posted.length > 0 && posted[0].type, 'ready', 'webview posts ready');
    assert(elements.input.focused, 'input is focused on load');
    assert.strictEqual(elements.status.dataset.state, 'connecting', 'initial status');

    // Status + busy messages from the extension.
    for (const listener of windowListeners.get('message')) {
        listener({ data: { type: 'status', state: 'ready', label: 'Connected · project #1' } });
    }
    assert.strictEqual(elements.status.textContent, 'Connected · project #1');
    assert.strictEqual(elements.status.dataset.state, 'ready');

    // Sending through the form.
    elements.input.value = 'hello engine';
    elements.composer.dispatch('submit', { preventDefault() {} });
    const sent = posted.find((message) => message.type === 'send');
    assert(sent && sent.text === 'hello engine', 'webview sends the typed text');
    assert.strictEqual(elements.input.value, '', 'input cleared after send');
    const userMessage = elements.messages.children[elements.messages.children.length - 1];
    assert.strictEqual(userMessage.className, 'nl-message nl-message-user');

    // Busy state while the engine is answering.
    for (const listener of windowListeners.get('message')) {
        listener({ data: { type: 'busy', value: true } });
    }
    assert.strictEqual(elements.send.disabled, true, 'send disabled while busy');

    // Model output containing markup is rendered as text, never as HTML.
    const hostile = '<img src=x onerror="globalThis.__pwned=1"> & <script>alert(1)</script>';
    for (const listener of windowListeners.get('message')) {
        listener({ data: { type: 'message', role: 'assistant', text: hostile } });
    }
    const assistantMessage = elements.messages.children[elements.messages.children.length - 1];
    assert.strictEqual(assistantMessage.className, 'nl-message nl-message-assistant');
    const label = assistantMessage.children[0];
    const body = assistantMessage.children[1];
    assert.strictEqual(label.textContent, 'NL');
    assert.strictEqual(body.textContent, hostile, 'model text is stored verbatim, not interpreted');
    assert.strictEqual(body.children.length, 0, 'no HTML elements were created from model text');
    assert.strictEqual(sandbox.__pwned, undefined, 'no script executed from model text');
    console.log('PASS webview behaviour: ready, status, busy, send, safe text rendering');
}

testScriptSyntax();
testHtml();
testWebviewBehaviour();
console.log('== WEBVIEW-TESTS-PASS ==');
