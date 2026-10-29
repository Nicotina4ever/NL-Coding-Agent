/**
 * Real mission acceptance inside VS Code Insiders.
 *
 * Uses the extension's public API (the same controller the NL Chat webview
 * calls) to start a real code-change mission on an isolated project. It then
 * waits for the Python engine, verifies the persisted tasks/handoffs/verification
 * runs/reviewer verdict, the promoted live file, the retained diff, and that the
 * dashboard webview receives the mission detail.
 */
'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');

const EXTENSION_NAME = 'nl-coding-agent';
const GOAL = 'In src/calc.py add sub(a, b) returning a - b. Preserve add and all existing tests. Change only src/calc.py.';
const DEVELOPER = 'ollama/qwen2.5-coder:7b-instruct-q4_K_M';
const REVIEWER = 'ollama/qwen2.5-coder:7b-instruct-q4_K_M';

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

async function run() {
    console.log('== NL Coding Agent mission acceptance ==');
    const extension = findExtension();
    assert(extension, 'extension not found');
    console.log('extension: ' + extension.id + ' at ' + extension.extensionPath);
    const api = await extension.activate();
    assert(api && api.connection && api.chat, 'activate() API');

    const folders = vscode.workspace.workspaceFolders || [];
    assert(folders.length === 1, 'one isolated workspace folder is required');
    const projectRoot = folders[0].uri.fsPath;
    console.log('isolated project: ' + projectRoot);
    assert(fs.existsSync(path.join(projectRoot, 'src', 'calc.py')), 'fixture src/calc.py');
    assert(fs.existsSync(path.join(projectRoot, 'tests', 'test_calc.py')), 'fixture tests/test_calc.py');

    await api.connect();
    const status = await api.getStatus();
    assert.strictEqual(status.executionEnabled, true, 'mission execution must be enabled for this test');
    const settings = await api.connection.engineSettings(false);
    console.log('engine tools: ' + (status.tools || []).join(', '));
    console.log('mission routes: ' + DEVELOPER + ' -> ' + REVIEWER);

    const started = await api.startMission({ goal: GOAL, developerModel: DEVELOPER, reviewerModel: REVIEWER });
    assert(started && Number.isInteger(started.missionId), 'mission id returned');
    const missionId = started.missionId;
    console.log('PASS mission dispatched: #' + missionId);

    const deadline = Date.now() + 300000;
    let detail = null;
    let lastStatus = '';
    while (Date.now() < deadline) {
        detail = await api.getMissionDetail(missionId);
        const current = detail.mission.status;
        if (current !== lastStatus) {
            console.log('mission status: ' + current + ' · tasks ' + detail.progress.completed + '/' + detail.progress.total);
            lastStatus = current;
        }
        if (['completed', 'failed', 'blocked', 'interrupted'].includes(current)) {
            break;
        }
        await sleep(1500);
    }
    assert(detail, 'mission detail returned');
    console.log('final status: ' + detail.mission.status + ' · verdict ' + detail.mission.review_verdict +
        ' · promotion ' + detail.mission.promotion_status);
    console.log('tasks: ' + detail.tasks.map((task) => task.agent_role + ':' + task.status).join(', '));
    console.log('handoffs: ' + detail.handoffs.map((item) => item.from_role + '->' + item.to_role).join(', '));
    console.log('verification: ' + detail.verification_runs.map((run) =>
        (run.passed ? 'PASS' : 'FAIL') + ' ' + run.command.split(' ')[0]).join(', '));
    if (detail.mission.result_summary) {
        console.log('result: ' + detail.mission.result_summary);
    }

    assert.strictEqual(detail.mission.status, 'completed', 'mission completed: ' + detail.mission.result_summary);
    assert.strictEqual(detail.mission.review_verdict, 'APPROVE', 'reviewer approved');
    assert.strictEqual(detail.mission.promotion_status, 'promoted', 'candidate promoted');
    assert(Array.isArray(detail.mission.changed_paths) && detail.mission.changed_paths.includes('src/calc.py'),
        'changed paths contain src/calc.py');
    assert(detail.tasks.length >= 3, 'developer/tester/reviewer tasks persisted');
    assert(detail.handoffs.some((item) => item.from_role === 'developer' && item.to_role === 'tester'),
        'developer handoff persisted');
    assert(detail.handoffs.some((item) => item.from_role === 'reviewer'), 'reviewer handoff persisted');
    const candidate = detail.verification_runs.filter((run) => run.command.startsWith('verify:candidate'));
    const oracle = detail.verification_runs.filter((run) => run.command.startsWith('verify:oracle'));
    assert(candidate.length >= 1 && candidate.every((run) => run.passed), 'candidate suite passed');
    assert(oracle.length >= 1 && oracle.every((run) => run.passed), 'oracle suite passed');
    const source = fs.readFileSync(path.join(projectRoot, 'src', 'calc.py'), 'utf8');
    assert(/def\s+sub\s*\(/.test(source), 'live src/calc.py contains sub()');
    console.log('PASS live file promoted: src/calc.py contains sub()');

    const diff = await api.getCandidateDiff(missionId);
    assert(diff && diff.ok === true, 'retained candidate diff available: ' + JSON.stringify(diff && diff.error));
    assert(typeof diff.diff === 'string' && /sub/.test(diff.diff), 'diff mentions the change');
    assert(Array.isArray(diff.changed_paths) && diff.changed_paths.includes('src/calc.py'), 'diff changed paths');
    console.log('PASS retained diff: ' + (diff.stat || ''));
    console.log('--- diff ---\n' + diff.diff.split('\n').slice(0, 20).join('\n') + '\n------------');

    const missions = await api.connection.missionList();
    assert(missions.some((mission) => mission.id === missionId), 'mission appears in the persistent list');
    console.log('PASS persistent mission list contains #' + missionId);

    // The dashboard must receive the detail + diff like the real chat UI.
    await vscode.commands.executeCommand('nlCodingAgent.startChat');
    await vscode.commands.executeCommand('workbench.view.extension.nlCodingAgent');
    await vscode.commands.executeCommand('nlCodingAgent.chat.focus').then(undefined, () => undefined);
    await waitFor(() => api.chat.debugState.resolved, 20000, 'webview view');
    await api.selectMission(missionId);
    await waitFor(() => api.chat.debugState.posted.some((message) =>
        message.type === 'state' && message.payload && message.payload.selected &&
        message.payload.selected.detail && message.payload.selected.detail.mission.id === missionId), 20000,
        'dashboard selection state');
    const selectedState = api.chat.debugState.posted.filter((message) =>
        message.type === 'state' && message.payload && message.payload.selected).pop();
    assert(selectedState.payload.selected.detail.verification_runs.length >= 2, 'dashboard got verification runs');
    assert(selectedState.payload.selected.diff && selectedState.payload.selected.diff.ok, 'dashboard got the diff');
    console.log('PASS dashboard received mission detail + diff');

    const pid = api.connection.childPid;
    await api.shutdown();
    await waitFor(() => {
        try { process.kill(pid, 0); return false; } catch { return true; }
    }, 10000, 'python child exit');
    console.log('PASS shutdown released python child ' + pid);
    console.log('== MISSION-ACCEPTANCE-PASS ==');
}

module.exports = { run };
