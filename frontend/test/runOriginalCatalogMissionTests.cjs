/**
 * Run the ORIGINAL strict catalog fixture in an isolated VS Code Insiders window.
 * The fixture is copied byte-for-byte from frontend/test/fixtures/catalog-original-strict.
 */
'use strict';

const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const frontendDir = path.resolve(__dirname, '..');
const repoRoot = path.resolve(frontendDir, '..');
const fixtureRoot = path.join(frontendDir, 'test', 'fixtures', 'catalog-original-strict', 'project');
const scratchRoot = path.join(repoRoot, '.workspace', 'temp', 'frontend-accept');
const runDir = path.join(scratchRoot, 'catalog-original-' + Date.now());
const projectDir = path.join(runDir, 'project');
const dataDir = path.join(runDir, 'data');
const workspaceDir = path.join(runDir, 'workspace');
const userDataDir = path.join(runDir, 'user-data');
const extensionsDir = path.join(runDir, 'extensions');
const logPath = path.join(scratchRoot, 'catalog-original-mission-test.log');

function codeInsidersPath() {
    return process.env.VSCODE_INSIDERS_EXE ||
        path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Microsoft VS Code Insiders', 'Code - Insiders.exe');
}

function main() {
    const executable = codeInsidersPath();
    if (!fs.existsSync(executable)) {
        console.error('VS Code Insiders not found at ' + executable);
        process.exit(2);
    }
    if (!fs.existsSync(path.join(fixtureRoot, 'catalog', 'service.py'))) {
        console.error('original fixture missing at ' + fixtureRoot);
        process.exit(2);
    }
    for (const dir of [projectDir, dataDir, workspaceDir, userDataDir, extensionsDir, scratchRoot]) {
        fs.mkdirSync(dir, { recursive: true });
    }
    fs.cpSync(fixtureRoot, projectDir, { recursive: true });
    const settings = path.join(userDataDir, 'User');
    fs.mkdirSync(settings, { recursive: true });
    fs.writeFileSync(path.join(settings, 'settings.json'), JSON.stringify({
        'nlCodingAgent.allowExecution': true,
        'nlCodingAgent.engineRoot': repoRoot,
        'nlCodingAgent.requestTimeoutSeconds': 900
    }, null, 2));

    const args = [
        '--extensionDevelopmentPath=' + frontendDir,
        '--extensionTestsPath=' + path.join(frontendDir, 'test', 'originalCatalogMission.test.cjs'),
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
    console.log('original strict log: ' + logPath);
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
        console.error('original strict mission timeout; killing VS Code');
        child.kill('SIGKILL');
    }, 1200000);
    child.on('exit', (code, signal) => {
        clearTimeout(timeout);
        fs.writeFileSync(logPath, output, 'utf8');
        console.log('\nexit code: ' + code + (signal ? ' signal ' + signal : ''));
        console.log('log: ' + logPath);
        if (code === 0 && output.includes('ORIGINAL-STRICT-CATALOG-ACCEPTANCE-PASS')) {
            console.log('== ORIGINAL-STRICT-CATALOG-HOST-TEST-PASS ==');
            process.exit(0);
        }
        console.error('== ORIGINAL-STRICT-CATALOG-HOST-TEST-FAIL ==');
        process.exit(1);
    });
}

main();
