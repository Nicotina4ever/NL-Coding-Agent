/** Real installed-webview acceptance via Electron CDP. All data is isolated. */
'use strict';
const fs = require('fs');
const path = require('path');
const net = require('net');
const { spawn, spawnSync } = require('child_process');
const assert = require('assert');
const repo = path.resolve(__dirname, '../..');
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const host = process.argv[2] || 'standalone';
const sessionOnly = process.argv[3] === 'sessions';
const permissionMode = process.argv[3] === 'permissions';
const packaged = process.argv[3] === 'packaged';
const realProject = process.argv[3] === 'real' || packaged || permissionMode;
const repairReal = process.argv[3] === 'repair-real';
const executable = process.env.NL_ACCEPTANCE_EXE || (host === 'standalone'
    ? path.join(repo, '.workspace/dist/NL Code/NL Code.exe')
    : path.join(process.env.LOCALAPPDATA, 'Programs/Microsoft VS Code Insiders/Code - Insiders.exe'));
const scratch = path.join(repo, '.workspace/temp', 'session-ui-' + host + (sessionOnly ? '-sessions' : realProject ? '-real' : repairReal ? '-repair-real' : '') + '-' + Date.now());
const project = realProject ? path.resolve(process.env.NL_ACCEPTANCE_PROJECT || 'K:/AI/NL_AudioLab') : path.join(scratch, 'project');
const data = path.join(scratch, 'data');
const sourceEngineRoot = process.env.NL_ACCEPTANCE_ENGINE_ROOT || (host === 'standalone' ? path.join(path.dirname(executable), 'engine') : repo);
const engineRoot = repairReal ? path.join(scratch, 'engine') : sourceEngineRoot;
const profile = host === 'standalone' ? path.join(scratch, 'portable/user-data') : path.join(scratch, 'profile');
const extensions = packaged ? path.join(path.dirname(executable),'data/extensions') : path.join(scratch, 'extensions');
const report = { host, scratch, checks: [], started_at: new Date().toISOString() };
const env = { ...process.env, NL_DATA_DIR: data, NL_WORKSPACE_DIR: path.join(scratch, 'workspace'),
    NL_MODELS_CONFIG: path.join(data, 'models.yaml'), NL_ENGINE_ROOT: engineRoot,
    ...(repairReal ? { NL_ACCEPTANCE_SOURCE_ROOT: repo, NL_ACCEPTANCE_PROJECT_COPY: project } : {}) };
delete env.ELECTRON_RUN_AS_NODE;
delete env.VSCODE_PORTABLE;
if (host === 'standalone') { env.VSCODE_PORTABLE = path.join(scratch, 'portable'); }
let child, browser, workbench;
const clients = [];

class Cdp {
    constructor(url) {
        this.next = 0; this.pending = new Map();
        this.socket = new WebSocket(url);
        this.ready = new Promise((resolve, reject) => {
            this.socket.onopen = resolve;
            this.socket.onerror = reject;
        });
        this.socket.onmessage = ({ data }) => {
            const msg = JSON.parse(data);
            if (!msg.id) { return; }
            const pending = this.pending.get(msg.id);
            if (!pending) { return; }
            this.pending.delete(msg.id);
            if (msg.error) { pending.reject(new Error(JSON.stringify(msg.error))); }
            else { pending.resolve(msg.result); }
        };
        clients.push(this);
    }
    async call(method, params = {}, sessionId) {
        await this.ready;
        const id = ++this.next;
        return new Promise((resolve, reject) => {
            const timer = setTimeout(() => { this.pending.delete(id); reject(new Error('CDP timeout: ' + method)); }, 20000);
            this.pending.set(id, { resolve: (v) => { clearTimeout(timer); resolve(v); },
                reject: (e) => { clearTimeout(timer); reject(e); } });
            this.socket.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
        });
    }
    async evaluate(expression, sessionId) {
        const result = await this.call('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }, sessionId);
        if (result.exceptionDetails) { throw new Error(JSON.stringify(result.exceptionDetails)); }
        return result.result.value;
    }
}

async function waitFor(fn, timeout, label) {
    const until = Date.now() + timeout;
    let error;
    while (Date.now() < until) {
        try { const result = await fn(); if (result) { return result; } } catch (err) { error = err; }
        await sleep(300);
    }
    throw new Error('Timed out: ' + label + (error ? ' (' + error.message + ')' : ''));
}
function check(label, detail) {
    report.checks.push({ label, detail, passed: true });
    console.log('PASS ' + label + (detail ? ': ' + detail : ''));
    fs.writeFileSync(path.join(scratch, 'evidence.json'), JSON.stringify(report, null, 2));
}
function db(query) {
    const result = spawnSync(path.join(repo, 'python/python.exe'), ['-c',
        'import sqlite3,json,sys; c=sqlite3.connect(sys.argv[1]); c.row_factory=sqlite3.Row; print(json.dumps([dict(r) for r in c.execute(sys.argv[2])]))',
        path.join(data, 'nl_coding_agent.sqlite3'), query], { encoding: 'utf8', windowsHide: true });
    if (result.status !== 0) { throw new Error(result.stderr); }
    return JSON.parse(result.stdout);
}
async function command(text) {
    await workbench.call('Page.bringToFront');
    await workbench.call('Input.dispatchKeyEvent', { type: 'keyDown', key: 'P', code: 'KeyP', modifiers: 10, windowsVirtualKeyCode: 80 });
    await workbench.call('Input.dispatchKeyEvent', { type: 'keyUp', key: 'P', code: 'KeyP', modifiers: 10, windowsVirtualKeyCode: 80 });
    await waitFor(() => workbench.evaluate('(()=>{const widget=document.querySelector(".quick-input-widget");const input=widget?.querySelector("input");if(!input||!widget.offsetHeight)return false;input.focus();return document.activeElement===input;})()'),10000,'command palette focus');
    await workbench.call('Input.insertText', { text });
    await sleep(400);
    await workbench.call('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
    await workbench.call('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
}

async function main() {
    assert(fs.existsSync(executable), executable);
    for (const dir of [data, profile, extensions, ...(realProject ? [] : [project, path.join(project, 'src'), path.join(project, 'tests')])]) {
        fs.mkdirSync(dir, { recursive: true });
    }
    const inventory = await (await fetch('http://127.0.0.1:11434/api/tags')).json();
    const models = inventory.models.filter((m) => !/cloud|embed/i.test(m.name) && m.size < 8e9)
        .sort((a, b) => Number(/coder/i.test(b.name)) - Number(/coder/i.test(a.name)) || a.size - b.size);
    let model = process.env.NL_ACCEPTANCE_MODEL;
    if (!model) {
        for (const candidate of models) {
            const details = await (await fetch('http://127.0.0.1:11434/api/show', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model: candidate.name })
            })).json();
            if ((details.capabilities || []).includes('tools')) { model = candidate.name; break; }
        }
    }
    assert(inventory.models.some((m) => m.name === model), 'an available local model is required');
    report.model = model;
    fs.writeFileSync(path.join(data, 'models.yaml'), 'providers:\n  ollama:\n    kind: ollama\n    enabled: true\n    base_url: http://127.0.0.1:11434\nroles:\n' +
        ['chat', 'developer', 'reviewer', 'architect', 'debugger'].map((role) => '  ' + role + ':\n    model: ollama/' + (repairReal && role === 'developer' ? 'acceptance-cloud' : model)).join('\n') + '\n');
    const seeded = spawnSync(path.join(repo, 'python/python.exe'), ['-c',
        'import sys; sys.path.insert(0,sys.argv[1]); from nl_coding_agent.models.generation_params import save_params; save_params({"num_ctx":8192,"num_predict":2048,"temperature":0,"seed":42},scope="global")', repo],
        { cwd: repo, env, encoding: 'utf8', windowsHide: true });
    assert.strictEqual(seeded.status, 0, seeded.stderr);
    if (repairReal) {
        const original = path.resolve(process.env.NL_ACCEPTANCE_PROJECT || 'K:/AI/NL_AudioLab');
        fs.mkdirSync(path.join(project,'scripts'),{recursive:true});
        for (const file of ['scripts/app.py', 'scripts/engine.py', 'AVVIO_CODEX_NL_AudioLab_DRAGON.md']) {
            fs.copyFileSync(path.join(original, file), path.join(project, file));
        }
        report.original_source = path.join(original, 'scripts/app.py');
        report.original_sha256 = require('crypto').createHash('sha256').update(fs.readFileSync(report.original_source)).digest('hex');
        fs.writeFileSync(path.join(project, 'README.md'), '# NL AudioLab acceptance copy\nReal PySide6 desktop frontend, audio restoration, MossFormer and FRCRN. Only documentation changes; preserve all definitions.\n');
        fs.writeFileSync(path.join(project, 'tests/test_app.py'), 'import ast\nfrom pathlib import Path\n\ndef test_paths_documented():\n    tree=ast.parse(Path("scripts/app.py").read_text(encoding="utf-8-sig"))\n    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=="InputList")\n    method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=="paths")\n    assert ast.get_docstring(method)=="Return the selected input paths."\n    assert any(isinstance(n,ast.Return) and isinstance(n.value,ast.ListComp) for n in method.body)\n');
        fs.mkdirSync(engineRoot, {recursive:true});
        fs.copyFileSync(path.join(__dirname, 'recoveryEngine.py'), path.join(engineRoot, 'nl_agent.py'));
        fs.writeFileSync(path.join(engineRoot,'acceptance.json'),JSON.stringify({source:sourceEngineRoot,project}));
    } else if (!realProject) {
        fs.writeFileSync(path.join(project, 'README.md'), '# Isolated session acceptance\nPython calculation module. Preserve add and existing tests.\n');
        fs.writeFileSync(path.join(project, 'src/calc.py'), 'def add(a, b):\n    return a + b\n\nPROJECT_TOKEN = "SESSION-UI-742"\n');
        fs.writeFileSync(path.join(project, 'tests/test_calc.py'), 'from src.calc import add\n\ndef test_add():\n    assert add(2, 3) == 5\n');
    }
    if (permissionMode) {
        const seed = spawnSync(path.join(repo, 'python/python.exe'), ['-c',
            'import sys; sys.path.insert(0,'+JSON.stringify(repo)+'); from pathlib import Path; from nl_coding_agent.app.services import AppServices; from nl_coding_agent.persistence.missions import create_mission,update_mission_status; s=AppServices(); scratch=Path(sys.argv[1]); [(scratch/str(i)).mkdir(exist_ok=True) for i in range(5)]; [s.open_project(scratch/str(i)) for i in range(5)]; p=s.open_project(sys.argv[2]); assert p["id"]==6; mid=create_mission(6,"Fixture DELETE progetto 6","Riproduzione isolata: nessuna esecuzione sul progetto reale"); update_mission_status(mid,"interrupted"); s._db.close()',
            scratch, project], { cwd: repo, env, encoding: 'utf8', windowsHide: true });
        assert.strictEqual(seed.status, 0, seed.stderr);
        report.original_source = ['README.md','scripts/app.py','pyproject.toml','AVVIO_CODEX_NL_AudioLab_DRAGON.md'].map(p=>path.join(project,p)).find(p=>fs.existsSync(p));
        assert(report.original_source, 'real project source is available');
        report.original_sha256 = require('crypto').createHash('sha256').update(fs.readFileSync(report.original_source)).digest('hex');
    }
    const settingsDir = path.join(profile, 'User');
    fs.mkdirSync(settingsDir, { recursive: true });
    fs.writeFileSync(path.join(settingsDir, 'settings.json'), JSON.stringify({
        'nlCodingAgent.engineRoot': engineRoot, 'nlCodingAgent.allowExecution': true,
        ...(repairReal ? { 'nlCodingAgent.pythonPath': path.join(sourceEngineRoot, 'python/python.exe') } : {}),
        'nlCodingAgent.showHomeOnStartup': false,
        'chat.disableAIFeatures': true,
        'workbench.secondarySideBar.defaultVisibility': 'hidden',
        ...(host === 'standalone' ? { 'workbench.colorTheme': 'NL Code Dark' } : {}),
        'window.restoreWindows': 'none', 'security.workspace.trust.enabled': false,
        'window.dialogStyle': 'custom',
        'workbench.startupEditor': 'none'
    }, null, 2));
    const extensionVersion = JSON.parse(fs.readFileSync(path.join(repo,'frontend/package.json'),'utf8')).version;
    const vsix = process.env.NL_ACCEPTANCE_VSIX || path.join(repo, '.workspace/dist/NL-Coding-Agent-'+extensionVersion+'.vsix');
    assert(fs.existsSync(vsix), 'package current extension first');
    const appDir = path.dirname(executable);
    const cli = [path.join(appDir, 'resources/app/out/cli.js'),
        ...fs.readdirSync(appDir, { withFileTypes: true }).filter((item) => item.isDirectory())
            .map((item) => path.join(appDir, item.name, 'resources/app/out/cli.js'))].find((item) => fs.existsSync(item));
    assert(cli, 'installed editor CLI is available');
    if (packaged) {
        assert(fs.existsSync(path.join(extensions,'nlcodingagent.nl-coding-agent-'+extensionVersion,'package.json')));
        check('current NL extension supplied by the clean archive; no VSIX install before launch',extensionVersion);
    } else {
    const installed = spawnSync(executable, [cli, '--install-extension', vsix, '--extensions-dir', extensions,
        '--user-data-dir', profile, '--force'], { env: { ...env, ELECTRON_RUN_AS_NODE: '1' }, encoding: 'utf8', windowsHide: true });
    assert.strictEqual(installed.status, 0, installed.stderr + installed.stdout);
    check('current VSIX installed in isolated profile', model);
    }
    const portServer = net.createServer();
    await new Promise((resolve) => portServer.listen(0, '127.0.0.1', resolve));
    const port = portServer.address().port;
    await new Promise((resolve) => portServer.close(resolve));
    child = spawn(executable, [project, '--new-window', '--user-data-dir', profile, '--extensions-dir', extensions,
        '--disable-workspace-trust', '--skip-welcome', '--skip-release-notes', '--remote-debugging-port=' + port],
        { env, cwd: repo, windowsHide: false, stdio: ['ignore', 'pipe', 'pipe'] });
    const log = fs.createWriteStream(path.join(scratch, 'application.log'));
    child.stdout.pipe(log); child.stderr.pipe(log);
    const version = await waitFor(async () => {
        const r = await fetch('http://127.0.0.1:' + port + '/json/version'); return r.json();
    }, 60000, 'Electron CDP');
    browser = new Cdp(version.webSocketDebuggerUrl);
    const page = await waitFor(async () => (await (await fetch('http://127.0.0.1:' + port + '/json/list')).json())
        .find((target) => target.type === 'page' && /workbench/.test(target.url)), 60000, 'workbench');
    workbench = new Cdp(page.webSocketDebuggerUrl);
    await sleep(5000);
    await command('NL Code: Open Chat');
    let webSession;
    const connectWebview = () => waitFor(async () => {
        const targets = (await browser.call('Target.getTargets')).targetInfos;
        for (const target of targets.filter((item) => item.type === 'iframe' || /webview/.test(item.url))
            .sort((a, b) => Number(a.url.includes('purpose=webviewView')) - Number(b.url.includes('purpose=webviewView')))) {
            try {
                const session = await browser.call('Target.attachToTarget', { targetId: target.targetId, flatten: true });
                if (await browser.evaluate('!!(document.getElementById("composer") || document.querySelector("iframe")?.contentDocument?.getElementById("composer"))', session.sessionId)) {
                    webSession = session.sessionId; return true;
                }
                await browser.call('Target.detachFromTarget', { sessionId: session.sessionId });
            } catch { /* frame may be navigating */ }
        }
        return false;
    }, 60000, 'NL Chat webview DOM');
    await connectWebview();
    const ui = (expression) => browser.evaluate('((document)=>(' + expression +
        '))(document.getElementById("composer") ? document : document.querySelector("iframe").contentDocument)', webSession);
    const capture = async (prefix) => {
        await workbench.call('Page.enable');
        for (const width of [1100, 750]) {
            await workbench.call('Emulation.setDeviceMetricsOverride', { width, height: 950, deviceScaleFactor: 1, mobile: false });
            await ui('(()=>{const messages=document.getElementById("messages"); messages.scrollTop=messages.scrollHeight; return true;})()');
            await sleep(700);
            const screenshot = await workbench.call('Page.captureScreenshot', { format: 'png' });
            fs.writeFileSync(path.join(scratch, prefix + '-' + width + '.png'), Buffer.from(screenshot.data, 'base64'));
        }
    };
    await waitFor(() => ui('document.getElementById("status").textContent.includes("read-only") || document.getElementById("status").textContent.includes("missions")'), 60000, 'engine ready');
    check('real editor Chat webview connected');
    if (permissionMode) {
        const selectMode = async (mode) => {
            await ui('(()=>{const e=document.getElementById("chat-access-profile");e.value='+JSON.stringify(mode)+';e.dispatchEvent(new Event("change",{bubbles:true}));return true;})()');
            await waitFor(() => db("SELECT value FROM app_settings WHERE key='access.mode'")[0]?.value === mode,
                15000, 'global mode persisted '+mode);
            await waitFor(() => ui('document.getElementById("chat-access-profile").value==='+JSON.stringify(mode)), 15000, 'selector reconciled');
            await sleep(500);
        };
        assert.strictEqual(db('SELECT id FROM projects WHERE id=6')[0].id, 6);
        const modes = await ui('Array.from(document.getElementById("chat-access-profile").options).map(o=>o.value)');
        assert.deepStrictEqual(modes, ['read-only','workspace-write','auto-review','full-access']);
        assert(await ui('!document.getElementById("permission-grant") && !document.getElementById("cloud-policy") && document.getElementById("exec-toggle").tagName==="SPAN"'));
        check('only four global authorization modes; no grant/cloud/execution switches');
        for (const mode of modes) {
            await selectMode(mode);
            const evaluated = spawnSync(path.join(repo,'python/python.exe'),['-c',
                'import sys; sys.path.insert(0,'+JSON.stringify(repo)+'); import json; from nl_coding_agent.core import permissions as p; print(json.dumps({"mode":p.get_access_mode(),"same":p.get_policy(6)==p.get_policy(1),"delete":p.check_capability("delete").allowed,"cloud":p.check_capability("model-inference-cloud").allowed}))'],
                {cwd:repo,env,encoding:'utf8',windowsHide:true});
            assert.strictEqual(evaluated.status,0,evaluated.stderr);
            const result=JSON.parse(evaluated.stdout);
            assert(result.same); assert.strictEqual(result.mode,mode);
            assert.strictEqual(result.delete, mode==='full-access');
            assert.strictEqual(result.cloud, ['auto-review','full-access'].includes(mode));
            check('GUI mode controls every project and capability',mode);
        }
        await selectMode('workspace-write');
        await ui('(()=>{document.querySelector(\'[data-tab="missions"]\').click();return true;})()');
        await waitFor(() => ui('Array.from(document.querySelectorAll("#mission-list button")).some(b=>b.textContent==="Delete")'),15000,'mission 6 list');
        await ui('(()=>{Array.from(document.querySelectorAll("#mission-list button")).find(b=>b.textContent==="Delete").click();return true;})()');
        await waitFor(async () => db('SELECT id FROM missions WHERE project_id=6').length===0 ||
            await workbench.evaluate('Array.from(document.querySelectorAll(".monaco-dialog-box .monaco-button")).some(b=>b.textContent.includes("Delete permanently"))'),15000,'delete confirmation or accepted action');
        if (db('SELECT id FROM missions WHERE project_id=6').length) {
            await workbench.evaluate('(()=>{Array.from(document.querySelectorAll(".monaco-dialog-box .monaco-button")).find(b=>b.textContent.includes("Delete permanently")).click();return true;})()');
        }
        await waitFor(() => db('SELECT id FROM missions WHERE project_id=6').length===0,15000,'DELETE project 6 completed');
        assert.strictEqual(db("SELECT count(*) AS n FROM app_settings WHERE key LIKE 'permissions.policy.%' OR key LIKE 'access.profile.%'")[0].n,0);
        check('Workspace Write DELETE project 6 succeeds without DELETE grant or execution flag');
        await command('NL Code: Reconnect Backend');
        await sleep(2000);
        await waitFor(() => ui('document.getElementById("chat-access-profile").value==="workspace-write"'),20000,'mode after reconnect');
        assert.strictEqual(require('crypto').createHash('sha256').update(fs.readFileSync(report.original_source)).digest('hex'),report.original_sha256);
        check('reconnect preserves global policy; real NL_AudioLab source unchanged');
        await capture('permissions');
        console.log('GLOBAL-POLICY-UI-PASS '+scratch);
        return;
    }
    if (sessionOnly) {
        const originalSession = await waitFor(() => ui('document.getElementById("chat-session").value'),
            30000, 'initial conversation loaded');
        await ui('(()=>{document.querySelector(".nl-session-drawer").open=true;document.getElementById("session-new").click(); return true;})()');
        await waitFor(() => workbench.evaluate('(()=>{const widget=document.querySelector(".quick-input-widget");const input=widget?.querySelector("input");if(!input||!widget.offsetHeight)return false;input.focus();return document.activeElement===input;})()'),
            10000, 'session title dialog focused');
        await workbench.call('Input.insertText', { text: 'Isolated second conversation' });
        await workbench.call('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
        await workbench.call('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
        const secondSession = await waitFor(async () => {
            const sid = await ui('document.getElementById("chat-session").value');
            return sid && sid !== originalSession && sid;
        }, 20000, 'second session selected');
        const selectSession = (sid) => ui('(()=>{const select=document.getElementById("chat-session");select.value=' +
            JSON.stringify(sid) + ';select.dispatchEvent(new Event("change",{bubbles:true}));return true;})()');
        await selectSession(originalSession);
        await waitFor(() => ui('document.getElementById("chat-session").value===' + JSON.stringify(originalSession)), 20000, 'first session restored');
        await selectSession(secondSession);
        await waitFor(() => ui('document.getElementById("chat-session").value===' + JSON.stringify(secondSession)), 20000, 'second session restored');
        assert.strictEqual(db('SELECT count(*) AS n FROM chat_sessions')[0].n, 2);
        assert.strictEqual(db('SELECT count(*) AS n FROM session_runs')[0].n, 0);
        check('session drawer creates and switches conversations without submitting or resuming work');
        await capture('session-drawer');
        console.log('SESSION-UI-SESSIONS-PASS ' + scratch);
        return;
    }
    const send = (text) => ui('(()=>{document.getElementById("input").value=' + JSON.stringify(text) +
        '; document.getElementById("composer").dispatchEvent(new Event("submit",{bubbles:true,cancelable:true})); return true;})()');
    if (realProject) {
        const crypto = require('crypto');
        const appPath = path.join(project, 'scripts/app.py');
        const before = crypto.createHash('sha256').update(fs.readFileSync(appPath)).digest('hex');
        const title = fs.readFileSync(appPath, 'utf8').match(/setWindowTitle\(['"]([^'"]+)['"]\)/)[1];
        await send('Leggi scripts/app.py con gli strumenti e riporta il titolo esatto della finestra. Non modificare file.');
        await waitFor(() => db("SELECT * FROM session_runs WHERE status='completed'").length, 180000, 'real project read');
        assert(db("SELECT content FROM chat_messages WHERE role='assistant'").some((row) => row.content.includes(title)));
        check('real NL_AudioLab source read and answer matches the actual file');
        const droppedName = 'AVVIO_CODEX_NL_AudioLab_DRAGON.md';
        const droppedText = fs.readFileSync(path.join(project, droppedName), 'utf8');
        await ui('(()=>{const transfer=new DataTransfer();transfer.items.add(new File([' + JSON.stringify(droppedText) + '],' +
            JSON.stringify(droppedName) + ',{type:"text/markdown"}));document.dispatchEvent(new DragEvent("drop",{bubbles:true,cancelable:true,dataTransfer:transfer}));return true;})()');
        await waitFor(() => ui('document.body.textContent.includes(' + JSON.stringify(droppedName) + ')'), 20000, 'dropped file attachment');
        assert(db("SELECT * FROM mission_attachments WHERE name='" + droppedName + "'").length);
        check('OS-style File drop without URI ingested and displayed in the real composer');
        await ui('(()=>{document.querySelector("[data-tab=agents]").click();document.getElementById("specialist-generate").click();return true;})()');
        const enter = async () => {
            await workbench.call('Input.dispatchKeyEvent', {type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
            await workbench.call('Input.dispatchKeyEvent', {type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
        };
        await waitFor(() => workbench.evaluate('!!Array.from(document.querySelectorAll(".quick-input-widget")).find(w=>w.offsetHeight&&w.textContent.includes("Modelli della squadra"))'), 30000, 'team model pool');
        await enter();
        await waitFor(() => workbench.evaluate('!!Array.from(document.querySelectorAll(".quick-input-widget")).find(w=>w.offsetHeight&&w.textContent.includes("Team Architect model"))'), 10000, 'team analyst picker');
        await workbench.call('Input.insertText', {text:model});
        await sleep(300);
        await enter();
        const agentsPath = path.join(data, 'custom_agents.json');
        await waitFor(() => fs.existsSync(agentsPath) && JSON.parse(fs.readFileSync(agentsPath,'utf8')).filter(a=>a.team_active).length>=5, 240000, 'generated active project team');
        check('Generate Team created and activated all five runtime roles for the real project');
        await ui('(()=>{document.getElementById("specialist-new").click();return true;})()');
        const models = await ui('Array.from(document.getElementById("specialist-model").options).map(o=>o.value)');
        for (const item of inventory.models.filter(m=>!/embed/i.test(m.name))) { assert(models.includes('ollama/'+item.name), 'detected model remains available: '+item.name); }
        check('all detected generative local and cloud models remain selectable after team save');
        assert.strictEqual(crypto.createHash('sha256').update(fs.readFileSync(appPath)).digest('hex'), before);
        report.project = project; report.source_sha256 = before;
        await capture('real-project-agents');
        console.log('REAL-PROJECT-UI-ACCEPTANCE-PASS ' + scratch);
        return;
    }
    if (repairReal) {
        await waitFor(() => ui('document.getElementById("auto-coding").checked'),30000,'authorized automatic coding ready');
        await send('Modifica scripts/app.py: aggiungi alla funzione InputList.paths la docstring esatta "Return the selected input paths.". Preserva tutte le classi, funzioni e il comportamento esistente. Esegui test e review.');
        await waitFor(() => db('SELECT * FROM session_runs WHERE mission_id IS NOT NULL').length, 90000, 'real-code mission');
        await command('View: Close Editor');
        const mission = await waitFor(() => {
            const row=db('SELECT * FROM missions ORDER BY id DESC LIMIT 1')[0];
            if (row && ['blocked','failed','interrupted'].includes(row.status)) {
                const run=db('SELECT * FROM session_runs WHERE mission_id='+row.id)[0];
                if (run && ['blocked','failed','interrupted'].includes(run.status)) { throw new Error(JSON.stringify(row)); }
            }
            return row?.status==='completed' && row;
        }, 900000, 'automatic recovery and real-code promotion');
        report.mission=mission;
        await waitFor(() => db("SELECT * FROM session_runs WHERE mission_id="+mission.id+" AND status='completed'").length,30000,'mission result persisted with Chat closed');
        assert.strictEqual(mission.promotion_status,'promoted');
        assert.strictEqual(mission.review_verdict,'APPROVE');
        assert.strictEqual(db('SELECT count(*) AS n FROM missions')[0].n,1);
        assert(fs.existsSync(path.join(data,'injected-internal-failure')));
        assert(fs.existsSync(path.join(data,'injected-cloud-quota')));
        assert(db("SELECT * FROM session_events WHERE payload_json LIKE '%Cloud non disponibile%'").length);
        assert(db("SELECT * FROM session_events WHERE payload_json LIKE '%Riparazione automatica%'").length);
        assert(db('SELECT * FROM verification_runs WHERE passed=1').length>=2);
        const agents=JSON.parse(fs.readFileSync(path.join(data,'custom_agents.json'),'utf8')).filter(a=>a.team_active);
        assert(agents.length>=7,JSON.stringify(agents));
        assert.strictEqual(require('crypto').createHash('sha256').update(fs.readFileSync(report.original_source)).digest('hex'),report.original_sha256);
        check('project-specific specialist team created automatically',String(agents.length));
        check('internal failure repaired automatically on the same mission without Resume');
        check('simulated cloud quota recovered with an actual dynamically detected local model');
        check('real-source copy promoted after candidate/oracle PASS and reviewer APPROVE; original unchanged');
        await waitFor(() => db("SELECT * FROM chat_messages WHERE content LIKE 'Missione #%completed%'").length,30000,'durable closed-UI result');
        await command('NL Code: Open Chat');
        await connectWebview();
        await waitFor(() => ui('document.getElementById("messages").textContent.includes("Missione #1: completed")'),30000,'real-code persisted result');
        await capture('real-code-recovered');
        check('verified recovery result restored after Chat reopening');
        console.log('REAL-CODE-RECOVERY-PASS '+scratch);
        return;
    }
    await send('Leggi il file src/calc.py con gli strumenti e dimmi il valore esatto di PROJECT_TOKEN.');
    await waitFor(() => db("SELECT * FROM session_runs WHERE status='completed'").length, 180000, 'read-only Chat turn');
    assert(db("SELECT * FROM tool_invocations WHERE tool_name IN ('read_source','read_file') AND status='completed'").length);
    assert(db("SELECT content FROM chat_messages WHERE role='assistant'").some((row) => row.content.includes('SESSION-UI-742')));
    assert(db("SELECT seq FROM session_events WHERE type='assistant.delta'").length);
    check('typed request used a real source tool and streamed the answer');
    const before = db('SELECT count(*) AS n FROM session_runs')[0].n;
    await send('Aggiungi in src/calc.py una funzione subtract(a, b) che restituisce a meno b, preservando add, PROJECT_TOKEN e tutti i test esistenti. Verifica la modifica con i test e la review.');
    await waitFor(() => db('SELECT * FROM session_runs WHERE mission_id IS NOT NULL').length, 60000, 'natural-language mission');
    await send('Al termine rispondi brevemente indicando se i test sono passati.');
    await waitFor(() => db('SELECT count(*) AS n FROM session_runs')[0].n >= before + 2, 20000, 'queued follow-up accepted');
    check('natural request started a mission; composer remains usable during work');
    await waitFor(() => db("SELECT * FROM missions WHERE status='running'").length, 60000, 'mission begins before Stop');
    await ui('(()=>{document.getElementById("btn-chat-stop").click(); return true;})()');
    await waitFor(() => db("SELECT * FROM session_runs WHERE mission_id IS NOT NULL AND status='interrupted'").length,
        180000, 'mission acknowledges Stop at a safe checkpoint');
    assert.strictEqual(db('SELECT count(*) AS n FROM missions')[0].n, 1);
    await waitFor(() => ui('!document.getElementById("session-resume").classList.contains("hidden")'), 20000, 'mission Resume control');
    await ui('(()=>{document.getElementById("session-resume").click(); return true;})()');
    await waitFor(() => db("SELECT * FROM session_runs WHERE mission_id IS NOT NULL AND status IN ('running','waiting_mission')").length,
        30000, 'same mission resumes');
    await waitFor(() => db("SELECT * FROM missions WHERE status IN ('running','completed')").length,
        60000, 'resumed mission worker starts');
    check('mission Stop reached a safe checkpoint and Resume retained the same mission');
    await command('View: Close Editor');
    await sleep(700);
    const until = Date.now() + 720000;
    let last;
    while (Date.now() < until) {
        const mission = db('SELECT * FROM missions ORDER BY id DESC LIMIT 1')[0];
        if (mission?.status !== last) { console.log('MISSION ' + mission?.status); last = mission?.status; }
        if (mission && ['completed', 'failed', 'blocked', 'interrupted'].includes(mission.status)) {
            report.mission = mission;
            assert.strictEqual(mission.status, 'completed', JSON.stringify(mission));
            assert.strictEqual(mission.promotion_status, 'promoted');
            assert.strictEqual(mission.review_verdict, 'APPROVE');
            break;
        }
        await sleep(1500);
    }
    assert(report.mission, 'mission finished within acceptance deadline');
    assert(fs.readFileSync(path.join(project, 'src/calc.py'), 'utf8').includes('def subtract'));
    assert(db('SELECT * FROM verification_runs WHERE passed=1').length >= 2);
    await waitFor(() => db("SELECT * FROM chat_messages WHERE content LIKE 'Missione #%completed%'").length, 20000, 'durable mission result');
    check('mission promoted with candidate/oracle verification and reviewer approval');
    report.handoffs = db('SELECT id,from_role,to_role,summary FROM handoffs');
    assert(report.handoffs.length >= 4);
    check('specialist handoffs persisted', String(report.handoffs.length));
    await waitFor(() => db("SELECT count(*) AS n FROM session_runs WHERE status IN ('queued','running','waiting_mission')")[0].n === 0,
        180000, 'queued follow-up');
    check('engine persisted mission result and drained the queue with editor Chat closed');
    await command('NL Code: Open Chat');
    await connectWebview();
    await waitFor(() => ui('document.getElementById("messages").textContent.includes("Missione #1: completed")'),
        30000, 'persisted mission result restored after Chat reopening');
    await waitFor(() => ui('Array.from(document.querySelectorAll("#messages button")).some(b=>b.textContent.includes("Apri diff"))'),
        20000, 'persisted mission diff action restored');
    await ui('(()=>{Array.from(document.querySelectorAll("#messages button")).find(b=>b.textContent.includes("Apri diff")).click(); return true;})()');
    await waitFor(() => ui('Array.from(document.querySelectorAll("#messages details")).some(d=>d.textContent.includes("def subtract"))'),
        20000, 'actual candidate diff opened from the conversation');
    check('verified file diff is accessible from the persisted conversation');
    await capture('mission-complete');
    const initialRuns = db('SELECT count(*) AS n FROM session_runs')[0].n;
    await send('Scrivi una spiegazione dettagliata di almeno 700 parole sul testing del software. Non modificare file e non usare strumenti.');
    const stoppedRun = await waitFor(() => {
        const rows = db("SELECT id,status FROM session_runs ORDER BY ordering DESC LIMIT 1");
        return rows[0] && rows[0].status === 'running' && rows[0];
    }, 30000, 'generation starts before Stop');
    await waitFor(() => db("SELECT seq FROM session_events WHERE run_id='" + stoppedRun.id + "' AND type='assistant.delta'").length,
        60000, 'real partial generation before Stop');
    await ui('(()=>{document.getElementById("btn-chat-stop").click(); return true;})()');
    await waitFor(() => db("SELECT status FROM session_runs WHERE id='" + stoppedRun.id + "'")[0].status === 'cancelled',
        20000, 'durable Stop acknowledgement');
    check('Stop cancels a live provider stream and retains its partial reply');
    const previousOwner = db('SELECT owner FROM session_dispatchers LIMIT 1')[0].owner;
    await command('NL Code: Reconnect Backend');
    await waitFor(async () => db('SELECT owner FROM session_dispatchers LIMIT 1')[0]?.owner !== previousOwner &&
        await ui('document.getElementById("status").textContent.includes("missions")'), 60000, 'new backend process reconnects');
    assert.strictEqual(db("SELECT status FROM session_runs WHERE id='" + stoppedRun.id + "'")[0].status, 'cancelled');
    assert(db("SELECT * FROM chat_messages WHERE content LIKE 'Missione #%completed%'").length);
    check('reconnect preserves Stop, conversation and verified mission result');
    await waitFor(() => ui('!document.getElementById("session-resume").classList.contains("hidden")'), 20000, 'Resume control');
    await ui('(()=>{document.getElementById("session-resume").click(); return true;})()');
    await waitFor(() => db("SELECT status FROM session_runs WHERE id='" + stoppedRun.id + "'")[0].status === 'completed',
        180000, 'same turn resumed to completion');
    assert.strictEqual(db('SELECT count(*) AS n FROM session_runs')[0].n, initialRuns + 1);
    const resumedResult = JSON.parse(db("SELECT result_json FROM session_runs WHERE id='" + stoppedRun.id + "'")[0].result_json);
    assert(!/<tool_call>|<function=/.test(resumedResult.reply), 'resume returns an answer, not unexecuted tool markup');
    assert(resumedResult.reply.length > 200 && /test|software/i.test(resumedResult.reply), 'resumed answer addresses the original prose request');
    assert.strictEqual(db('SELECT count(*) AS n FROM missions')[0].n, 1, 'prose/stop/resume never creates an extra mission');
    check('Resume completes the same persisted turn without a duplicate submission');
    await capture('chat');
    check('wide and compact visual evidence captured');
    console.log('SESSION-UI-ACCEPTANCE-PASS ' + scratch);
}

main().catch(async (error) => {
    report.error = error.stack;
    console.error(error.stack);
    process.exitCode = 1;
    if (workbench) {
        const shot = await workbench.call('Page.captureScreenshot', { format: 'png' }).catch(() => undefined);
        if (shot) { fs.writeFileSync(path.join(scratch, 'failure.png'), Buffer.from(shot.data, 'base64')); }
    }
}).finally(async () => {
    report.finished_at = new Date().toISOString();
    fs.mkdirSync(scratch, { recursive: true });
    fs.writeFileSync(path.join(scratch, 'evidence.json'), JSON.stringify(report, null, 2));
    if (workbench) { await workbench.call('Browser.close').catch(() => {}); }
    for (const client of clients) { client.socket.close(); }
    // Only the isolated application launched by this harness is closed.
    if (child && child.exitCode === null) { child.kill(); }
});
