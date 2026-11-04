/** Real child-process failure: bounded reconnect, then explicit retry succeeds. */
'use strict';
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const {EngineConnection} = require('../out/backend.js');
const repo = path.resolve(__dirname,'../..');
const scratch = path.join(repo,'.workspace/temp','connection-recovery-'+Date.now());
const sleep = ms => new Promise(resolve=>setTimeout(resolve,ms));
async function main() {
    fs.mkdirSync(scratch,{recursive:true});
    const launcher=path.join(scratch,'nl_agent.py');
    fs.writeFileSync(launcher,'raise RuntimeError("acceptance: engine startup failure")\n');
    const lines=[];
    const connection=new EngineConnection({engineRoot:scratch,pythonPath:path.join(repo,'python/python.exe'),
        projectRoot:scratch,log:line=>lines.push(line),env:{NL_DATA_DIR:path.join(scratch,'data'),NL_WORKSPACE_DIR:path.join(scratch,'workspace'),CREWAI_STORAGE_DIR:path.join(scratch,'crewai')}});
    try {
        await assert.rejects(connection.connect(),/Connection closed/);
        await sleep(23000);
        assert.strictEqual(lines.filter(line=>line.startsWith('starting engine:')).length,4,'one start and three automatic retries');
        assert.strictEqual(connection.state,'failed');
        await sleep(2500);
        assert.strictEqual(lines.filter(line=>line.startsWith('starting engine:')).length,4,'retries stop after the limit');
        fs.writeFileSync(launcher,'import sys,runpy\nsys.path.insert(0,'+JSON.stringify(repo)+')\nrunpy.run_path('+JSON.stringify(path.join(repo,'nl_agent.py'))+',run_name="__main__")\n');
        await connection.restart();
        assert.strictEqual(connection.state,'ready','manual reconnect works after launcher repair');
        const pid=connection.childPid;
        await connection.disposeResources();
        let staleRetryFired=false;
        connection.reconnectTimer=setTimeout(()=>{staleRetryFired=true;},10000);
        // Simulate a direct connect finishing before its earlier retry timer.
        connection.state='failed';
        await connection.connect();
        const healthyPid=connection.childPid;
        assert.notStrictEqual(healthyPid,pid);
        await sleep(10500);
        assert(!staleRetryFired,'successful connect clears an already scheduled retry');
        assert.strictEqual(connection.childPid,healthyPid,'successful connect cancels an earlier retry timer');
        console.log('CONNECTION-RECOVERY-PASS');
    } catch(error) { console.error(lines.slice(-35).join('\n')); throw error; }
    finally { await connection.close(); }
}
main().catch(error=>{console.error(error);process.exitCode=1;});
