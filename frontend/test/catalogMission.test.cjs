/**
 * Realistic multi-module mission acceptance (Gate C, development workbench).
 *
 * Fixture: a small catalog package with models, repository, service and API.
 * The reservation feature spans three source modules and starts with a genuinely
 * red test suite. The mission planner must create dependent subtasks, the Flow
 * must repair real verification failures, and promotion may happen only after
 * candidate+oracle tests and reviewer approval.
 */
'use strict';

const assert = require('assert');
const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');

const EXTENSION_NAME = 'nl-coding-agent';
const GOAL = [
    'Create the new reservation feature across catalog/reservation_repository.py, catalog/reservation_service.py and catalog/reservation_api.py.',
    'ReservationRepository must store Reservation objects and provide add(product_id, quantity, created_at, expires_at), get(reservation_id), remove(reservation_id) -> bool, list_active(product_id, now) and expire(now) -> list of removed reservations.',
    'ReservationService must take the existing CatalogRepository plus a ReservationRepository and provide reserve(product_id, quantity, now=None, ttl=30), release(reservation_id), expire(now=None) and available(product_id, now=None).',
    'Reservations must reduce available stock; reservations with expires_at <= now must no longer block stock; release returns True only for a known reservation; expire returns the number removed.',
    'reservation_api must provide api_reserve(service, product_id, quantity, now=None, ttl=30), api_release(service, reservation_id) and api_available(service, product_id, now=None).',
    'Use the existing catalog.models and catalog.repository modules; preserve existing product APIs/tests. Change only the three new reservation modules.'
].join(' ');
const DEVELOPER = 'ollama/qwen3.5:9b';
const REVIEWER = 'ollama/qwen3.5:9b';

function sleep(ms) { return new Promise((resolve) => setTimeout(resolve, ms)); }

async function waitFor(predicate, timeoutMs, label, intervalMs) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
        if (await predicate()) { return; }
        await sleep(intervalMs || 250);
    }
    throw new Error('timed out waiting for ' + label);
}

function findExtension() {
    const direct = vscode.extensions.getExtension('nlcodingagent.' + EXTENSION_NAME);
    return direct || vscode.extensions.all.find((item) =>
        item.packageJSON && item.packageJSON.name === EXTENSION_NAME);
}

function projectPython(projectRoot) {
    const repoPython = path.resolve(__dirname, '..', '..', 'python', 'python.exe');
    return fs.existsSync(repoPython) ? repoPython : 'python';
}

function runPytest(projectRoot) {
    const result = spawnSync(projectPython(projectRoot), ['-m', 'pytest', '-q', '-p', 'no:cacheprovider'],
        { cwd: projectRoot, encoding: 'utf8', timeout: 120000 });
    return { code: result.status, stdout: String(result.stdout || ''), stderr: String(result.stderr || '') };
}

async function run() {
    console.log('== NL Code realistic multi-module mission acceptance ==');
    const extension = findExtension();
    assert(extension, 'extension not found');
    const api = await extension.activate();
    const folders = vscode.workspace.workspaceFolders || [];
    assert(folders.length === 1, 'one isolated workspace folder is required');
    const projectRoot = folders[0].uri.fsPath;
    assert(fs.existsSync(path.join(projectRoot, 'catalog', 'service.py')), 'catalog fixture');
    const baseline = runPytest(projectRoot);
    assert(baseline.code !== 0, 'fixture must start with a genuinely red test suite');
    console.log('PASS baseline suite is red: ' + (baseline.stdout || '').split('\n').slice(-2).join(' '));

    await api.connect();
    const status = await api.getStatus();
    assert.strictEqual(status.executionEnabled, true, 'mission execution enabled');
    console.log('mission routes: ' + DEVELOPER + ' -> ' + REVIEWER);

    const started = await api.startMission({ goal: GOAL, developerModel: DEVELOPER, reviewerModel: REVIEWER });
    assert(started && Number.isInteger(started.missionId), 'mission id returned');
    const missionId = started.missionId;
    console.log('PASS mission dispatched from NL Chat controller: #' + missionId);

    const deadline = Date.now() + 900000;
    let detail = null;
    let last = '';
    while (Date.now() < deadline) {
        detail = await api.getMissionDetail(missionId);
        const current = detail.mission.status;
        if (current !== last) {
            console.log('status ' + current + ' · tasks ' + detail.progress.completed + '/' + detail.progress.total);
            last = current;
        }
        if (['completed', 'failed', 'blocked', 'interrupted'].includes(current)) { break; }
        await sleep(2000);
    }
    assert(detail, 'mission detail');
    console.log('final: ' + detail.mission.status + ' · ' + detail.mission.review_verdict +
        ' · ' + detail.mission.promotion_status + ' · flow ' + detail.mission.flow_id);
    console.log('tasks: ' + detail.tasks.map((task) => task.agent_role + ':' + task.status).join(', '));
    console.log('handoffs: ' + detail.handoffs.map((item) => item.from_role + '->' + item.to_role).join(', '));
    console.log('verification: ' + detail.verification_runs.map((run) =>
        (run.passed ? 'PASS' : 'FAIL') + ' ' + String(run.command).split(' ')[0]).join(', '));

    assert.strictEqual(detail.mission.status, 'completed',
        'mission completed: ' + detail.mission.result_summary);
    assert.strictEqual(detail.mission.review_verdict, 'APPROVE', 'reviewer approved');
    assert.strictEqual(detail.mission.promotion_status, 'promoted', 'promoted only after verification');
    assert(detail.mission.flow_id, 'CrewAI Flow id persisted');

    const roles = detail.tasks.map((task) => task.agent_role);
    const developers = roles.filter((role) => role === 'developer').length;
    assert(roles.includes('architect') && roles.includes('tester') && roles.includes('reviewer'));
    assert(developers >= 3, 'three source modules produce multiple developer subtasks: ' + roles.join(','));
    assert(detail.tasks.every((task) => task.status === 'completed'),
        'every planned task completed');
    console.log('PASS dynamic dependent team: ' + roles.join(' -> '));

    const pairs = detail.handoffs.map((item) => item.from_role + '->' + item.to_role);
    for (const required of ['architect->developer', 'developer->developer',
        'developer->tester', 'tester->reviewer', 'reviewer->orchestrator']) {
        assert(pairs.includes(required), 'missing handoff ' + required);
    }
    const failedRuns = detail.verification_runs.filter((run) => !run.passed);
    assert(failedRuns.length >= 1, 'at least one real verification failure was recorded');
    assert(pairs.includes('tester->debugger') || detail.handoffs.some((item) =>
        item.from_role === 'debugger'), 'real repair/debugger handoff observed');
    console.log('PASS real failure + repair branch observed (' + failedRuns.length + ' red run)');

    const models = detail.model_bindings || {};
    assert(models.developer && models.reviewer && models.architect,
        'ModelRouter role snapshots');
    const modelled = detail.attempts.filter((attempt) => attempt.metadata && attempt.metadata.model);
    assert(modelled.length >= 3, 'attempt model evidence');
    console.log('models: ' + Object.keys(models).map((role) => role + '=' + models[role].model_name).join(', '));

    const live = runPytest(projectRoot);
    assert.strictEqual(live.code, 0, 'final project tests pass: ' + live.stdout + live.stderr);
    const service = fs.readFileSync(path.join(projectRoot, 'catalog', 'reservation_service.py'), 'utf8');
    const apiText = fs.readFileSync(path.join(projectRoot, 'catalog', 'reservation_api.py'), 'utf8');
    const repositoryText = fs.readFileSync(path.join(projectRoot, 'catalog', 'reservation_repository.py'), 'utf8');
    assert(/def\s+reserve\s*\(/.test(service) && /def\s+expire\s*\(/.test(service),
        'live reservation_service.py has reserve/expire');
    assert(/def\s+api_reserve\s*\(/.test(apiText), 'live reservation_api.py has api_reserve');
    assert(/def\s+add\s*\(/.test(repositoryText), 'live reservation_repository.py has add');
    console.log('PASS live multi-module implementation promoted; suite green');

    const candidate = detail.verification_runs.filter((run) => String(run.command).startsWith('verify:candidate'));
    const oracle = detail.verification_runs.filter((run) => String(run.command).startsWith('verify:oracle'));
    assert(candidate.some((run) => run.passed) && oracle.some((run) => run.passed),
        'independent candidate and oracle suites eventually passed');

    const diff = await api.getCandidateDiff(missionId);
    assert(diff && diff.ok === true, 'retained diff available');
    assert(/catalog\/reservation_service\.py/.test(diff.diff) &&
        /catalog\/reservation_repository\.py/.test(diff.diff) &&
        /catalog\/reservation_api\.py/.test(diff.diff), 'diff spans all three new modules');
    console.log('PASS retained multi-module diff: ' + (diff.stat || ''));

    await vscode.commands.executeCommand('nlCodingAgent.startChat');
    await vscode.commands.executeCommand('workbench.view.extension.nlCodingAgentChat');
    await vscode.commands.executeCommand('nlCodingAgent.chat.focus').then(undefined, () => undefined);
    await waitFor(() => api.chat.debugState.resolved, 20000, 'webview view');
    await api.selectMission(missionId);
    await waitFor(() => api.chat.debugState.posted.some((message) =>
        message.type === 'state' && message.payload && message.payload.selected &&
        message.payload.selected.detail && message.payload.selected.detail.mission.id === missionId),
        20000, 'dashboard selection');
    const selected = api.chat.debugState.posted.filter((message) =>
        message.type === 'state' && message.payload && message.payload.selected).pop().payload.selected;
    assert(selected.detail.verification_runs.some((run) => !run.passed), 'dashboard got red run');
    assert(selected.diff && selected.diff.ok, 'dashboard got diff');
    console.log('PASS dashboard shows multi-subtask mission, repair evidence and diff');

    const pid = api.connection.childPid;
    await api.shutdown();
    await waitFor(() => {
        try { process.kill(pid, 0); return false; } catch { return true; }
    }, 10000, 'python child exit');
    console.log('PASS shutdown released python child ' + pid);
    console.log('== CATALOG-MISSION-ACCEPTANCE-PASS ==');
}

module.exports = { run };

