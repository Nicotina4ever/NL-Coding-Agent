/**
 * Launch VS Code Insiders with the extension under development and run the real
 * chat feature acceptance (test/chatfeatures.test.cjs) on an isolated project.
 *
 * Sets up the scratch Project Access NETWORK grant (including web-fetch),
 * enables the trusted-auto-review research profile via user settings, and keeps
 * all engine data under the isolated run directory.
 */
'use strict';

const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const frontendDir = path.resolve(__dirname, '..');
const repoRoot = path.resolve(frontendDir, '..');
const scratchRoot = path.join(repoRoot, '.workspace', 'temp', 'frontend-accept');
const runDir = path.join(scratchRoot, 'chatfeatures-' + Date.now());
const projectDir = path.join(runDir, 'project');
const dataDir = path.join(runDir, 'data');
const workspaceDir = path.join(runDir, 'workspace');
const userDataDir = path.join(runDir, 'user-data');
const extensionsDir = path.join(runDir, 'extensions');
const logPath = path.join(scratchRoot, 'chatfeatures-test.log');

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
    fs.writeFileSync(path.join(projectDir, 'README.md'), '# Isolated chat feature fixture\n');
    fs.writeFileSync(path.join(projectDir, 'notes.txt'),
        'The secret editor token is NL-EDITOR-TOKEN-52.\nThis file is used for attachment and editor-context acceptance.\n');
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
    if (!fs.existsSync(executable)) {
        console.error('VS Code Insiders not found at ' + executable);
        process.exit(2);
    }
    prepare();
    const engineEnv = {
        ...process.env,
        NL_DATA_DIR: dataDir,
        NL_WORKSPACE_DIR: workspaceDir,
        NL_MODELS_CONFIG: path.join(repoRoot, 'config', 'models.yaml')
    };
    delete engineEnv.ELECTRON_RUN_AS_NODE;
    delete engineEnv.ELECTRON_NO_ATTACH_CONSOLE;
    const setup = spawnSync(path.join(repoRoot, 'python', 'python.exe'), [
        path.join(frontendDir, 'test', 'setupResearchGrants.py'),
        projectDir
    ], { cwd: repoRoot, env: engineEnv, encoding: 'utf8' });
    process.stdout.write(setup.stdout || '');
    process.stderr.write(setup.stderr || '');
    if (setup.status !== 0) {
        console.error('grant setup failed: ' + setup.status);
        process.exit(1);
    }

    const args = [
        '--extensionDevelopmentPath=' + frontendDir,
        '--extensionTestsPath=' + path.join(frontendDir, 'test', 'chatfeatures.test.cjs'),
        '--user-data-dir=' + userDataDir,
        '--extensions-dir=' + extensionsDir,
        '--disable-extensions',
        '--disable-workspace-trust',
        '--skip-welcome',
        '--skip-release-notes',
        projectDir
    ];
    console.log('launching: "' + executable + '" ' + args.join(' '));
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
        console.error('chat feature acceptance timeout; killing VS Code');
        child.kill('SIGKILL');
    }, 900000);
    child.on('exit', (code, signal) => {
        clearTimeout(timeout);
        fs.writeFileSync(logPath, output, 'utf8');
        console.log('\nexit code: ' + code + (signal ? ' signal ' + signal : ''));
        console.log('log: ' + logPath);
        if (code === 0 && output.includes('CHAT-FEATURE-ACCEPTANCE-PASS')) {
            console.log('== CHAT-FEATURE-HOST-TEST-PASS ==');
            process.exit(0);
        }
        console.error('== CHAT-FEATURE-HOST-TEST-FAIL ==');
        process.exit(1);
    });
}

main();
