/**
 * Verify confirmed single/batch mission deletion through the installed NL Coder
 * controller and real project-bound engine while mission execution is disabled.
 */
'use strict';

const assert = require('assert');
const { spawnSync } = require('child_process');
const vscode = require('vscode');

const EXTENSION_NAME = 'nl-coding-agent';

function findExtension() {
    const direct = vscode.extensions.getExtension('nlcodingagent.' + EXTENSION_NAME);
    if (direct) {
        return direct;
    }
    return vscode.extensions.all.find((item) =>
        item.packageJSON && item.packageJSON.name === EXTENSION_NAME);
}

function createPendingMissions(api, projectId) {
    const location = api.connection.engineLocation;
    assert(location && location.pythonPath && location.engineRoot, 'engine Python and root are resolved');
    const code = [
        'import json, sys',
        'sys.path.insert(0, sys.argv[1])',
        'from nl_coding_agent.core.permissions import DELETE, grant',
        'from nl_coding_agent.persistence.missions import create_mission',
        'project_id = int(sys.argv[2])',
        'grant(DELETE, project_id=project_id, source="installed-acceptance")',
        'ids = [create_mission(project_id, "Pending acceptance " + str(i), "Not started") for i in range(3)]',
        'print(json.dumps(ids))'
    ].join('\n');
    const result = spawnSync(location.pythonPath, ['-c', code, location.engineRoot, String(projectId)], {
        cwd: location.engineRoot,
        env: process.env,
        encoding: 'utf8',
        windowsHide: true
    });
    assert.strictEqual(result.status, 0, 'pending missions created: ' + result.stderr);
    return JSON.parse(result.stdout.trim());
}

async function run() {
    const extension = findExtension();
    assert(extension, 'installed NL Coder extension found');
    const api = await extension.activate();
    try {
        await api.connect();
        assert.strictEqual(api.connection.executionAllowed, false,
            'mission execution remains disabled');
        const context = await api.connection.projectContext();
        const ids = createPendingMissions(api, context.project.id);
        const confirmations = [];
        const originalConfirm = api.chat.confirm;
        api.chat.confirm = async (message, detail, action) => {
            confirmations.push({ message, detail, action });
            return action === 'Delete permanently';
        };
        try {
            await api.chat.deleteSelectedMissions([ids[0]]);
            assert.strictEqual((await api.connection.missionList({ includeArchived: true }))
                .some((mission) => mission.id === ids[0]), false,
            'single pending mission is removed through the controller');
            await api.chat.deleteSelectedMissions(ids.slice(1));
            const remaining = await api.connection.missionList({ includeArchived: true });
            assert(!ids.some((id) => remaining.some((mission) => mission.id === id)),
                'batch pending missions are removed through the controller');
            assert.strictEqual(confirmations.length, 2, 'single and batch actions are confirmed');
            assert(confirmations.every((item) => item.detail.includes('pending')),
                'confirmation summarizes the selected pending missions');
            assert.strictEqual(api.connection.executionAllowed, false,
                'deletion never enables mission execution');
        } finally {
            api.chat.confirm = originalConfirm;
        }
        console.log('== MISSION-DELETE-ACCEPTANCE-PASS ==');
    } finally {
        await api.shutdown();
    }
}

module.exports = { run };
