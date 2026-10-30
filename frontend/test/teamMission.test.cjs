/**
 * Real multi-agent team mission acceptance inside VS Code Insiders.
 *
 * The objective spans two source files, so the proportional planner must add a
 * read-only architect in front of developer -> deterministic tester -> reviewer.
 * The test verifies actual per-role execution, handoffs, model assignments,
 * attempt metadata, independent verification, promotion, and the dashboard view.
 */
'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');

const EXTENSION_NAME = 'nl-coding-agent';
const GOAL = 'In src/calc.py add sub(a, b) returning a - b. In src/stats.py add mean(values) returning the arithmetic mean. Preserve all existing tests. Change only src/calc.py and src/stats.py.';
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
        await sleep(intervalMs || 250);
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
    console.log('== NL Coder multi-agent team mission acceptance ==');
    const extension = findExtension();
    assert(extension, 'extension not found');
    const api = await extension.activate();
    const folders = vscode.workspace.workspaceFolders || [];
    assert(folders.length === 1, 'one isolated workspace folder is required');
    const projectRoot = folders[0].uri.fsPath;
    assert(fs.existsSync(path.join(projectRoot, 'src', 'calc.py')), 'fixture calc.py');
    assert(fs.existsSync(path.join(projectRoot, 'src', 'stats.py')), 'fixture stats.py');

    await api.connect();
    const status = await api.getStatus();
    assert.strictEqual(status.executionEnabled, true, 'mission execution enabled');
    console.log('mission routes: ' + DEVELOPER + ' -> ' + REVIEWER);

    const started = await api.startMission({ goal: GOAL, developerModel: DEVELOPER, reviewerModel: REVIEWER });
    assert(started && Number.isInteger(started.missionId), 'mission id returned');
    const missionId = started.missionId;
    console.log('PASS mission dispatched from Chat controller: #' + missionId);

    const deadline = Date.now() + 600000;
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
    console.log('models: ' + JSON.stringify(detail.model_bindings || {}));
    console.log('verification: ' + detail.verification_runs.map((run) =>
        (run.passed ? 'PASS' : 'FAIL') + ' ' + run.command.split(' ')[0]).join(', '));

    assert.strictEqual(detail.mission.status, 'completed',
        'mission completed: ' + detail.mission.result_summary);
    assert.strictEqual(detail.mission.review_verdict, 'APPROVE', 'reviewer approved');
    assert.strictEqual(detail.mission.promotion_status, 'promoted', 'candidate promoted');

    const roles = detail.tasks.map((task) => task.agent_role);
    assert(roles.includes('architect'), 'proportional planner added architect: ' + roles.join(','));
    assert(roles.includes('developer') && roles.includes('tester') && roles.includes('reviewer'));
    assert(roles.filter((role) => role === 'developer').length >= 2,
        'one developer subtask per source path');
    assert(detail.tasks.length >= 5, 'team has proportional dependent roles');
    assert(detail.tasks.every((task) => task.status === 'completed'), 'every planned agent completed');
    console.log('PASS proportional team: ' + roles.join(' -> '));

    const handoffPairs = detail.handoffs.map((item) => item.from_role + '->' + item.to_role);
    for (const required of ['architect->developer', 'developer->developer',
        'developer->tester', 'tester->reviewer', 'reviewer->orchestrator']) {
        assert(handoffPairs.includes(required), 'missing handoff ' + required + ': ' + handoffPairs.join(', '));
    }
    const architectHandoff = detail.handoffs.find((item) => item.from_role === 'architect');
    assert(architectHandoff && architectHandoff.payload && String(architectHandoff.payload.notes || '').trim().length > 20,
        'architect delivered real notes');
    const developerPaths = detail.handoffs
        .filter((item) => item.from_role === 'developer')
        .flatMap((item) => (item.payload && item.payload.changed_paths) || []);
    assert(new Set(developerPaths).size >= 2,
        'developer handoffs cover both changed files: ' + JSON.stringify(developerPaths));
    console.log('PASS persisted handoffs with real work payloads');

    assert(detail.model_bindings && detail.model_bindings.developer && detail.model_bindings.reviewer,
        'ModelRouter bindings persisted');
    assert(detail.model_bindings.architect, 'architect binding persisted');
    assert(String(detail.model_bindings.developer.model_name || '').includes('qwen2.5-coder'),
        'developer model binding: ' + JSON.stringify(detail.model_bindings.developer));
    console.log('PASS ModelRouter role bindings persisted');

    const modelledAttempts = detail.attempts.filter((attempt) =>
        attempt.metadata && attempt.metadata.model);
    assert(modelledAttempts.length >= 3, 'attempt metadata records model evidence');
    assert(detail.attempts.every((attempt) => attempt.status !== 'failed' || attempt.metadata),
        'attempt evidence retained for failures too');
    console.log('PASS per-attempt model/usage evidence: ' + modelledAttempts.map((attempt) =>
        attempt.agent_role + '=' + attempt.metadata.model).join(', '));

    const changed = detail.mission.changed_paths || [];
    assert(changed.includes('src/calc.py') && changed.includes('src/stats.py'),
        'both files promoted: ' + changed.join(','));
    const calc = fs.readFileSync(path.join(projectRoot, 'src', 'calc.py'), 'utf8');
    const stats = fs.readFileSync(path.join(projectRoot, 'src', 'stats.py'), 'utf8');
    assert(/def\s+sub\s*\(/.test(calc), 'live calc.py contains sub()');
    assert(/def\s+mean\s*\(/.test(stats), 'live stats.py contains mean()');
    console.log('PASS live files promoted: src/calc.py + src/stats.py');

    const candidate = detail.verification_runs.filter((run) => run.command.startsWith('verify:candidate'));
    const oracle = detail.verification_runs.filter((run) => run.command.startsWith('verify:oracle'));
    assert(candidate.length >= 1 && candidate.every((run) => run.passed), 'candidate tests passed');
    assert(oracle.length >= 1 && oracle.every((run) => run.passed), 'oracle tests passed');
    console.log('PASS independent candidate + oracle verification');

    const diff = await api.getCandidateDiff(missionId);
    assert(diff && diff.ok === true, 'retained diff available');
    assert(/src\/calc\.py/.test(diff.diff) && /src\/stats\.py/.test(diff.diff),
        'diff includes both files');
    console.log('PASS retained diff: ' + (diff.stat || ''));

    await vscode.commands.executeCommand('nlCodingAgent.startChat');
    await vscode.commands.executeCommand('workbench.view.extension.nlCodingAgentChat');
    await vscode.commands.executeCommand('nlCodingAgent.chat.focus').then(undefined, () => undefined);
    await waitFor(() => api.chat.debugState.resolved, 20000, 'webview view');
    await api.selectMission(missionId);
    await waitFor(() => api.chat.debugState.posted.some((message) =>
        message.type === 'state' && message.payload && message.payload.selected &&
        message.payload.selected.detail && message.payload.selected.detail.mission.id === missionId), 20000,
        'dashboard selection state');
    const selected = api.chat.debugState.posted.filter((message) =>
        message.type === 'state' && message.payload && message.payload.selected).pop().payload.selected;
    assert(selected.detail.model_bindings && selected.detail.model_bindings.architect,
        'dashboard received model assignments');
    assert(selected.detail.attempts.some((attempt) => attempt.metadata && attempt.metadata.model),
        'dashboard received attempt model evidence');
    assert(selected.detail.verification_runs.length >= 2, 'dashboard received verification');
    assert(selected.diff && selected.diff.ok, 'dashboard received diff');
    console.log('PASS dashboard shows completed mission, handoffs, models, verification and diff');

    const pid = api.connection.childPid;
    await api.shutdown();
    await waitFor(() => {
        try { process.kill(pid, 0); return false; } catch { return true; }
    }, 10000, 'python child exit');
    console.log('PASS shutdown released python child ' + pid);
    console.log('== TEAM-MISSION-ACCEPTANCE-PASS ==');
}

module.exports = { run };

