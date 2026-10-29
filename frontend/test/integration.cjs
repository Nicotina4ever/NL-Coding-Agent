/**
 * Real integration acceptance for the VS Code frontend backend.
 *
 * Runs outside VS Code: spawns the actual Python MCP engine through the same
 * EngineConnection the extension uses, verifies the MCP handshake, real tool
 * discovery, project binding, a real Ollama chat turn, cross-project refusal,
 * project isolation, and process shutdown.
 *
 * Usage: node test/integration.cjs
 */
'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const frontendDir = path.resolve(__dirname, '..');
const repoRoot = path.resolve(frontendDir, '..');
const { EngineConnection, EngineError, resolveEngineLocation } = require(path.join(frontendDir, 'out', 'backend.js'));

const scratch = path.join(repoRoot, '.workspace', 'temp', 'frontend-accept', 'integration');
const projectA = path.join(scratch, 'project-a');
const projectB = path.join(scratch, 'project-b');
const dataDir = path.join(scratch, 'data');
const workspaceDir = path.join(scratch, 'workspace');

function log(line) {
    console.log(line);
}

function assertPathEqual(actual, expected, label) {
    const left = path.resolve(actual).toLowerCase();
    const right = path.resolve(expected).toLowerCase();
    assert.strictEqual(left, right, `${label}: expected ${expected}, got ${actual}`);
}

function prepare() {
    fs.rmSync(scratch, { recursive: true, force: true });
    fs.mkdirSync(projectA, { recursive: true });
    fs.mkdirSync(projectB, { recursive: true });
    fs.mkdirSync(dataDir, { recursive: true });
    fs.mkdirSync(workspaceDir, { recursive: true });
    fs.writeFileSync(path.join(projectA, 'README.md'), '# Project A\nIntegration acceptance fixture.\n');
    fs.writeFileSync(path.join(projectA, 'hello.py'), 'def hello():\n    return "hello"\n');
    fs.writeFileSync(path.join(projectB, 'notes.txt'), 'Project B fixture.\n');
}

function engineOptions(projectRoot) {
    return {
        engineRoot: '',
        extensionPath: frontendDir,
        projectRoot,
        env: {
            NL_DATA_DIR: dataDir,
            NL_WORKSPACE_DIR: workspaceDir,
            NL_MODELS_CONFIG: path.join(repoRoot, 'config', 'models.yaml')
        },
        requestTimeoutMs: 240000,
        log: (line) => log('    [engine] ' + line)
    };
}

async function waitForProcessExit(pid, timeoutMs) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
        try {
            process.kill(pid, 0);
        } catch {
            return true;
        }
        await new Promise((resolve) => setTimeout(resolve, 100));
    }
    return false;
}

async function main() {
    log('== NL Coding Agent frontend integration acceptance ==');
    prepare();

    // 1. Engine location is resolved from the extension installation, not the project.
    const location = resolveEngineLocation({ extensionPath: frontendDir });
    assertPathEqual(location.engineRoot, repoRoot, 'engine root');
    assert(fs.existsSync(location.pythonPath), 'python.exe exists');
    assert(fs.existsSync(location.nlAgentPath), 'nl_agent.py exists');
    log('PASS engine location: ' + location.engineRoot);

    let invalid = false;
    try {
        resolveEngineLocation({ extensionPath: frontendDir, engineRoot: path.join(scratch, 'missing-engine') });
    } catch (error) {
        invalid = error instanceof EngineError && error.code === 'engine-invalid';
    }
    assert(invalid, 'invalid explicit engineRoot must fail closed');
    log('PASS invalid engine root rejected');

    // 2. Workspace is required (the engine binds one project per process).
    const noWorkspace = new EngineConnection({ extensionPath: frontendDir, projectRoot: '' });
    let noWorkspaceError = null;
    try {
        await noWorkspace.connect();
    } catch (error) {
        noWorkspaceError = error;
    }
    assert(noWorkspaceError instanceof EngineError && noWorkspaceError.code === 'no-workspace');
    log('PASS missing workspace rejected before spawning');

    const first = new EngineConnection(engineOptions(projectA));
    const second = new EngineConnection(engineOptions(projectB));
    try {
        // 3. MCP initialization + tool discovery.
        await first.connect();
        assert.strictEqual(first.state, 'ready', 'first connection ready');
        const engine = first.engineInfo;
        assert(engine && engine.name === 'NL Coding Engine', 'serverInfo name: ' + JSON.stringify(engine));
        log(`PASS MCP initialize: ${engine.name} ${engine.version} (pid ${first.childPid})`);

        const tools = await first.listTools();
        const names = tools.map((tool) => tool.name);
        for (const required of ['project_context', 'nlc_converse', 'mission_list', 'mission_status',
            'mission_events', 'candidate_diff', 'start_mission', 'cancel_mission']) {
            assert(names.includes(required), `missing tool ${required}`);
        }
        log(`PASS tools discovered (${tools.length}): ${names.join(', ')}`);

        // 4. Safe read-only tool with a real result.
        const context = await first.projectContext();
        assert(Number.isInteger(context.project.id) && context.project.id > 0, 'project id');
        assertPathEqual(context.project.root, projectA, 'project A root');
        assert.strictEqual(context.execution_enabled, false, 'engine is read-only by default');
        const missions = await first.callJson('mission_list', {});
        assert(Array.isArray(missions.missions), 'mission_list shape');
        log(`PASS project_context: project #${context.project.id} root=${context.project.root} (read-only)`);
        log(`PASS read-only tool result: mission_list -> ${JSON.stringify(missions)}`);

        // 5. Real Ollama chat turn.
        const reply = await first.converse(context.project.id, 'Reply with exactly: NLCHAT-OK');
        assert.strictEqual(reply.ok, true, 'converse ok');
        assert(/NLCHAT-OK/.test(reply.reply), 'model reply: ' + JSON.stringify(reply.reply));
        const last = reply.messages[reply.messages.length - 1];
        assert(last && last.role === 'assistant' && /NLCHAT-OK/.test(last.content), 'persisted assistant message');
        log(`PASS real Ollama chat reply: ${JSON.stringify(reply.reply)}`);

        // 6. The server refuses another project's id (cross-project isolation).
        let refused = null;
        try {
            await first.converse(context.project.id + 1, 'this must never reach a model');
        } catch (error) {
            refused = error;
        }
        assert(refused instanceof EngineError && refused.code === 'tool-error', 'cross-project call rejected');
        assert(/bound to this server/i.test(refused.message), 'cross-project error text: ' + refused.message);
        assert(!fs.existsSync(path.join(dataDir, 'chat', `project-${context.project.id + 1}.json`)),
            'cross-project chat history must not be written');
        log('PASS cross-project project_id rejected by the engine');

        // 7. Workspace -> project mapping is per connection and isolated.
        await second.connect();
        const otherContext = await second.projectContext();
        assert.notStrictEqual(otherContext.project.id, context.project.id, 'second project has its own id');
        assertPathEqual(otherContext.project.root, projectB, 'project B root');
        const otherMissions = await second.callJson('mission_list', {});
        assert.deepStrictEqual(otherMissions.missions, [], 'project B sees no project A missions');
        log(`PASS workspace isolation: project A #${context.project.id}, project B #${otherContext.project.id}`);

        // 8. Shutdown releases the Python child process.
        const pids = [first.childPid, second.childPid];
        assert(pids.every((pid) => typeof pid === 'number' && pid > 0), 'child pids');
        await first.close();
        await second.close();
        assert.strictEqual(first.state, 'closed', 'first closed');
        assert.strictEqual(second.state, 'closed', 'second closed');
        for (const pid of pids) {
            assert(await waitForProcessExit(pid, 10000), `python child ${pid} still alive after close`);
        }
        log(`PASS shutdown released child processes ${pids.join(', ')}`);

        fs.writeFileSync(path.join(scratch, 'result.json'), JSON.stringify({
            ok: true,
            engine: location.engineRoot,
            projectA: context.project.id,
            projectB: otherContext.project.id,
            reply: reply.reply,
            tools: names
        }, null, 2));
    } finally {
        try { await first.close(); } catch { /* already closed */ }
        try { await second.close(); } catch { /* already closed */ }
    }

    log('== INTEGRATION-ACCEPTANCE-PASS ==');
}

main().then(
    () => process.exit(0),
    (error) => {
        console.error('INTEGRATION-ACCEPTANCE-FAIL');
        console.error(error && error.stack ? error.stack : error);
        process.exit(1);
    }
);
