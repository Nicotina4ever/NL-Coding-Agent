/**
 * Real VS Code Insiders extension-host acceptance.
 *
 * Loaded by VS Code via --extensionTestsPath. Verifies activation, the live MCP
 * session, tool discovery, workspace->project mapping, the real Ollama reply,
 * that the NL Chat webview was created and received real results, cross-project
 * refusal, and that shutdown releases the Python child process.
 */
'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');

const EXTENSION_NAME = 'nl-coding-agent';

function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitFor(predicate, timeoutMs, label) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
        if (await predicate()) {
            return;
        }
        await sleep(150);
    }
    throw new Error('timed out waiting for ' + label);
}

function findExtension() {
    const direct = vscode.extensions.getExtension('nlcodingagent.' + EXTENSION_NAME);
    if (direct) {
        return direct;
    }
    return vscode.extensions.all.find((item) => item.packageJSON && item.packageJSON.name === EXTENSION_NAME);
}

function assertPathEqual(actual, expected, label) {
    const left = path.resolve(String(actual)).toLowerCase();
    const right = path.resolve(String(expected)).toLowerCase();
    assert.strictEqual(left, right, label + ': expected ' + expected + ', got ' + actual);
}

function alive(pid) {
    try {
        process.kill(pid, 0);
        return true;
    } catch {
        return false;
    }
}

async function run() {
    console.log('== NL Coding Agent VS Code extension-host acceptance ==');
    const extension = findExtension();
    assert(extension, 'extension not found; loaded extensions: ' +
        vscode.extensions.all.map((item) => item.packageJSON && item.packageJSON.name).join(', '));
    console.log('extension: ' + extension.id + ' at ' + extension.extensionPath);
    assert.strictEqual(extension.packageJSON.displayName, 'NL Coder', 'extension display name');
    assert.strictEqual(extension.packageJSON.icon, 'assets/icon.png', 'extension icon manifest');
    assert(fs.existsSync(path.join(extension.extensionPath, 'assets', 'icon.png')), 'real icon asset exists');

    const api = await extension.activate();
    assert(api && api.connection && api.chat, 'activate() must return the testable API');

    // 1. Live MCP session + tool discovery.
    await api.connect();
    assert.strictEqual(api.connection.state, 'ready', 'connection ready');
    const tools = await api.connection.listTools();
    const names = tools.map((tool) => tool.name);
    for (const required of ['project_context', 'nlc_converse', 'mission_list', 'mission_detail',
        'candidate_diff', 'start_mission', 'cancel_mission', 'engine_settings',
        'attachment_ingest', 'chat_history', 'research_fetch_url']) {
        assert(names.includes(required), 'missing tool ' + required);
    }
    assert.strictEqual(api.connection.executionAllowed, false, 'engine session is read-only by default');
    const settings = await api.connection.engineSettings(false);
    assert(Number.isInteger(settings.project.id), 'engine_settings project id');
    assert(settings.permissions.scopes.includes('read'), 'engine_settings permissions');
    assert(settings.mission_defaults.developer_model, 'engine_settings mission defaults');
    console.log('PASS MCP initialize + tools: ' + names.join(', '));
    console.log('PASS engine settings: ' + settings.models.chat_default_spec + ' / missions ' +
        settings.mission_defaults.developer_model + ' -> ' + settings.mission_defaults.reviewer_model);

    // 2. Active workspace maps to the bound backend project.
    const folders = vscode.workspace.workspaceFolders || [];
    assert(folders.length > 0, 'the acceptance window must open one folder');
    const workspaceRoot = folders[0].uri.fsPath;
    const context = await api.connection.projectContext();
    assertPathEqual(context.project.root, workspaceRoot, 'workspace -> project root');
    assert(Number.isInteger(context.project.id) && context.project.id > 0, 'project id');
    console.log('PASS workspace mapping: "' + workspaceRoot + '" -> project #' + context.project.id);

    // 3. NL Chat view is created inside the real workbench and receives real results.
    await vscode.commands.executeCommand('nlCodingAgent.startChat');
    await vscode.commands.executeCommand('workbench.view.extension.nlCodingAgentChat');
    await vscode.commands.executeCommand('nlCodingAgent.chat.focus').then(undefined, () => undefined);
    await waitFor(() => api.chat.debugState.resolved, 20000, 'NL Chat webview view');
    await waitFor(() => api.chat.debugState.posted.some((message) =>
        message.type === 'status' && message.state === 'ready'), 60000, 'webview ready status');
    const html = (api.chat.renderedHtml || '')
        .replace(/&#39;/g, "'")
        .replace(/&quot;/g, '"')
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>')
        .replace(/&amp;/g, '&');
    assert(html.includes("default-src 'none'"), 'webview HTML has a CSP');
    assert(/media\/main\.js/.test(html), 'webview script points at the extension media resource');
    for (const id of ['chat-session', 'chat-queue', 'provider-id', 'provider-kind',
        'provider-api-key-env', 'chat-controls-toggle', 'mission-fields-toggle',
        'mission-list-toggle', 'generation-save', 'permission-grant',
        'autonomy-save', 'mcp-save', 'probe-run', 'storage-scan', 'storage-vacuum']) {
        assert(html.includes('id="' + id + '"'), 'real VSIX webview exposes #' + id);
    }
    const systemMessage = api.chat.debugState.posted.find((message) =>
        message.type === 'chat' && message.role === 'system');
    assert(systemMessage, 'webview received the project/tool system message');
    assert(systemMessage.text.includes('#' + context.project.id), 'system message shows the project id');
    assert(systemMessage.text.includes('Project:'), 'system message lists the bound project');
    const stateMessage = api.chat.debugState.posted.filter((message) => message.type === 'state').pop();
    assert(stateMessage && stateMessage.payload && stateMessage.payload.settings,
        'webview received engine settings in the dashboard state');
    assert.strictEqual(stateMessage.payload.project.id, context.project.id, 'dashboard project id');
    console.log('PASS NL Chat webview created; it received project #' + context.project.id +
        ' and the engine settings/model catalog');

    await vscode.commands.executeCommand('nlCodingAgent.openHome');
    await waitFor(() => Boolean(api.home && api.home.renderedHtml), 15000, 'NL Code home webview');
    const homeHtml = api.home.renderedHtml || '';
    for (const id of ['connection', 'project', 'execution', 'mission-count', 'model-count',
        'agent-count', 'session-count', 'details', 'theme']) {
        assert(homeHtml.includes('id="' + id + '"'), 'home dashboard exposes #' + id);
    }
    assert(homeHtml.includes('nlCodingAgent.startChat'), 'home exposes real command cards');
    assert(homeHtml.includes("default-src 'none'"), 'home dashboard has a strict CSP');
    console.log('PASS NL Code home dashboard rendered with real commands and live status');

    // 4. A real user turn reaches a configured Ollama model and is displayed.
    await api.chat.handleUserMessage('Reply with exactly: EXT-OK');
    const assistant = api.chat.debugState.posted.filter((message) =>
        message.type === 'chat' && message.role === 'assistant').pop();
    assert(assistant, 'webview received an assistant message');
    assert(/EXT-OK/.test(assistant.text), 'assistant reply text: ' + JSON.stringify(assistant.text));
    console.log('PASS real Ollama reply delivered to NL Chat: ' + JSON.stringify(assistant.text));

    // 5. Cross-project identity is refused.
    let refused = null;
    try {
        await api.connection.converse(context.project.id + 1, 'must be refused');
    } catch (error) {
        refused = error;
    }
    assert(refused && /bound to this server/i.test(refused.message), 'cross-project id must be refused');
    console.log('PASS cross-project project_id refused');

    // 6. Shutdown releases the child process.
    const pid = api.connection.childPid;
    assert(typeof pid === 'number' && pid > 0, 'python child pid');
    await api.shutdown();
    await waitFor(() => !alive(pid), 10000, 'python child exit');
    assert.strictEqual(api.connection.state, 'closed', 'connection closed');
    console.log('PASS shutdown released python child ' + pid);

    console.log('== EXTENSION-ACCEPTANCE-PASS ==');
}

// VS Code's extension-test harness imports this module and awaits `run()`.
module.exports = { run };

