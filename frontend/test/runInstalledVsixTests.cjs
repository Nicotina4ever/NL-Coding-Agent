/**
 * Install the packaged VSIX into an isolated VS Code Insiders profile and run the
 * same real mission acceptance from the installed extension (no development path).
 *
 * Usage: node test/runInstalledVsixTests.cjs [path-to.vsix]
 */
'use strict';

const assert = require('assert');
const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const frontendDir = path.resolve(__dirname, '..');
const repoRoot = path.resolve(frontendDir, '..');
const scratchRoot = path.join(repoRoot, '.workspace', 'temp', 'frontend-accept');
const vsixPath = process.argv[2] || path.join(repoRoot, '.workspace', 'dist', 'NL-Coding-Agent-0.2.0.vsix');
const runDir = path.join(scratchRoot, 'vsix-' + Date.now());
const projectDir = path.join(runDir, 'project');
const dataDir = path.join(runDir, 'data');
const workspaceDir = path.join(runDir, 'workspace');
const userDataDir = path.join(runDir, 'user-data');
const extensionsDir = path.join(runDir, 'extensions');
const logPath = path.join(scratchRoot, 'vsix-test.log');

function codeInsidersPath() {
    if (process.env.VSCODE_INSIDERS_EXE) {
        return process.env.VSCODE_INSIDERS_EXE;
    }
    return path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Microsoft VS Code Insiders', 'Code - Insiders.exe');
}

function codeInsidersCli() {
    if (process.env.VSCODE_INSIDERS_CLI) {
        return process.env.VSCODE_INSIDERS_CLI;
    }
    const root = path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Microsoft VS Code Insiders', 'bin');
    return path.join(root, 'code-insiders.cmd');
}

function runCli(cli, args, env) {
    // .cmd needs a command interpreter; pass each argument separately so Node
    // quotes paths containing spaces for cmd.exe.
    return spawnSync('cmd.exe', ['/d', '/c', 'call', cli, ...args], {
        encoding: 'utf8',
        windowsHide: true,
        env
    });
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
    fs.writeFileSync(path.join(projectDir, 'README.md'), '# Isolated VSIX mission fixture\n');
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
    if (!fs.existsSync(vsixPath)) {
        console.error('VSIX not found at ' + vsixPath);
        process.exit(2);
    }
    prepare();
    const baseEnv = { ...process.env };
    // A shell running under Electron may export ELECTRON_RUN_AS_NODE; VS Code
    // would then start as plain Node and reject its CLI switches.
    delete baseEnv.ELECTRON_RUN_AS_NODE;
    delete baseEnv.ELECTRON_NO_ATTACH_CONSOLE;
    const cli = codeInsidersCli();
    if (!fs.existsSync(cli)) {
        console.error('VS Code Insiders CLI not found at ' + cli + ' (set VSCODE_INSIDERS_CLI).');
        process.exit(2);
    }
    const install = runCli(cli, [
        '--install-extension', vsixPath,
        '--force',
        '--user-data-dir', userDataDir,
        '--extensions-dir', extensionsDir
    ], baseEnv);
    process.stdout.write(install.stdout || '');
    process.stderr.write(install.stderr || '');
    if (install.status !== 0) {
        console.error('VSIX installation failed with exit ' + install.status);
        process.exit(1);
    }
    const listed = runCli(cli, [
        '--list-extensions',
        '--user-data-dir', userDataDir,
        '--extensions-dir', extensionsDir
    ], baseEnv);
    process.stdout.write(listed.stdout || '');
    if (!String(listed.stdout || '').toLowerCase().includes('nlcodingagent.nl-coding-agent')) {
        console.error('installed extension not listed');
        process.exit(1);
    }
    console.log('PASS VSIX installed in isolated profile: ' + extensionsDir);
    const installed = fs.readdirSync(extensionsDir).find((name) => name.toLowerCase().startsWith('nlcodingagent.nl-coding-agent'));
    assert(installed, 'installed extension folder missing');
    console.log('installed extension folder: ' + path.join(extensionsDir, installed));
    // VS Code only runs --extensionTestsPath when --extensionDevelopmentPath is
    // present. Point it at an empty folder so the test loads the *installed*
    // extension from --extensions-dir (findExtension resolves it by id).
    const emptyDevDir = path.join(runDir, 'dev-empty');
    fs.mkdirSync(emptyDevDir, { recursive: true });

    const args = [
        '--extensionDevelopmentPath=' + emptyDevDir,
        '--extensionTestsPath=' + path.join(frontendDir, 'test', 'mission.test.cjs'),
        '--user-data-dir=' + userDataDir,
        '--extensions-dir=' + extensionsDir,
        '--disable-workspace-trust',
        '--skip-welcome',
        '--skip-release-notes',
        projectDir
    ];
    const env = {
        ...baseEnv,
        NL_DATA_DIR: dataDir,
        NL_WORKSPACE_DIR: workspaceDir,
        NL_MODELS_CONFIG: path.join(repoRoot, 'config', 'models.yaml')
    };
    delete env.ELECTRON_RUN_AS_NODE;
    delete env.ELECTRON_NO_ATTACH_CONSOLE;
    console.log('launching installed VSIX: "' + executable + '" ' + args.join(' '));
    console.log('log: ' + logPath);
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
        console.error('installed VSIX acceptance timeout; killing VS Code');
        child.kill('SIGKILL');
    }, 600000);
    child.on('exit', (code, signal) => {
        clearTimeout(timeout);
        fs.writeFileSync(logPath, output, 'utf8');
        console.log('\nexit code: ' + code + (signal ? ' signal ' + signal : ''));
        const passed = output.includes('MISSION-ACCEPTANCE-PASS');
        if (code === 0 && passed) {
            console.log('== VSIX-INSTALLED-MISSION-PASS ==');
            process.exit(0);
        }
        console.error('== VSIX-INSTALLED-MISSION-FAIL ==');
        process.exit(1);
    });
}

main();
