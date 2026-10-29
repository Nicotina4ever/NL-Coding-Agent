/**
 * Launch the installed VS Code Insiders with the extension under development and
 * run test/extension.test.cjs inside the real extension host.
 *
 * Usage: node test/runExtensionTests.cjs
 */
'use strict';

const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const frontendDir = path.resolve(__dirname, '..');
const repoRoot = path.resolve(frontendDir, '..');
const scratchRoot = path.join(repoRoot, '.workspace', 'temp', 'frontend-accept');
const runDir = path.join(scratchRoot, 'extension-' + Date.now());
const projectDir = path.join(runDir, 'project');
const dataDir = path.join(runDir, 'data');
const workspaceDir = path.join(runDir, 'workspace');
const userDataDir = path.join(runDir, 'user-data');
const extensionsDir = path.join(runDir, 'extensions');
const logPath = path.join(scratchRoot, 'extension-test.log');

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
    fs.writeFileSync(path.join(projectDir, 'README.md'), '# VS Code acceptance fixture\n');
    fs.writeFileSync(path.join(projectDir, 'app.py'), 'print("hello")\n');
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
        '--extensionTestsPath=' + path.join(frontendDir, 'test', 'extension.test.cjs'),
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
    // A shell that itself runs under Electron may export ELECTRON_RUN_AS_NODE;
    // inherited into the VS Code binary it would run as plain Node and reject
    // the VS Code switches.
    delete env.ELECTRON_RUN_AS_NODE;
    delete env.ELECTRON_NO_ATTACH_CONSOLE;
    console.log('launching: "' + executable + '" ' + args.join(' '));
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
        console.error('extension test timeout; killing VS Code');
        child.kill('SIGKILL');
    }, 300000);
    child.on('exit', (code, signal) => {
        clearTimeout(timeout);
        fs.writeFileSync(logPath, output, 'utf8');
        console.log('\nexit code: ' + code + (signal ? ' signal ' + signal : ''));
        console.log('log: ' + logPath);
        const passed = output.includes('EXTENSION-ACCEPTANCE-PASS');
        if (code === 0 && passed) {
            console.log('== EXTENSION-HOST-TEST-PASS ==');
            process.exit(0);
        }
        console.error('== EXTENSION-HOST-TEST-FAIL ==');
        process.exit(1);
    });
}

main();
