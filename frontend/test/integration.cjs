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
const modelsConfig = path.join(scratch, 'models.yaml');
const mcpConfig = path.join(scratch, 'mcp_servers.json');

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
    fs.writeFileSync(path.join(projectA, 'notes.txt'),
        'The secret token is NLATTACH-47.\nSecond line for extraction.\n');
    fs.writeFileSync(path.join(projectB, 'notes.txt'), 'Project B fixture.\n');
    fs.writeFileSync(path.join(scratch, 'outside.txt'), 'outside the project root\n');
    fs.copyFileSync(path.join(repoRoot, 'config', 'models.yaml'), modelsConfig);
    fs.writeFileSync(mcpConfig, JSON.stringify({ servers: {} }, null, 2));
}

function engineOptions(projectRoot, extra = {}) {
    return {
        engineRoot: '',
        extensionPath: frontendDir,
        projectRoot,
        env: {
            NL_DATA_DIR: dataDir,
            NL_WORKSPACE_DIR: workspaceDir,
            NL_MODELS_CONFIG: modelsConfig,
            NL_MCP_CONFIG: mcpConfig
        },
        requestTimeoutMs: 240000,
        log: (line) => log('    [engine] ' + line),
        ...extra
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
            'mission_events', 'mission_detail', 'candidate_diff', 'start_mission', 'cancel_mission',
            'engine_settings', 'attachment_ingest', 'chat_history', 'research_fetch_url',
            'chat_sessions', 'chat_session_create', 'chat_session_rename',
            'chat_session_archive', 'chat_session_delete', 'chat_search',
            'generation_parameters', 'save_generation_parameters', 'save_provider_settings',
            'save_role_settings', 'set_cloud_escalation', 'save_permission_scope',
            'autonomy_settings', 'save_autonomy_settings', 'mcp_servers', 'save_mcp_servers',
            'probe_model_capabilities', 'archive_mission', 'unarchive_mission',
            'delete_mission', 'storage_scan', 'storage_vacuum']) {
            assert(names.includes(required), `missing tool ${required}`);
        }
        log(`PASS tools discovered (${tools.length}): ${names.join(', ')}`);

        // 4. Safe read-only tools with real results.
        const context = await first.projectContext();
        assert(Number.isInteger(context.project.id) && context.project.id > 0, 'project id');
        assertPathEqual(context.project.root, projectA, 'project A root');
        assert.strictEqual(context.execution_enabled, false, 'engine is read-only by default');
        const settings = await first.engineSettings(false);
        assert.strictEqual(settings.project.id, context.project.id, 'engine_settings project');
        assert(settings.permissions.scopes.includes('read'), 'permission scopes');
        assert(settings.mission_defaults.developer_model, 'mission developer default');
        assert(settings.mission_defaults.reviewer_model, 'mission reviewer default');
        assert.strictEqual(settings.models.discovered, null, 'no probe without explicit request');
        assert(settings.research && settings.research.profile === 'manual', 'research profile settings');
        const missions = await first.callJson('mission_list', {});
        assert(Array.isArray(missions.missions), 'mission_list shape');
        log(`PASS project_context: project #${context.project.id} root=${context.project.root} (read-only)`);
        log(`PASS engine_settings: ${settings.models.chat_default_spec} / ` +
            `${settings.mission_defaults.developer_model} -> ${settings.mission_defaults.reviewer_model}`);

        // 4b. Attachment ingestion is project-scoped and returns a bounded preview.
        const ingested = await first.attachmentIngest({ paths: [path.join(projectA, 'notes.txt')] });
        assert(ingested.ok && ingested.attachments.length === 1, 'attachment ingested');
        const attachment = ingested.attachments[0];
        assert.strictEqual(attachment.name, 'notes.txt');
        assert.strictEqual(attachment.has_text, true);
        assert(/NLATTACH-47/.test(attachment.preview), 'attachment preview contains extracted text');
        assert(!('stored_path' in attachment), 'attachment view does not expose host path');
        let outsideRejected = null;
        try {
            await first.attachmentIngest({ paths: [path.join(scratch, 'outside.txt')] });
        } catch (error) {
            outsideRejected = error;
        }
        assert(outsideRejected && /outside the bound project/i.test(outsideRejected.message),
            'outside-project attachment rejected');
        log('PASS attachment ingestion + project containment');

        // 4c. Research is permission-gated by default (no NETWORK grant).
        let researchDenied = null;
        try {
            await first.researchFetch('https://example.com/');
        } catch (error) {
            researchDenied = error;
        }
        assert(researchDenied && /NETWORK/i.test(researchDenied.message), 'research denied without NETWORK');
        log('PASS research fetch denied without NETWORK permission');

        // 4b. A read-only server must refuse mission start before creating anything.
        let deniedStart = null;
        try {
            await first.startMission({
                goal: 'This must never start',
                developerModel: settings.mission_defaults.developer_model,
                reviewerModel: settings.mission_defaults.reviewer_model
            });
        } catch (error) {
            deniedStart = error;
        }
        assert(deniedStart && /read-only|approved/i.test(deniedStart.message),
            'read-only mission start refused: ' + (deniedStart && deniedStart.message));
        const missionsAfterDenial = await first.callJson('mission_list', {});
        assert.deepStrictEqual(missionsAfterDenial.missions, [], 'denied start created no mission');
        log('PASS read-only engine refused start_mission and created no mission');

        // 5. Real Ollama turn with an explicit non-default model and a real attachment.
        const explicitModel = 'ollama/granite4.2:3b';
        const reply = await first.converse(
            context.project.id,
            'Read the attached notes. Reply with exactly the secret token and nothing else.',
            [],
            240000,
            explicitModel,
            [attachment.id]
        );
        assert.strictEqual(reply.ok, true, 'converse ok');
        assert(reply.route && reply.route.model === 'granite4.2:3b', 'route model: ' + JSON.stringify(reply.route));
        assert.strictEqual(reply.route.automatic, false, 'explicit route marked non-automatic');
        assert(/NLATTACH-47/.test(reply.reply), 'model used the attachment context: ' + JSON.stringify(reply.reply));
        const last = reply.messages[reply.messages.length - 1];
        assert(last && last.role === 'assistant' && /NLATTACH-47/.test(last.content), 'persisted assistant message');
        assert.strictEqual(last.model, 'granite4.2:3b', 'assistant history records the model');
        const history = await first.chatHistory(50);
        assert(history.count >= 2 && history.messages.length >= 2, 'persisted history returned');
        const persistedUser = history.messages.filter((item) => item.role === 'user').pop();
        assert(persistedUser && Array.isArray(persistedUser.attachment_ids) &&
            persistedUser.attachment_ids.includes(attachment.id), 'history stores the attachment id');
        assert(persistedUser.attachments && persistedUser.attachments[0].name === 'notes.txt',
            'history resolves attachment metadata');
        log(`PASS real model route ${explicitModel} + attachment context: ${JSON.stringify(reply.reply)}`);
        log(`PASS engine history: ${history.count} messages, model recorded, attachment metadata resolved`);

        // 5b. Full VSIX -> MCP -> backend round trip for Gate B/D settings.
        const writer = new EngineConnection(engineOptions(projectA, { allowExecution: true }));
        const verifier = new EngineConnection(engineOptions(projectA));
        try {
            await writer.connect();
            assert.strictEqual(writer.executionAllowed, true, 'writer execution enabled');
            const configuredModel = settings.models.chat_default_spec;
            const before = await writer.generationParameters(configuredModel, 'chat');
            assert(before && before.effective !== undefined, 'generation parameters read');
            await writer.saveGenerationParameters(
                { temperature: 0.2, top_p: 0.9, top_k: 20 }, 'model', configuredModel);
            const after = await writer.generationParameters(configuredModel, 'chat');
            assert.strictEqual(after.effective.temperature, 0.2, 'generation parameter persisted');
            assert.strictEqual(after.effective.top_k, 20, 'top_k persisted');

            await writer.saveProviderSettings('ollama', { enabled: true });
            await writer.saveProviderSettings('lm_studio_custom', {
                enabled: false, baseUrl: 'http://127.0.0.1:1234/v1',
                label: 'Custom OpenAI-compatible', kind: 'openai_compatible'
            });
            const settingsAfterProvider = await writer.engineSettings(false);
            const customProvider = settingsAfterProvider.models.providers.find(
                (item) => item.provider_id === 'lm_studio_custom');
            assert(customProvider, 'custom provider persisted');
            assert.strictEqual(customProvider.kind, 'openai_compatible', 'custom provider kind');
            assert.strictEqual(customProvider.enabled, false, 'custom provider disabled');
            await writer.saveRoleSettings('chat', { model: configuredModel });
            const savedSpecialist = await writer.saveCustomAgent({
                name: 'Security reviewer', provider: 'ollama', model: configuredModel,
                role: 'security', instructions: 'Review for injection and permissions.',
                tools: ['read', 'diff'], permissions: ['read-only'], enabled: true
            });
            assert(savedSpecialist.agent.id, 'specialist id assigned');
            const settingsWithSpecialist = await writer.engineSettings(false);
            const specialist = (settingsWithSpecialist.agents.custom_agents || [])
                .find((item) => item.name === 'Security reviewer');
            assert(specialist, 'specialist agent persisted');
            assert.strictEqual(specialist.role, 'security', 'specialist role persisted');
            const duplicated = await writer.duplicateCustomAgent(specialist.id);
            assert(duplicated.agent.id !== specialist.id, 'specialist duplicated with a new id');
            await writer.deleteCustomAgent(duplicated.agent.id);
            const settingsAfterDelete = await writer.engineSettings(false);
            assert(!(settingsAfterDelete.agents.custom_agents || [])
                .some((item) => item.id === duplicated.agent.id), 'duplicated specialist deleted');
            await writer.saveCloudEscalation(false);
            await writer.savePermissionScope('read', true);
            const autonomy = await writer.autonomySettings();
            assert(Array.isArray(autonomy.modes), 'autonomy modes');
            await writer.saveAutonomySettings({ mode: 'off', maxMissions: 1, attempts: 1 });

            const sessions = await writer.chatSessions();
            assert(Array.isArray(sessions.sessions) && sessions.sessions.length >= 1, 'sessions listed');
            const created = await writer.chatSessionCreate('Integration durable session');
            await writer.chatSessionRename(created.session.id, 'Integration renamed session');
            const archiveTarget = await writer.chatSessionCreate('Archive me');
            await writer.chatSessionArchive(archiveTarget.session.id);
            await writer.chatSessionDelete(archiveTarget.session.id);
            const search = await writer.chatSearch('NLATTACH-47');
            assert(Array.isArray(search.messages), 'chat search shape');

            const mcp = await writer.mcpServers();
            assert(mcp && mcp.config && typeof mcp.config === 'object', 'MCP config read');
            await writer.saveMcpServers({ servers: {} });
            const scan = await writer.storageScan();
            assert(Array.isArray(scan.items) && Array.isArray(scan.never_delete), 'storage scan shape');
            const vacuum = await writer.storageVacuum();
            assert(vacuum && typeof vacuum.ok === 'boolean', 'SQLite compaction result shape');

            // Restart persistence: a fresh connection must see the durable rows.
            await verifier.connect();
            const persistedSessions = await verifier.chatSessions();
            assert(persistedSessions.sessions.some((item) => item.id === created.session.id),
                'chat session survives engine restart');
            const persistedGenerations = await verifier.generationParameters(configuredModel, 'chat');
            assert.strictEqual(persistedGenerations.effective.temperature, 0.2,
                'generation parameters survive engine restart');
            log('PASS VSIX backend round trip: settings, generation params, sessions, MCP, storage, restart persistence');
        } finally {
            await writer.close();
            await verifier.close();
        }

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
