/**
 * Install the packaged VSIX into an isolated VS Code Insiders profile and run the
 * real chat feature acceptance from the installed package (no development path).
 *
 * Grants NETWORK + web-fetch in the isolated backend data directory using the
 * owner/backend permission API before launch; the extension never grants them.
 */
'use strict';

const { spawn, spawnSync } = require('child_process');
const assert = require('assert');
const fs = require('fs');
const path = require('path');

const frontendDir = path.resolve(__dirname, '..');
const repoRoot = path.resolve(frontendDir, '..');
const scratchRoot = path.join(repoRoot, '.workspace', 'temp', 'frontend-accept');
const vsixPath = process.argv[2] || path.join(repoRoot, '.workspace', 'dist', 'NL-Coding-Agent-0.5.0.vsix');
const runDir = path.join(scratchRoot, 'vsix-chat-' + Date.now());
const projectDir = path.join(runDir, 'project');
const dataDir = path.join(runDir, 'data');
const workspaceDir = path.join(runDir, 'workspace');
const userDataDir = path.join(runDir, 'user-data');
const extensionsDir = path.join(runDir, 'extensions');
const logPath = path.join(scratchRoot, 'vsix-chat-test.log');

function codeInsidersPath() {
    return process.env.VSCODE_INSIDERS_EXE ||
        path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Microsoft VS Code Insiders', 'Code - Insiders.exe');
}

function codeInsidersCli() {
    return process.env.VSCODE_INSIDERS_CLI ||
        path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Microsoft VS Code Insiders', 'bin', 'code-insiders.cmd');
}

function runCli(cli, args, env) {
    return spawnSync('cmd.exe', ['/d', '/c', 'call', cli, ...args], {
        encoding: 'utf8', windowsHide: true, env
    });
}

function prepare() {
    for (const dir of [projectDir, dataDir, workspaceDir, userDataDir, extensionsDir, scratchRoot]) {
        fs.mkdirSync(dir, { recursive: true });
    }
    fs.writeFileSync(path.join(projectDir, 'README.md'), '# Isolated VSIX chat fixture\n');
    fs.writeFileSync(path.join(projectDir, 'notes.txt'),
        'The secret editor token is NL-EDITOR-TOKEN-52.\nVSIX attachment fixture.\n');
    const userSettings = path.join(userDataDir, 'User');
    fs.mkdirSync(userSettings, { recursive: true });
    fs.writeFileSync(path.join(userSettings, 'settings.json'), JSON.stringify({
        'nlCodingAgent.engineRoot': repoRoot,
        'nlCodingAgent.researchProfile': 'trusted-auto-review',
        'nlCodingAgent.requestTimeoutSeconds': 240
    }, null, 2));
}

function main() {
    const executable = codeInsidersPath();
    const cli = codeInsidersCli();
    if (!fs.existsSync(executable) || !fs.existsSync(cli)) {
        console.error('VS Code Insiders not found');
        process.exit(2);
    }
    if (!fs.existsSync(vsixPath)) {
        console.error('VSIX not found at ' + vsixPath);
        process.exit(2);
    }
    prepare();
    const baseEnv = { ...process.env };
    delete baseEnv.ELECTRON_RUN_AS_NODE;
    delete baseEnv.ELECTRON_NO_ATTACH_CONSOLE;
    const install = runCli(cli, ['--install-extension', vsixPath, '--force',
        '--user-data-dir', userDataDir, '--extensions-dir', extensionsDir], baseEnv);
    process.stdout.write(install.stdout || '');
    process.stderr.write(install.stderr || '');
    if (install.status !== 0) {
        console.error('VSIX install failed: ' + install.status);
        process.exit(1);
    }
    const installed = fs.readdirSync(extensionsDir).find((name) =>
        name.toLowerCase().startsWith('nlcodingagent.nl-coding-agent'));
    assert(installed, 'installed extension folder');
    console.log('PASS VSIX installed: ' + path.join(extensionsDir, installed));

    const engineEnv = {
        ...baseEnv,
        NL_DATA_DIR: dataDir,
        NL_WORKSPACE_DIR: workspaceDir,
        NL_MODELS_CONFIG: path.join(repoRoot, 'config', 'models.yaml')
    };
    const setup = spawnSync(path.join(repoRoot, 'python', 'python.exe'), [
        path.join(frontendDir, 'test', 'setupResearchGrants.py'), projectDir
    ], { cwd: repoRoot, env: engineEnv, encoding: 'utf8' });
    process.stdout.write(setup.stdout || '');
    process.stderr.write(setup.stderr || '');
    if (setup.status !== 0) {
        console.error('grant setup failed: ' + setup.status);
        process.exit(1);
    }

    const emptyDevDir = path.join(runDir, 'dev-empty');
    fs.mkdirSync(emptyDevDir, { recursive: true });
    const args = [
        '--extensionDevelopmentPath=' + emptyDevDir,
        '--extensionTestsPath=' + path.join(frontendDir, 'test', 'chatfeatures.test.cjs'),
        '--user-data-dir=' + userDataDir,
        '--extensions-dir=' + extensionsDir,
        '--disable-workspace-trust',
        '--skip-welcome',
        '--skip-release-notes',
        projectDir
    ];
    console.log('launching installed VSIX: "' + executable + '" ' + args.join(' '));
    const child = spawn(executable, args, { cwd: repoRoot, env: engineEnv, windowsHide: false });
    let output = '';
    const sink = (chunk) => {
        const text = chunk.toString();
        output += text;
        process.stdout.write(text);
    };
    child.stdout.on('data', sink);
    child.stderr.on('data', sink);
    const timeout = setTimeout(() => {
        console.error('installed VSIX chat acceptance timeout; killing VS Code');
        child.kill('SIGKILL');
    }, 900000);
    child.on('exit', (code, signal) => {
        clearTimeout(timeout);
        fs.writeFileSync(logPath, output, 'utf8');
        console.log('\nexit code: ' + code + (signal ? ' signal ' + signal : ''));
        if (code === 0 && output.includes('CHAT-FEATURE-ACCEPTANCE-PASS')) {
            console.log('== VSIX-CHAT-FEATURE-PASS ==');
            process.exit(0);
        }
        console.error('== VSIX-CHAT-FEATURE-FAIL ==');
        process.exit(1);
    });
}

main();
