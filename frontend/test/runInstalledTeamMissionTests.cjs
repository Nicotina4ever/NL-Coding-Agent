/**
 * Install the packaged VSIX into an isolated profile and run the real proportional
 * team mission acceptance from the installed payload.
 */
'use strict';

const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const frontendDir = path.resolve(__dirname, '..');
const repoRoot = path.resolve(frontendDir, '..');
const scratchRoot = path.join(repoRoot, '.workspace', 'temp', 'frontend-accept');
const vsixPath = process.argv[2] || path.join(repoRoot, '.workspace', 'dist', 'NL-Coding-Agent-0.5.0.vsix');
const runDir = path.join(scratchRoot, 'vsix-team-' + Date.now());
const projectDir = path.join(runDir, 'project');
const dataDir = path.join(runDir, 'data');
const workspaceDir = path.join(runDir, 'workspace');
const userDataDir = path.join(runDir, 'user-data');
const extensionsDir = path.join(runDir, 'extensions');
const logPath = path.join(scratchRoot, 'vsix-team-test.log');

function codeInsidersPath() {
    return process.env.VSCODE_INSIDERS_EXE ||
        path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Microsoft VS Code Insiders', 'Code - Insiders.exe');
}

function codeInsidersCli() {
    return process.env.VSCODE_INSIDERS_CLI ||
        path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Microsoft VS Code Insiders', 'bin', 'code-insiders.cmd');
}

function prepare() {
    for (const dir of [projectDir, dataDir, workspaceDir, userDataDir, extensionsDir, scratchRoot,
        path.join(projectDir, 'src'), path.join(projectDir, 'tests')]) {
        fs.mkdirSync(dir, { recursive: true });
    }
    fs.writeFileSync(path.join(projectDir, 'src', '__init__.py'), '');
    fs.writeFileSync(path.join(projectDir, 'src', 'calc.py'), '# Arithmetic helpers live in this module.\n');
    fs.writeFileSync(path.join(projectDir, 'src', 'stats.py'), '# Statistics helpers live in this module.\n');
    fs.writeFileSync(path.join(projectDir, 'tests', 'test_calc.py'),
        'from src.calc import sub\n\n\ndef test_sub():\n    assert sub(8, 3) == 5\n    assert sub(2, 5) == -3\n');
    fs.writeFileSync(path.join(projectDir, 'tests', 'test_stats.py'),
        'from src.stats import mean\n\n\ndef test_mean():\n    assert mean([1, 2, 3]) == 2\n    assert mean([4, 6]) == 5\n');
    fs.writeFileSync(path.join(projectDir, 'README.md'), '# Isolated installed team mission fixture\n');
    const userSettings = path.join(userDataDir, 'User');
    fs.mkdirSync(userSettings, { recursive: true });
    fs.writeFileSync(path.join(userSettings, 'settings.json'), JSON.stringify({
        'nlCodingAgent.allowExecution': true,
        'nlCodingAgent.engineRoot': repoRoot,
        'nlCodingAgent.requestTimeoutSeconds': 600
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
    const env = { ...process.env };
    delete env.ELECTRON_RUN_AS_NODE;
    delete env.ELECTRON_NO_ATTACH_CONSOLE;
    const install = spawnSync('cmd.exe', ['/d', '/c', 'call', cli, '--install-extension', vsixPath,
        '--force', '--user-data-dir', userDataDir, '--extensions-dir', extensionsDir],
        { encoding: 'utf8', windowsHide: true, env });
    process.stdout.write(install.stdout || '');
    process.stderr.write(install.stderr || '');
    if (install.status !== 0) {
        console.error('VSIX install failed: ' + install.status);
        process.exit(1);
    }
    const installed = fs.readdirSync(extensionsDir).find((name) =>
        name.toLowerCase().startsWith('nlcodingagent.nl-coding-agent'));
    if (!installed) {
        console.error('installed extension folder missing');
        process.exit(1);
    }
    console.log('PASS VSIX installed: ' + path.join(extensionsDir, installed));

    const emptyDevDir = path.join(runDir, 'dev-empty');
    fs.mkdirSync(emptyDevDir, { recursive: true });
    const engineEnv = {
        ...env,
        NL_DATA_DIR: dataDir,
        NL_WORKSPACE_DIR: workspaceDir,
        NL_MODELS_CONFIG: path.join(repoRoot, 'config', 'models.yaml')
    };
    const args = [
        '--extensionDevelopmentPath=' + emptyDevDir,
        '--extensionTestsPath=' + path.join(frontendDir, 'test', 'teamMission.test.cjs'),
        '--user-data-dir=' + userDataDir,
        '--extensions-dir=' + extensionsDir,
        '--disable-workspace-trust',
        '--skip-welcome',
        '--skip-release-notes',
        projectDir
    ];
    console.log('launching installed VSIX team mission: "' + executable + '" ' + args.join(' '));
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
        console.error('installed VSIX team mission timeout; killing VS Code');
        child.kill('SIGKILL');
    }, 900000);
    child.on('exit', (code, signal) => {
        clearTimeout(timeout);
        fs.writeFileSync(logPath, output, 'utf8');
        console.log('\nexit code: ' + code + (signal ? ' signal ' + signal : ''));
        console.log('log: ' + logPath);
        if (code === 0 && output.includes('TEAM-MISSION-ACCEPTANCE-PASS')) {
            console.log('== VSIX-TEAM-MISSION-PASS ==');
            process.exit(0);
        }
        console.error('== VSIX-TEAM-MISSION-FAIL ==');
        process.exit(1);
    });
}

main();
