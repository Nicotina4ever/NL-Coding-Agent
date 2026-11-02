/**
 * Installed VS Code acceptance for URL recognition, authorized fetch and
 * source-preserving attachment handoff without invoking an LLM.
 */
'use strict';

const assert = require('assert');
const vscode = require('vscode');

function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitFor(predicate, timeoutMs, label) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
        if (await predicate()) {
            return;
        }
        await sleep(200);
    }
    throw new Error('timed out waiting for ' + label);
}

function findExtension() {
    const direct = vscode.extensions.getExtension('nlcodingagent.nl-coding-agent');
    return direct || vscode.extensions.all.find((item) =>
        item.packageJSON && item.packageJSON.name === 'nl-coding-agent');
}

async function run() {
    const extension = findExtension();
    assert(extension, 'installed NL Coder extension');
    const api = await extension.activate();
    assert.strictEqual((vscode.workspace.workspaceFolders || []).length, 1,
        'one isolated project is required');
    await api.connect();
    await vscode.commands.executeCommand('nlCodingAgent.startChat');
    await vscode.commands.executeCommand('workbench.view.extension.nlCodingAgentChat');
    await waitFor(() => api.chat.debugState.resolved, 20000, 'Chat webview');

    let captured;
    let ingestedRequest;
    let ingestedResult;
    const originalConverse = api.connection.converse;
    const originalAttachmentIngest = api.connection.attachmentIngest;
    api.connection.converse = async (...args) => {
        captured = args;
        return { ok: true, reply: 'The page was fetched and attached.' };
    };
    api.connection.attachmentIngest = async (args) => {
        ingestedRequest = args;
        ingestedResult = await originalAttachmentIngest.call(api.connection, args);
        return ingestedResult;
    };
    try {
        await api.chat.handleUserMessage(
            'Read this page and summarize it: https://www.python.org/');
        await waitFor(() => !api.chat.debugState.busy, 30000, 'Chat turn');
    } finally {
        api.connection.converse = originalConverse;
        api.connection.attachmentIngest = originalAttachmentIngest;
    }

    assert(ingestedRequest && ingestedRequest.text.includes('Welcome to Python.org'),
        'the fetched page text reached attachment ingestion');
    assert(ingestedRequest.text.includes('Source URL: https://www.python.org/'),
        'attachment preserves the source URL');
    assert(ingestedRequest.text.includes('UNTRUSTED DATA'),
        'retrieved page is explicitly untrusted');
    const attachment = ingestedResult.attachments[0];
    assert(attachment && captured && captured[5].includes(attachment.id),
        'fetched attachment ID reaches the Chat turn');
    console.log('PASS installed VSIX URL detection -> authorized fetch -> sourced attachment');
    console.log('WEB-RESEARCH-ACCEPTANCE-PASS');
}

module.exports = { run };
