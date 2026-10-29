/**
 * Launch VS Code Insiders with the extension under development and run the real
 * mission acceptance (test/mission.test.cjs) on an isolated project.
 *
 * The fixture deliberately has a failing baseline test importing sub(); the
 * engine's candidate/oracle suites must both pass before the reviewer can
 * approve and promote the change.
 *
 * Usage: node test/runMissionTests.cjs
 */
'use strict';

const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const frontendDir = path.resolve(__dirname, '..');
const repoRoot = path.resolve(frontendDir, '..');
const scratchRoot = path.join(repoRoot, '.workspace', 'temp', 'frontend-accept');
const runDir = path.join(scratchRoot, 'mission-' + Date.now());
const projectDir = path.join(runDir, 'project');
const dataDir = path.join(runDir, 'data');
const workspaceDir = path.join(runDir, 'workspace');
const userDataDir = path.join(runDir, 'user-data');
const extensionsDir = path.join(runDir, 'extensions');
const logPath = path.join(scratchRoot, 'mission-test.log');

function codeInsidersPath() {
    if (process.env.VSCODE_INSIDERS_EXE) {
        return process.env.VSCODE_INSIDERS_EXE;
    }
    return path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Microsoft VS Code Insiders', 'Code - Insiders.exe');
}

function prepare() {
    for (const dir of [projectDir, dataDir, workspaceDir, userDataDir, extensionsDir, scratchRoot]) {
        fs.mkdirSync(dir, { recursive: true });
    }
    fs.mkdirSync(path.join(projectDir, 'src'), { recursive: true });
    fs.mkdirSync(path.join(projectDir, 'tests'), { recursive: true });
    fs.writeFileSync(path.join(projectDir, 'src', '__init__.py'), '');
    fs.writeFileSync(path.join(projectDir, 'src', 'calc.py'),
        'def add(a, b):\n    return a + b\n');
    fs.writeFileSync(path.join(projectDir, 'tests', 'test_calc.py'),
        'from src.calc import add, sub\n\n\n' +
        'def test_add():\n    assert add(2, 3) == 5\n\n\n' +
        'def test_sub():\n    assert sub(8, 3) == 5\n    assert sub(2, 5) == -3\n');
    fs.writeFileSync(path.join(projectDir, 'README.md'), '# Isolated mission fixture\n');
    const userSettings = path.join(userDataDir, 'User');
    fs.mkdirSync(userSettings, { recursive: true });
    fs.writeFileSync(path.join(userSettings, 'settings.json'), JSON.stringify({
        'nlCodingAgent.allowExecution': true,
        'nlCodingAgent.engineRoot': repoRoot,
        'nlCodingAgent.requestTimeoutSeconds': 180
    }, null, 2));
}

function main() {
    const executable = codeInsidersPath();
    if (!fs.existsSync(executable)) {
        console.error('VS Code Insiders not found at ' + executable + ' (set VSCODE_INSIDERS_EXE).');
        process.exit(2);
    }
    prepare();
    const args = [
        '--extensionDevelopmentPath=' + frontendDir,
        '--extensionTestsPath=' + path.join(frontendDir, 'test', 'mission.test.cjs'),
        '--user-data-dir=' + userDataDir,
        '--extensions-dir=' + extensionsDir,
        '--disable-extensions',
        '--disable-workspace-trust',
        '--skip-welcome',
        '--skip-release-notes',
        projectDir
    ];
    const env = {
        ...process.env,
        NL_DATA_DIR: dataDir,
        NL_WORKSPACE_DIR: workspaceDir,
        NL_MODELS_CONFIG: path.join(repoRoot, 'config', 'models.yaml')
    };
    delete env.ELECTRON_RUN_AS_NODE;
    delete env.ELECTRON_NO_ATTACH_CONSOLE;
    console.log('launching: "' + executable + '" ' + args.join(' '));
    console.log('mission log: ' + logPath);
    const child = spawn(executable, args, { cwd: repoRoot, env, windowsHide: false });
    let output = '';
    const sink = (chunk) => {
        const text = chunk.toString();
        output += text;
        process.stdout.write(text);
    };
    child.stdout.on('data', sink);
    child.stderr.on('data', sink);
    const timeout = setTimeout(() => {
        console.error('mission acceptance timeout; killing VS Code');
        child.kill('SIGKILL');
    }, 600000);
    child.on('exit', (code, signal) => {
        clearTimeout(timeout);
        fs.writeFileSync(logPath, output, 'utf8');
        console.log('\nexit code: ' + code + (signal ? ' signal ' + signal : ''));
        console.log('log: ' + logPath);
        const passed = output.includes('MISSION-ACCEPTANCE-PASS');
        if (code === 0 && passed) {
            console.log('== MISSION-HOST-TEST-PASS ==');
            process.exit(0);
        }
        console.error('== MISSION-HOST-TEST-FAIL ==');
        process.exit(1);
    });
}

main();
