/**
 * Launch VS Code Insiders with the extension under development and run the real
 * multi-agent team mission acceptance (test/teamMission.test.cjs) on an isolated
 * two-file project. The objective spans two source files so the planner adds the
 * read-only architect role; the mission must still pass independent verification.
 */
'use strict';

const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const frontendDir = path.resolve(__dirname, '..');
const repoRoot = path.resolve(frontendDir, '..');
const scratchRoot = path.join(repoRoot, '.workspace', 'temp', 'frontend-accept');
const runDir = path.join(scratchRoot, 'team-mission-' + Date.now());
const projectDir = path.join(runDir, 'project');
const dataDir = path.join(runDir, 'data');
const workspaceDir = path.join(runDir, 'workspace');
const userDataDir = path.join(runDir, 'user-data');
const extensionsDir = path.join(runDir, 'extensions');
const logPath = path.join(scratchRoot, 'team-mission-test.log');

function codeInsidersPath() {
    if (process.env.VSCODE_INSIDERS_EXE) {
        return process.env.VSCODE_INSIDERS_EXE;
    }
    return path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Microsoft VS Code Insiders', 'Code - Insiders.exe');
}

function prepare() {
    for (const dir of [projectDir, dataDir, workspaceDir, userDataDir, extensionsDir, scratchRoot,
        path.join(projectDir, 'src'), path.join(projectDir, 'tests')]) {
        fs.mkdirSync(dir, { recursive: true });
    }
    fs.writeFileSync(path.join(projectDir, 'src', '__init__.py'), '');
    fs.writeFileSync(path.join(projectDir, 'src', 'calc.py'),
        '# Arithmetic helpers live in this module.\n');
    fs.writeFileSync(path.join(projectDir, 'src', 'stats.py'),
        '# Statistics helpers live in this module.\n');
    fs.writeFileSync(path.join(projectDir, 'tests', 'test_calc.py'),
        'from src.calc import sub\n\n\n' +
        'def test_sub():\n    assert sub(8, 3) == 5\n    assert sub(2, 5) == -3\n');
    fs.writeFileSync(path.join(projectDir, 'tests', 'test_stats.py'),
        'from src.stats import mean\n\n\n' +
        'def test_mean():\n    assert mean([1, 2, 3]) == 2\n    assert mean([4, 6]) == 5\n');
    fs.writeFileSync(path.join(projectDir, 'README.md'), '# Isolated proportional team mission fixture\n');
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
    if (!fs.existsSync(executable)) {
        console.error('VS Code Insiders not found at ' + executable + ' (set VSCODE_INSIDERS_EXE).');
        process.exit(2);
    }
    prepare();
    const args = [
        '--extensionDevelopmentPath=' + frontendDir,
        '--extensionTestsPath=' + path.join(frontendDir, 'test', 'teamMission.test.cjs'),
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
    console.log('team mission log: ' + logPath);
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
        console.error('team mission acceptance timeout; killing VS Code');
        child.kill('SIGKILL');
    }, 900000);
    child.on('exit', (code, signal) => {
        clearTimeout(timeout);
        fs.writeFileSync(logPath, output, 'utf8');
        console.log('\nexit code: ' + code + (signal ? ' signal ' + signal : ''));
        console.log('log: ' + logPath);
        if (code === 0 && output.includes('TEAM-MISSION-ACCEPTANCE-PASS')) {
            console.log('== TEAM-MISSION-HOST-TEST-PASS ==');
            process.exit(0);
        }
        console.error('== TEAM-MISSION-HOST-TEST-FAIL ==');
        process.exit(1);
    });
}

main();
