/**
 * Real VS Code Insiders acceptance for the completed chat surface:
 * model selection -> conversation, attachment -> context, editor selection,
 * authorized URL fetch -> context, persisted history, and automatic mode.
 *
 * Requires the isolated runner (runChatFeatureTests.cjs), which grants the
 * Project Access NETWORK/web-fetch permission in a scratch data directory.
 */
'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');

const EXTENSION_NAME = 'nl-coding-agent';
const TOKEN = 'NL-EDITOR-TOKEN-52';
const EXPLICIT_MODEL = 'ollama/granite4.2:3b';

function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitFor(predicate, timeoutMs, label, intervalMs) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
        if (await predicate()) {
            return;
        }
        await sleep(intervalMs || 200);
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

function latestState(api) {
    return api.chat.debugState.posted.filter((message) => message.type === 'state').pop();
}

function latestHistory(api) {
    return api.chat.debugState.posted.filter((message) => message.type === 'history').pop();
}

async function run() {
    console.log('== NL Coding Agent chat feature acceptance ==');
    const extension = findExtension();
    assert(extension, 'extension not found');
    assert.strictEqual(extension.packageJSON.displayName, 'NL Coder', 'extension display name');
    assert.strictEqual(extension.packageJSON.icon, 'assets/icon.png', 'extension icon manifest');
    assert(fs.existsSync(path.join(extension.extensionPath, 'assets', 'icon.png')), 'real icon asset exists');
    const api = await extension.activate();
    const folders = vscode.workspace.workspaceFolders || [];
    assert(folders.length === 1, 'one isolated workspace folder is required');
    const projectRoot = folders[0].uri.fsPath;
    const notesPath = path.join(projectRoot, 'notes.txt');
    assert(fs.existsSync(notesPath), 'notes.txt fixture');
    await api.connect();
    const status = await api.getStatus();
    assert(status.tools.includes('attachment_ingest'), 'attachment tool exposed');
    assert(status.tools.includes('chat_history'), 'history tool exposed');
    assert(status.tools.includes('research_fetch_url'), 'research tool exposed');

    await vscode.commands.executeCommand('nlCodingAgent.startChat');
    await vscode.commands.executeCommand('workbench.view.extension.nlCodingAgentChat');
    await vscode.commands.executeCommand('nlCodingAgent.chat.focus').then(undefined, () => undefined);
    await waitFor(() => api.chat.debugState.resolved, 20000, 'webview view');
    await waitFor(() => latestState(api) && latestState(api).payload.settings &&
        latestState(api).payload.settings.research &&
        latestState(api).payload.settings.research.profile === 'trusted-auto-review',
        30000, 'engine settings with trusted research profile');
    console.log('PASS webview ready with engine settings and trusted research profile');

    await api.chat.searchWorkspaceFiles('notes');
    const fileMentions = api.chat.debugState.posted.filter((message) =>
        message.type === 'fileMentions').pop();
    assert(fileMentions && fileMentions.files.some((item) => item.path === 'notes.txt'),
        'workspace @mention search returns the matching project file');
    await api.chat.mentionWorkspaceFile('notes.txt');
    assert(latestState(api).payload.attachments.some((item) => item.name === 'notes.txt'),
        '@mention selection uses the existing attachment pipeline');
    api.chat.removeAttachment(latestState(api).payload.attachments.find((item) => item.name === 'notes.txt').id);
    console.log('PASS installed VSIX @file search -> project attachment');

    // Concurrent MCP calls must stay responsive while the real Team Architect runs.
    const queued = await api.connection.chatEnqueue('Concurrent queue-removal acceptance item');
    assert(queued.item && queued.item.id, 'queue item created');
    const originalQuickPick = vscode.window.showQuickPick;
    const originalModelOptions = api.chat.modelOptions;
    const originalTeamPlan = api.connection.teamPlan;
    let quickCalls;
    let quickCallDuration = 0;
    api.chat.modelOptions = () => [{
        value: EXPLICIT_MODEL,
        label: EXPLICIT_MODEL,
        group: 'test',
        loaded: false,
        provider: 'ollama',
        model: 'granite4.2:3b'
    }];
    vscode.window.showQuickPick = async (items) => items.find((item) => item.route === EXPLICIT_MODEL);
    api.connection.teamPlan = function (model, focus) {
        const teamRequest = originalTeamPlan.call(this, model, focus);
        const quickCallsStartedAt = Date.now();
        quickCalls = Promise.all([
            api.connection.missionDetail(2147483647).then(() => {
                throw new Error('mission_detail unexpectedly accepted a missing mission');
            }, (error) => {
                assert(/Mission does not belong/.test(error.message), error.message);
            }),
            api.connection.chatQueueRemove(queued.item.id),
            api.connection.saveRoleSettings('chat', { model: EXPLICIT_MODEL })
        ]).then((result) => {
            quickCallDuration = Date.now() - quickCallsStartedAt;
            return result;
        });
        return teamRequest;
    };
    api.chat.drainingQueue = true;
    try {
        await api.chat.generateSpecialistTeam(true);
        await quickCalls;
        assert(quickCallDuration < 10000,
            'mission_detail, queue remove and role settings stayed responsive (' + quickCallDuration + ' ms)');
    } finally {
        api.chat.drainingQueue = false;
        vscode.window.showQuickPick = originalQuickPick;
        api.connection.teamPlan = originalTeamPlan;
        api.chat.modelOptions = originalModelOptions;
    }
    assert.strictEqual(api.chat.debugState.busy, false, 'Team Architect releases the busy state');
    assert(api.chat.debugState.posted.some((message) =>
        message.type === 'chat' && message.role === 'system' && /Team Architect:/.test(message.text)),
    'Team Architect completed and persisted a specialist team');
    const assignedTeam = await api.connection.customAgents();
    const activeSpecialists = assignedTeam.agents.filter((agent) => agent.team_active);
    assert(activeSpecialists.length > 0, 'Team Architect persisted active project specialists');
    assert(activeSpecialists.every((agent) =>
        ['architect', 'developer', 'debugger', 'reviewer', 'auditor'].includes(agent.role_id) &&
        String(agent.model || '').includes('/') &&
        String(agent.model).startsWith(String(agent.provider || '') + '/')),
    'active specialist provider/model assignments persisted: ' + JSON.stringify(activeSpecialists));
    assert(!(await api.connection.chatQueue()).items.some((item) => item.id === queued.item.id),
        'the concurrently removed queue item is gone');
    console.log('PASS installed Team Architect persisted provider/model routes for active specialists');
    console.log('PASS installed Team Architect completed alongside mission, queue and settings calls');

    const clipboardImage = fs.readFileSync(path.join(extension.extensionPath, 'assets', 'icon.png'))
        .toString('base64');
    await api.chat.attachClipboardImage(clipboardImage);
    await waitFor(() => latestState(api).payload.attachments.some((item) => item.kind === 'image'),
        20000, 'pasted clipboard image attachment');
    const pastedImage = latestState(api).payload.attachments.find((item) => item.kind === 'image');
    assert(pastedImage && pastedImage.mime === 'image/png', 'clipboard PNG stored by the engine');
    api.chat.removeAttachment(pastedImage.id);
    console.log('PASS installed VSIX clipboard image -> MCP attachment store');

    // 1. Explicit model selection must be used by the real request.
    api.setChatModel(EXPLICIT_MODEL);
    await waitFor(() => latestState(api).payload.chatModel === EXPLICIT_MODEL, 10000, 'selected model state');
    await api.chat.handleUserMessage('Reply with exactly: MODEL-OK');
    await waitFor(() => !api.chat.debugState.busy, 240000, 'model reply');
    let state = latestState(api);
    const assistant = api.chat.debugState.posted.filter((message) =>
        message.type === 'chat' && message.role === 'assistant').pop();
    assert(assistant && /MODEL-OK/.test(assistant.text), 'model reply: ' + JSON.stringify(assistant && assistant.text));
    assert(state.payload.lastRoute && state.payload.lastRoute.model === 'granite4.2:3b',
        'last route model: ' + JSON.stringify(state.payload.lastRoute));
    assert.strictEqual(state.payload.lastRoute.automatic, false, 'explicit route');
    console.log('PASS model selection influenced the request: ' + state.payload.lastRoute.model);

    // 2. Engine attachment ingestion and model context.
    await api.attachPaths([notesPath]);
    await waitFor(() => latestState(api).payload.attachments.length >= 1, 20000, 'attachment state');
    let attachment = latestState(api).payload.attachments[0];
    assert.strictEqual(attachment.name, 'notes.txt');
    assert(attachment.preview && attachment.preview.includes(TOKEN), 'attachment preview has token');
    await api.chat.handleUserMessage('Read the attached notes. Reply with exactly the secret token and nothing else.');
    await waitFor(() => !api.chat.debugState.busy, 240000, 'attachment reply');
    const attachmentReply = api.chat.debugState.posted.filter((message) =>
        message.type === 'chat' && message.role === 'assistant').pop();
    assert(attachmentReply && attachmentReply.text.includes(TOKEN), 'model used attachment: ' +
        JSON.stringify(attachmentReply && attachmentReply.text));
    console.log('PASS attachment -> model context: ' + attachmentReply.text.trim());

    // 3. Editor selection context via the real VS Code document API.
    const document = await vscode.workspace.openTextDocument(vscode.Uri.file(notesPath));
    const editor = await vscode.window.showTextDocument(document);
    const line = document.getText().split(/\r?\n/).findIndex((text) => text.includes(TOKEN));
    const start = new vscode.Position(line, 0);
    editor.selection = new vscode.Selection(start, new vscode.Position(line, document.lineAt(line).text.length));
    await api.chat.attachActiveEditor('selection');
    await sleep(1500);
    console.log('DEBUG active editor: ' + JSON.stringify(vscode.window.activeTextEditor
        ? { path: vscode.window.activeTextEditor.document.uri.fsPath,
            selection: !vscode.window.activeTextEditor.selection.isEmpty }
        : null));
    console.log('DEBUG attachments: ' + JSON.stringify((latestState(api).payload.attachments || [])
        .map((item) => ({ name: item.name, status: item.extraction_status }))));
    console.log('DEBUG errors: ' + JSON.stringify(api.chat.debugState.posted.filter((message) =>
        message.type === 'chat' && message.role === 'error').map((message) => message.text)));
    await waitFor(() => latestState(api).payload.attachments.length >= 1, 20000, 'selection attachment');
    const selectionAttachment = latestState(api).payload.attachments.slice(-1)[0];
    assert(selectionAttachment.name.includes('selection'), 'selection attachment name: ' + selectionAttachment.name);
    assert(selectionAttachment.preview.includes(TOKEN), 'selection text captured');
    console.log('PASS editor selection captured as attachment: ' + selectionAttachment.name);

    // 4. A URL sent in Chat is fetched, ingested and included in that same turn.
    //
    // Pending attachments are deliberately cleared when the turn completes (explicit
    // per-turn context), so the assertion is on the durable evidence of the turn:
    // the system message that announced the untrusted fetch, the engine history with
    // the attachment ids, and the assistant reply. Full preview text is asserted by
    // the engine-level research/chat-tools tests.
    await api.chat.handleUserMessage('Fetch and summarize this URL: https://www.python.org/');
    await waitFor(() => !api.chat.debugState.busy, 240000, 'URL research chat turn');
    const fetchNotice = api.chat.debugState.posted.filter((message) =>
        message.type === 'chat' && message.role === 'system' &&
        String(message.text || '').includes('as UNTRUSTED context')).pop();
    assert(fetchNotice, 'URL was recognized, fetched and attached to its Chat turn');
    assert(String(fetchNotice.text).includes('python.org'),
        'fetched page notice preserves its source URL');
    assert.strictEqual(latestState(api).payload.attachments.length, 0,
        'pending attachments are consumed and cleared after the turn');
    const researchReply = api.chat.debugState.posted.filter((message) =>
        message.type === 'chat' && message.role === 'assistant').pop();
    assert(researchReply && researchReply.text.trim(), 'model returned a chat reply');
    await api.loadHistory();
    const researchHistory = latestHistory(api).payload;
    const researchTurn = researchHistory.messages.find((message) =>
        message.role === 'user' && message.content.includes('Fetch and summarize this URL'));
    assert(researchTurn && researchTurn.attachments && researchTurn.attachments.length >= 1,
        'fetched page attachment persisted on the real Chat turn');
    assert(researchTurn.attachments.every((item) => item.has_text),
        'persisted fetched attachments keep their extracted text');
    console.log('PASS Chat URL detection -> live fetch -> persisted same-turn attachment');

    // 5. Persisted history is returned by the engine, including route/attachment metadata.
    await api.loadHistory();
    await waitFor(() => {
        const history = latestHistory(api);
        return history && history.payload.messages && history.payload.messages.length >= 6;
    }, 20000, 'persisted history');
    const history = latestHistory(api).payload;
    const historyText = history.messages.map((message) => message.content).join('\n');
    assert(historyText.includes('MODEL-OK'), 'history contains model turn');
    assert(history.messages.some((message) => message.attachments && message.attachments.length),
        'history includes attachment metadata');
    assert(history.messages.some((message) => message.model === 'granite4.2:3b'),
        'history records the route model');
    console.log('PASS persisted engine history: ' + history.count + ' messages');

    // 6. Automatic mode omits the spec and the engine reports the fallback route.
    api.setChatModel('');
    await waitFor(() => latestState(api).payload.chatModel === '', 10000, 'automatic model state');
    await api.chat.handleUserMessage('Reply with exactly: AUTO-OK');
    await waitFor(() => !api.chat.debugState.busy, 240000, 'automatic reply');
    state = latestState(api);
    assert(state.payload.lastRoute && state.payload.lastRoute.automatic === true,
        'automatic route: ' + JSON.stringify(state.payload.lastRoute));
    console.log('PASS automatic mode -> engine default ' + state.payload.lastRoute.model);

    const pid = api.connection.childPid;
    await api.shutdown();
    await waitFor(() => {
        try { process.kill(pid, 0); return false; } catch { return true; }
    }, 10000, 'python child exit');
    console.log('PASS shutdown released python child ' + pid);
    console.log('== CHAT-FEATURE-ACCEPTANCE-PASS ==');
}

module.exports = { run };
