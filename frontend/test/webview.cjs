/**
 * Webview security + behaviour tests.
 *
 * 1. The shipped webview script must be valid JavaScript (no TypeScript syntax).
 * 2. It must render engine text with textContent and never with an HTML sink.
 * 3. The generated HTML must carry a strict CSP with no inline script.
 * 4. Running the script against a minimal DOM must render the dashboard state,
 *    chat, mission mode, mission detail and send the expected actions.
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
    for (const id of ['mission-banner', 'mission-list', 'mission-detail', 'engine-content',
        'chat-model', 'dev-model', 'reviewer-model', 'mode', 'exec-toggle']) {
        assert(html.includes(`id="${id}"`), `markup exposes #${id}`);
    }
    assert.strictEqual(escapeHtml('<b>&"\'</b>'), '&lt;b&gt;&amp;&quot;&#39;&lt;/b&gt;');
    console.log('PASS generated HTML has a strict CSP, no inline script and the dashboard structure');
}

class FakeClassList {
    constructor() {
        this.values = new Set();
    }
    add(...names) { names.forEach((name) => this.values.add(name)); }
    remove(...names) { names.forEach((name) => this.values.delete(name)); }
    contains(name) { return this.values.has(name); }
    toggle(name, force) {
        const next = force === undefined ? !this.values.has(name) : Boolean(force);
        if (next) { this.values.add(name); } else { this.values.delete(name); }
        return next;
    }
}

class FakeElement {
    constructor(tagName) {
        this.tagName = tagName;
        this.children = [];
        this.listeners = new Map();
        this.classList = new FakeClassList();
        this._className = '';
        this._text = '';
        this.dataset = {};
        this.style = {};
        this.value = '';
        this.disabled = false;
        this.scrollTop = 0;
        this.scrollHeight = 0;
        this.focused = false;
    }
    set className(value) {
        this._className = String(value || '');
        this.classList = new FakeClassList();
        this._className.split(/\s+/).filter(Boolean).forEach((name) => this.classList.add(name));
    }
    get className() { return this._className; }
    get firstChild() { return this.children[0] || null; }
    set textContent(value) { this._text = String(value); this.children = []; }
    get textContent() { return this._text; }
    appendChild(child) { this.children.push(child); return child; }
    removeChild(child) {
        const index = this.children.indexOf(child);
        if (index >= 0) { this.children.splice(index, 1); }
        return child;
    }
    addEventListener(type, listener) {
        if (!this.listeners.has(type)) { this.listeners.set(type, []); }
        this.listeners.get(type).push(listener);
    }
    dispatch(type, event) {
        for (const listener of this.listeners.get(type) || []) { listener(event || {}); }
    }
    focus() { this.focused = true; }
}

function collectText(element) {
    if (!element) { return ''; }
    return String(element.textContent || '') + element.children.map(collectText).join(' ');
}

function testWebviewBehaviour() {
    const elements = new Map();
    const get = (id) => {
        if (!elements.has(id)) { elements.set(id, new FakeElement('div')); }
        return elements.get(id);
    };
    const tabButtons = ['chat', 'missions', 'engine'].map((name) => {
        const button = new FakeElement('button');
        button.dataset.tab = name;
        return button;
    });
    const posted = [];
    const windowListeners = new Map();
    const documentListeners = new Map();
    let savedState;
    const sandbox = {
        console,
        acquireVsCodeApi: () => ({
            postMessage: (message) => posted.push(message),
            getState: () => savedState,
            setState: (state) => { savedState = state; }
        }),
        document: {
            getElementById: get,
            createElement: (tag) => new FakeElement(tag),
            querySelectorAll: (selector) => selector === '.nl-tab-button' ? tabButtons : [],
            addEventListener: (type, listener) => {
                if (!documentListeners.has(type)) { documentListeners.set(type, []); }
                documentListeners.get(type).push(listener);
            }
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

    assert.strictEqual(posted[0].type, 'ready', 'webview posts ready');
    assert(get('input').focused, 'input is focused on load');

    const settings = {
        schema_version: 1,
        project: { id: 7, root: 'K:\\project' },
        execution_enabled: true,
        models: {
            config_path: 'K:\\engine\\config\\models.yaml',
            config_exists: true,
            ollama: { base_url: 'http://127.0.0.1:11434' },
            providers: [{ provider_id: 'ollama', kind: 'ollama', label: 'Ollama', base_url: 'http://127.0.0.1:11434', enabled: true }],
            roles: { developer: { model: 'ollama/dev' }, reviewer: { model: 'ollama/rev' } },
            chat_role: 'developer',
            chat_default_spec: 'ollama/dev',
            cloud_escalation_enabled: false,
            discovered: {
                reachable: true,
                providers: [{
                    provider_id: 'ollama', label: 'Ollama', reachable: true,
                    models: [
                        { name: 'dev', loaded: true, capabilities: ['completion'] },
                        { name: 'embed', capabilities: ['embedding'] }
                    ]
                }]
            }
        },
        mission_defaults: { developer_model: 'ollama/dev', reviewer_model: 'ollama/rev', debug_model: 'ollama/dev' },
        agents: { roles: [{ role: 'developer', model: 'ollama/dev', kind: 'llm' }], custom_agents: [] },
        permissions: {
            scopes: ['read', 'write', 'execute', 'delete', 'network'],
            policy: { read: true, write: true, execute: true, delete: false, network: true },
            cloud_escalation_enabled: false
        },
        research: {
            profile: 'trusted-auto-review',
            status: 'available',
            offline: false,
            network_configured: true,
            network_granted: true
        }
    };
    const detail = {
        mission: {
            id: 3, project_id: 7, title: 'Add sub', goal: 'Add sub to calc.py',
            status: 'completed', review_verdict: 'APPROVE', promotion_status: 'promoted',
            diff_stat: '1 file(s), +2/-0', changed_paths: ['src/calc.py'], harness_version: 2
        },
        tasks: [{ id: 1, title: 'Code Implementation', status: 'completed', agent_role: 'developer', attempts: 1 }],
        handoffs: [
            { id: 1, from_role: 'developer', to_role: 'tester', summary: 'staged 1 file', payload: { actions: ['Wrote src/calc.py'] } },
            { id: 2, from_role: 'reviewer', to_role: 'orchestrator', summary: 'APPROVE', payload: { verdict: 'APPROVE', review_notes: 'APPROVE\nLooks correct.' } }
        ],
        verification_runs: [
            { id: 1, command: 'verify:candidate pytest tests', exit_code: 0, passed: true, stdout: '2 passed' },
            { id: 2, command: 'verify:oracle pytest tests', exit_code: 0, passed: true, stdout: '2 passed' }
        ],
        attempts: [{
            id: 1, task_title: 'Code Implementation', agent_role: 'developer', status: 'completed',
            output: '```write:src/calc.py\n...',
            metadata: {
                model: 'qwen2.5-coder:7b-instruct-q4_K_M', provider: 'ollama',
                duration_s: 12.4, usage: { total_tokens: 321 }
            }
        }],
        model_bindings: {
            architect: { role: 'architect', provider_id: 'ollama', model_name: 'qwen2.5-coder:7b-instruct-q4_K_M', source: 'role_config' },
            developer: { role: 'developer', provider_id: 'ollama', model_name: 'qwen2.5-coder:7b-instruct-q4_K_M', source: 'role_config' },
            reviewer: { role: 'reviewer', provider_id: 'ollama', model_name: 'qwen2.5-coder:7b-instruct-q4_K_M', source: 'role_config' }
        },
        progress: { total: 3, completed: 3, failed: 0, running: 0, pending: 0, percent: 100 }
    };
    const state = {
        connected: true,
        connectionState: 'ready',
        project: { id: 7, root: 'K:\\project', name: 'project' },
        engine: { name: 'NL Coding Engine', version: '1.0' },
        executionEnabled: true,
        settings,
        missions: [{
            id: 3, project_id: 7, title: 'Add sub', goal: 'Add sub to calc.py', status: 'completed',
            review_verdict: 'APPROVE', promotion_status: 'promoted', diff_stat: '1 file(s), +2/-0',
            changed_paths: ['src/calc.py'], harness_version: 2
        }],
        selected: { detail, diff: { ok: true, diff: '--- a/src/calc.py\n+++ b/src/calc.py\n@@\n+def sub(a, b):' } },
        activeMissionId: 3,
        busyChat: false,
        busyMission: false,
        chatModel: 'ollama/dev',
        missionModels: { developerModel: 'ollama/dev', reviewerModel: 'ollama/rev' },
        modelOptions: [
            { value: '', label: 'Automatic — ollama/dev (developer)', group: 'automatic', loaded: false, provider: '', model: '', automatic: true },
            { value: 'ollama/dev', label: 'dev', group: 'Ollama', loaded: true, provider: 'ollama', model: 'dev' },
            { value: 'ollama/rev', label: 'rev', group: 'Ollama', loaded: false, provider: 'ollama', model: 'rev' }
        ],
        providers: [{ id: 'ollama', label: 'Ollama', kind: 'ollama', enabled: true }],
        defaultChatSpec: 'ollama/dev',
        chatRole: 'developer',
        busyPhase: 'idle',
        attachments: [{
            id: 41, project_id: 7, name: 'notes.txt', kind: 'text', mime: 'text/plain',
            size_bytes: 29, extraction_status: 'extracted', text_chars: 29, has_text: true,
            metadata: { truncated: false }, preview: 'hello attachment\nsecond line\n'
        }],
        editor: {
            path: 'K:\\project\\src\\calc.py', relativePath: 'src/calc.py',
            languageId: 'python', hasSelection: true, selectionLines: 3, dirty: false
        },
        research: {
            ok: true, outcome: 'allowed', capability: 'web-fetch',
            url: 'https://example.com/', title: 'Example Domain',
            text: 'Example Domain\n\nThis domain is for use in examples.',
            text_truncated: false, untrusted: true, source_id: 1,
            provenance: { content_type: 'text/html', size: 577 },
            injection_warnings: []
        },
        researchProfile: 'trusted-auto-review',
        historyCount: 2,
        historyLoaded: true
    };
    const send = (data) => {
        for (const listener of windowListeners.get('message') || []) { listener({ data }); }
    };
    send({ type: 'state', payload: state });

    assert.strictEqual(get('status').textContent, 'missions enabled · project #7');
    assert.strictEqual(get('project-badge').textContent, '#7 · project');
    assert.strictEqual(get('exec-toggle').dataset.enabled, 'true');
    assert.strictEqual(get('chat-model').value, 'ollama/dev');
    assert.strictEqual(get('provider-select').value, 'ollama');
    assert.strictEqual(get('auto-model').checked, false);
    assert(collectText(get('model-current')).includes('Explicit'));
    assert.strictEqual(get('dev-model').value, 'ollama/dev');
    assert.strictEqual(get('reviewer-model').value, 'ollama/rev');
    assert.strictEqual(get('attachment-chips').children.length, 1, 'attachment chip rendered');
    assert(collectText(get('attachment-chips')).includes('notes.txt'));
    assert(collectText(get('editor-context')).includes('src/calc.py'));
    assert(!get('research-card').classList.contains('hidden'), 'research card visible');
    assert.strictEqual(get('research-title').textContent, 'Example Domain');
    assert(get('research-text').textContent.includes('This domain is for use'));
    assert.strictEqual(get('research-use').disabled, false);
    assert.strictEqual(get('mission-list').children.length, 1, 'mission row rendered');
    assert(!get('mission-banner').classList.contains('hidden'), 'active mission banner visible');
    assert.strictEqual(get('banner-status').textContent, 'completed');
    assert.strictEqual(get('banner-progress-bar').style.width, '100%');
    assert.strictEqual(get('mission-detail').classList.contains('hidden'), false);
    const detailText = collectText(get('mission-detail'));
    assert(detailText.includes('Mission #3'), 'detail title rendered');
    assert(detailText.includes('APPROVE'), 'reviewer verdict rendered');
    assert(detailText.includes('verify:candidate'), 'verification command rendered');
    assert(detailText.includes('Tool activity'), 'persisted tool activity rendered');
    assert(detailText.includes('Wrote src/calc.py'), 'recorded write action rendered');
    assert(detailText.includes('ModelRouter snapshot'), 'model assignment section rendered');
    assert(detailText.includes('qwen2.5-coder'), 'role model assignment rendered');
    assert(detailText.includes('12.4s') && detailText.includes('321 tokens'), 'attempt model/usage evidence rendered');
    assert(detailText.includes('def sub'), 'diff rendered');
    const engineText = collectText(get('engine-content'));
    assert(engineText.includes('Permissions'), 'engine permissions rendered');
    assert(engineText.includes('Research / URL fetch'), 'research settings rendered');
    assert(engineText.includes('Trusted auto review'), 'research profile options rendered');
    assert(engineText.includes('ollama/dev'), 'model routes rendered');
    assert(engineText.includes('dev'), 'discovered model rendered');

    // Engine history is rendered from the engine's persisted thread, not local storage.
    send({
        type: 'history',
        payload: {
            messages: [
                { role: 'user', content: 'first question', created_at: '2026-10-29T10:00:00', attachments: [{ name: 'notes.txt', kind: 'text', size_bytes: 29, has_text: true }] },
                { role: 'assistant', content: 'see https://example.com/', created_at: '2026-10-29T10:00:05', model: 'dev' }
            ]
        }
    });
    assert.strictEqual(get('messages').children.length, 2, 'history rendered');
    const assistantHistory = get('messages').children[1];
    assert(collectText(assistantHistory).includes('via dev'), 'assistant route rendered from history');
    const link = (function find(node) {
        if (node.className && String(node.className).includes('nl-link')) { return node; }
        for (const child of node.children) {
            const found = find(child);
            if (found) { return found; }
        }
        return null;
    })(assistantHistory);
    assert(link && link.tagName === 'a', 'URL recognised and rendered as a link');
    link.dispatch('click', { preventDefault() {} });
    assert(posted.some((message) => message.type === 'action' && message.action === 'fetchUrl' &&
        message.payload.url === 'https://example.com/'), 'link click requests a real research fetch');

    // Tab navigation.
    tabButtons[1].dispatch('click', {});
    assert(get('tab-missions').classList.contains('active'), 'missions tab active after click');
    assert(!get('tab-chat').classList.contains('active'), 'chat tab inactive after click');

    // Mission mode: switch, fill objective, submit -> startMission action.
    get('mode').value = 'mission';
    get('mode').dispatch('change', {});
    assert(!get('mission-fields').classList.contains('hidden'), 'mission fields visible');
    assert.strictEqual(get('send').textContent, 'Start mission');
    get('input').value = 'Add sub to src/calc.py';
    get('composer').dispatch('submit', { preventDefault() {} });
    const missionAction = posted.find((message) => message.type === 'action' && message.action === 'startMission');
    assert(missionAction, 'mission action posted');
    assert.strictEqual(missionAction.payload.goal, 'Add sub to src/calc.py');
    assert.strictEqual(missionAction.payload.developerModel, 'ollama/dev');
    assert.strictEqual(missionAction.payload.reviewerModel, 'ollama/rev');

    // Chat mode: real send action.
    get('mode').value = 'chat';
    get('mode').dispatch('change', {});
    get('input').value = 'hello engine';
    get('composer').dispatch('submit', { preventDefault() {} });
    const chatAction = posted.find((message) => message.type === 'action' && message.action === 'sendChat');
    assert(chatAction && chatAction.payload.text === 'hello engine', 'chat action posted');

    // Hostile model text stays text.
    const hostile = '<img src=x onerror="globalThis.__pwned=1"> & <script>alert(1)</script>';
    send({ type: 'chat', role: 'assistant', text: hostile });
    const messages = get('messages').children;
    const last = messages[messages.length - 1];
    assert(last.className.includes('nl-message-assistant'), 'assistant message class');
    const body = last.children[1];
    assert.strictEqual(collectText(body), hostile, 'model text rendered verbatim');
    assert(body.children.every((child) => child.tagName === 'span'), 'only text spans created from model text');
    assert.strictEqual(sandbox.__pwned, undefined, 'no script executed');

    // Busy state keeps input available so messages can be queued or steered.
    send({ type: 'state', payload: { ...state, busyChat: true } });
    assert.strictEqual(get('send').disabled, false, 'send remains available while busy');
    assert.strictEqual(get('send').textContent, 'Queue');
    assert(get('hint').textContent.includes('/steer'), 'busy hint explains steering');

    // Error notice.
    send({ type: 'state', payload: { ...state, error: 'engine is read-only' } });
    assert(!get('notice').classList.contains('hidden'), 'error notice visible');
    assert.strictEqual(get('notice').textContent, 'engine is read-only');

    console.log('PASS webview behaviour: state, chat, mission mode/detail, safe text rendering');
}

testScriptSyntax();
testHtml();
testWebviewBehaviour();
console.log('== WEBVIEW-TESTS-PASS ==');
