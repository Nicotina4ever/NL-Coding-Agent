/**
 * Stop + resume acceptance inside VS Code Insiders.
 *
 * Dispatches a real mission, requests a cooperative stop immediately, verifies
 * the engine interrupts without touching the live tree and retains the mission,
 * then resumes the same persisted mission and verifies it completes/promotes.
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
const TERMINAL = ['completed', 'failed', 'blocked', 'interrupted'];

function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitFor(predicate, timeoutMs, label, intervalMs) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
        if (await predicate()) {
            return;
        }
        await sleep(intervalMs || 500);
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

async function waitForTerminal(api, missionId, timeoutMs) {
    let detail = null;
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
        detail = await api.getMissionDetail(missionId);
        if (TERMINAL.includes(detail.mission.status)) {
            return detail;
        }
        await sleep(1000);
    }
    return detail;
}

async function run() {
    console.log('== NL Coding Agent stop/resume acceptance ==');
    const extension = findExtension();
    assert(extension, 'extension not found');
    const api = await extension.activate();
    const folders = vscode.workspace.workspaceFolders || [];
    assert(folders.length === 1, 'one isolated workspace folder is required');
    const projectRoot = folders[0].uri.fsPath;
    await api.connect();
    const status = await api.getStatus();
    assert.strictEqual(status.executionEnabled, true, 'execution must be enabled');

    const started = await api.startMission({ goal: GOAL, developerModel: DEVELOPER, reviewerModel: REVIEWER });
    assert(started && started.missionId, 'mission id');
    const missionId = started.missionId;
    console.log('PASS mission dispatched: #' + missionId);

    const cancelled = await api.cancelMission(missionId);
    assert.strictEqual(cancelled, true, 'cooperative stop accepted');
    console.log('PASS stop accepted for #' + missionId);

    const interrupted = await waitForTerminal(api, missionId, 120000);
    assert(interrupted, 'mission detail after stop');
    console.log('status after stop: ' + interrupted.mission.status);
    assert.strictEqual(interrupted.mission.status, 'interrupted', 'mission interrupted at a safe checkpoint');
    const liveSource = fs.readFileSync(path.join(projectRoot, 'src', 'calc.py'), 'utf8');
    assert(!/def\s+sub\s*\(/.test(liveSource), 'interrupted mission did not touch the live tree');
    console.log('PASS live tree untouched by the interrupted mission');

    // Let the sequential scheduler retire the interrupted task before reusing
    // the same mission id (the GUI naturally has this gap between user actions).
    await sleep(3000);
    const resumed = await api.resumeMission(missionId);
    assert.strictEqual(resumed, true, 'resume dispatched');
    // The persisted row stays 'interrupted' until the orchestrator starts the
    // new run; wait for that transition before looking for a terminal state.
    await waitFor(async () => {
        const current = await api.getMissionDetail(missionId);
        return current.mission.status !== 'interrupted' || Number(current.mission.resume_count) >= 1;
    }, 60000, 'resume to start running', 1000);
    const completed = await waitForTerminal(api, missionId, 300000);
    assert(completed, 'mission detail after resume');
    console.log('status after resume: ' + completed.mission.status + ' · verdict ' + completed.mission.review_verdict +
        ' · promotion ' + completed.mission.promotion_status + ' · resumes ' + completed.mission.resume_count);
    assert.strictEqual(completed.mission.status, 'completed', 'resumed mission completed: ' + completed.mission.result_summary);
    assert.strictEqual(completed.mission.review_verdict, 'APPROVE', 'reviewer approved after resume');
    assert(Number(completed.mission.resume_count) >= 1, 'resume count incremented');
    const finalSource = fs.readFileSync(path.join(projectRoot, 'src', 'calc.py'), 'utf8');
    assert(/def\s+sub\s*\(/.test(finalSource), 'resumed mission promoted sub()');
    console.log('PASS resumed mission completed and promoted the change');

    const pid = api.connection.childPid;
    await api.shutdown();
    await waitFor(() => {
        try { process.kill(pid, 0); return false; } catch { return true; }
    }, 10000, 'python child exit');
    console.log('PASS shutdown released python child ' + pid);
    console.log('== STOP-RESUME-ACCEPTANCE-PASS ==');
}

module.exports = { run };
