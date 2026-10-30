/**
 * Acceptance on the ORIGINAL strict catalog fixture.
 *
 * The fixture and its tests are copied unchanged from
 * frontend/test/fixtures/catalog-original-strict.  No criteria are relaxed here:
 * the mission must implement the three existing modules, keep the existing API,
 * pass the original test suite, obtain reviewer approval and promote the live
 * candidate.  Initial red tests are part of the fixture.
 */
'use strict';

const assert = require('assert');
const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');

const EXTENSION_NAME = 'nl-coding-agent';
const GOAL = [
    'Implement reservation support in catalog/service.py, catalog/repository.py and catalog/api.py.',
    'Add CatalogService.reserve(product_id, quantity, now=None, ttl=30), release(reservation_id), expire(now=None) and available(product_id, now=None).',
    'Reservations must reduce available stock; a reservation whose expires_at is <= now must no longer block stock.',
    'release returns True only for a known reservation; expire returns the number of reservations removed.',
    'Add api.api_reserve(service, product_id, quantity, now=None, ttl=30), api.api_release(service, reservation_id) and api.api_available(service, product_id, now=None) using the same bootstrap service.',
    'Preserve the existing product API and all existing tests. Change only catalog/service.py, catalog/repository.py and catalog/api.py.'
].join(' ');
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
    return direct || vscode.extensions.all.find((item) =>
        item.packageJSON && item.packageJSON.name === EXTENSION_NAME);
}

function runPytest(projectRoot) {
    const repoPython = path.resolve(__dirname, '..', '..', 'python', 'python.exe');
    const python = fs.existsSync(repoPython) ? repoPython : 'python';
    const result = spawnSync(python, ['-m', 'pytest', '-q', '-p', 'no:cacheprovider'],
        { cwd: projectRoot, encoding: 'utf8', timeout: 120000 });
    return { code: result.status, stdout: String(result.stdout || ''), stderr: String(result.stderr || '') };
}

async function run() {
    console.log('== NL Code ORIGINAL strict multi-module mission acceptance ==');
    const extension = findExtension();
    assert(extension, 'extension not found');
    const api = await extension.activate();
    const folders = vscode.workspace.workspaceFolders || [];
    assert(folders.length === 1, 'one isolated workspace folder is required');
    const projectRoot = folders[0].uri.fsPath;
    for (const relative of ['catalog/service.py', 'catalog/repository.py',
        'catalog/api.py', 'tests/test_catalog.py']) {
        assert(fs.existsSync(path.join(projectRoot, relative)), 'original fixture ' + relative);
    }
    const baseline = runPytest(projectRoot);
    assert(baseline.code !== 0, 'original fixture must start red');
    console.log('PASS original strict fixture starts red: '
        + (baseline.stdout || '').split('\n').slice(-2).join(' '));

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
        if (['completed', 'failed', 'blocked', 'interrupted'].includes(current)) {
            break;
        }
        await sleep(2000);
    }
    assert(detail, 'mission detail');
    console.log('final: ' + detail.mission.status + ' · ' + detail.mission.review_verdict
        + ' · ' + detail.mission.promotion_status + ' · flow ' + detail.mission.flow_id);
    console.log('tasks: ' + detail.tasks.map((task) => task.agent_role + ':' + task.status).join(', '));
    console.log('handoffs: ' + detail.handoffs.map((item) => item.from_role + '->' + item.to_role).join(', '));
    console.log('verification: ' + detail.verification_runs.map((run) =>
        (run.passed ? 'PASS' : 'FAIL') + ' ' + String(run.command).split(' ')[0]).join(', '));
    if (detail.execution_errors && detail.execution_errors.length) {
        console.log('EXECUTION_ERRORS: ' + JSON.stringify(detail.execution_errors.map((item) => ({
            source: item.source, method: item.method, type: item.exception_type, message: item.message
        }))));
    }

    assert.strictEqual(detail.mission.status, 'completed',
        'original mission completed: ' + detail.mission.result_summary);
    assert.strictEqual(detail.mission.review_verdict, 'APPROVE', 'reviewer approved');
    assert.strictEqual(detail.mission.promotion_status, 'promoted', 'candidate promoted');
    assert(detail.mission.flow_id, 'Flow id persisted');
    assert(!(detail.execution_errors || []).length, 'no unexpected execution errors on success');

    const roles = detail.tasks.map((task) => task.agent_role);
    const developers = roles.filter((role) => role === 'developer').length;
    assert(roles.includes('architect') && roles.includes('tester') && roles.includes('reviewer'));
    assert(developers >= 3, 'three source modules produce multiple developer subtasks');
    assert(detail.tasks.every((task) => task.status === 'completed'), 'every planned task completed');
    console.log('PASS original strict dynamic team: ' + roles.join(' -> '));

    const pairs = detail.handoffs.map((item) => item.from_role + '->' + item.to_role);
    for (const required of ['architect->developer', 'developer->developer',
        'developer->tester', 'tester->reviewer', 'reviewer->orchestrator']) {
        assert(pairs.includes(required), 'missing handoff ' + required);
    }
    console.log('PASS original strict handoffs consumed');

    const live = runPytest(projectRoot);
    assert.strictEqual(live.code, 0, 'original strict tests pass: ' + live.stdout + live.stderr);
    const service = fs.readFileSync(path.join(projectRoot, 'catalog', 'service.py'), 'utf8');
    const repository = fs.readFileSync(path.join(projectRoot, 'catalog', 'repository.py'), 'utf8');
    const apiText = fs.readFileSync(path.join(projectRoot, 'catalog', 'api.py'), 'utf8');
    assert(/def\s+reserve\s*\(/.test(service) && /def\s+expire\s*\(/.test(service)
        && /def\s+available\s*\(/.test(service), 'live service implementation');
    assert(/def\s+save_reservation\s*\(/.test(repository)
        || /def\s+record_reservation\s*\(/.test(repository),
        'live repository reservation storage');
    assert(/def\s+api_reserve\s*\(/.test(apiText), 'live api helper');
    console.log('PASS original strict implementation promoted; unchanged suite green');

    const candidate = detail.verification_runs.filter((run) => String(run.command).startsWith('verify:candidate'));
    const oracle = detail.verification_runs.filter((run) => String(run.command).startsWith('verify:oracle'));
    assert(candidate.some((run) => run.passed) && oracle.some((run) => run.passed),
        'independent candidate and oracle suites passed');

    const diff = await api.getCandidateDiff(missionId);
    assert(diff && diff.ok === true, 'retained diff available');
    for (const relative of ['catalog/service.py', 'catalog/repository.py', 'catalog/api.py']) {
        assert(diff.diff.includes(relative), 'diff includes ' + relative);
    }
    console.log('PASS original strict diff: ' + (diff.stat || ''));

    await vscode.commands.executeCommand('nlCodingAgent.startChat');
    await vscode.commands.executeCommand('workbench.view.extension.nlCodingAgent');
    await vscode.commands.executeCommand('nlCodingAgent.chat.focus').then(undefined, () => undefined);
    await waitFor(() => api.chat.debugState.resolved, 20000, 'webview view');
    await api.selectMission(missionId);
    await waitFor(() => api.chat.debugState.posted.some((message) =>
        message.type === 'state' && message.payload && message.payload.selected &&
        message.payload.selected.detail && message.payload.selected.detail.mission.id === missionId),
        20000, 'dashboard selection');
    const selected = api.chat.debugState.posted.filter((message) =>
        message.type === 'state' && message.payload && message.payload.selected).pop().payload.selected;
    assert(selected.diff && selected.diff.ok, 'dashboard got diff');
    assert(!(selected.detail.execution_errors || []).length, 'dashboard shows no execution errors');
    console.log('PASS dashboard shows original strict mission and diff');

    const pid = api.connection.childPid;
    await api.shutdown();
    await waitFor(() => {
        try { process.kill(pid, 0); return false; } catch { return true; }
    }, 10000, 'python child exit');
    console.log('PASS shutdown released python child ' + pid);
    console.log('== ORIGINAL-STRICT-CATALOG-ACCEPTANCE-PASS ==');
}

module.exports = {
    run: async () => {
        try {
            await run();
        } catch (error) {
            const text = (error && error.stack) || String(error);
            try {
                fs.writeFileSync(path.join(__dirname, '..', '..', '.workspace', 'temp',
                    'original-test-error.txt'), text, 'utf8');
            } catch (ignored) {
                // best-effort diagnostics only
            }
            console.error('ORIGINAL-STRICT-ERROR: ' + text);
            throw error;
        }
    }
};
