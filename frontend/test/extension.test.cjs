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

    const api = await extension.activate();
    assert(api && api.connection && api.chat, 'activate() must return the testable API');

    // 1. Live MCP session + tool discovery.
    await api.connect();
    assert.strictEqual(api.connection.state, 'ready', 'connection ready');
    const tools = await api.connection.listTools();
    const names = tools.map((tool) => tool.name);
    for (const required of ['project_context', 'nlc_converse', 'mission_list']) {
        assert(names.includes(required), 'missing tool ' + required);
    }
    console.log('PASS MCP initialize + tools: ' + names.join(', '));

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
    await vscode.commands.executeCommand('workbench.view.extension.nlCodingAgent');
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
    const systemMessage = api.chat.debugState.posted.find((message) =>
        message.type === 'message' && message.role === 'system');
    assert(systemMessage, 'webview received the project/tool system message');
    assert(systemMessage.text.includes('#' + context.project.id), 'system message shows the project id');
    assert(systemMessage.text.includes('project_context'), 'system message lists real tools');
    console.log('PASS NL Chat webview created; it received project #' + context.project.id +
        ' and the discovered tools');

    // 4. A real user turn reaches a configured Ollama model and is displayed.
    await api.chat.handleUserMessage('Reply with exactly: EXT-OK');
    const assistant = api.chat.debugState.posted.filter((message) =>
        message.type === 'message' && message.role === 'assistant').pop();
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
