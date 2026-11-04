'use strict';
const assert = require('assert');
const Module = require('module');
const original = Module._load;
Module._load = function (name, ...args) { return name === 'vscode' ? {} : original.call(this, name, ...args); };
const { ChatProvider } = require('../out/chatProvider.js');
Module._load = original;

async function main() {
    let release;
    const checkpoint = new Promise((resolve) => { release = resolve; });
    const submissions = [];
    const connection = {
        sessionListeners: new Set(), supportsSessionRuntime: true, state: 'ready', projectRoot: 'K:/fixture',
        executionAllowed: true, checkpointCreate: () => checkpoint, connect: async () => {},
        projectContext: async () => ({ project: { id: 1, root: 'K:/fixture' } }),
        sessionSubmit: async (...args) => { submissions.push(args); return { run_id: 'accepted' }; },
        sessionSnapshot: async (sid) => ({ session_id: sid, runs: [], messages: [], activity: [], live_text: '' })
    };
    const provider = new ChatProvider({}, connection, { appendLine() {} }, 1000);
    provider.currentSessionId = 'A';
    const pending = provider.handleUserMessage('Inspect this module');
    provider.currentSessionId = 'B';
    release();
    await pending;
    assert.strictEqual(submissions[0][0], 'A', 'an in-flight send stays bound to its original conversation');
    assert.strictEqual(provider.currentSessionId, 'B', 'the selected conversation stays under user control');
    let unblockMission;
    const missionCheckpoint = new Promise((resolve) => { unblockMission = resolve; });
    const missions = [];
    provider.ensureExecution = () => missionCheckpoint;
    provider.refreshMissions = async () => {};
    provider.startMonitoring = () => { throw new Error('runtime missions must not use UI polling'); };
    connection.startMission = async (input) => {
        missions.push(input);
        return { mission_id: 1, session_id: input.sessionId, session_run_id: 'mission-turn' };
    };
    provider.currentSessionId = 'A';
    const starting = provider.startMission({ goal: 'Fix module', developerModel: 'ollama/local', reviewerModel: 'ollama/local' }, true);
    provider.currentSessionId = 'B';
    unblockMission();
    await starting;
    assert.strictEqual(missions[0].sessionId, 'A', 'an explicit mission keeps the session captured before awaits');
    assert(missions[0].requestId, 'explicit mission submission carries an idempotency key');
    assert.strictEqual(provider.currentSessionId, 'B');
    provider.dispose();
    console.log('SESSION-CONTROLLER-TESTS-PASS');
}
main().catch((error) => { console.error(error); process.exitCode = 1; });
