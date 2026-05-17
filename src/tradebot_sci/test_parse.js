const fs = require('fs');
const path = require('path');
const os = require('os');

const instanceId = process.env.TRADEBOT_INSTANCE_ID || 'local';
let baseDir = process.env.TRADEBOT_DATA_DIR;
if (baseDir) {
    if (baseDir.endsWith('/data') || baseDir.endsWith('/logs') || baseDir.endsWith('/config') ||
        baseDir.endsWith('\\data') || baseDir.endsWith('\\logs') || baseDir.endsWith('\\config')) {
        baseDir = path.dirname(baseDir);
    }
    if (path.basename(baseDir) !== instanceId && !baseDir.includes(instanceId)) {
        baseDir = path.join(baseDir, instanceId);
    }
} else {
    baseDir = path.join(process.env.XDG_CONFIG_HOME || path.join(os.homedir(), '.config'), 'tradebot-sci-gui', instanceId);
}
const stdoutPath = path.join(baseDir, 'logs', 'bot_stdout.log');
const stat = fs.statSync(stdoutPath);
const readSize = Math.min(stat.size, 50000);
const fd = fs.openSync(stdoutPath, 'r');
const buf = Buffer.alloc(readSize);
fs.readSync(fd, buf, 0, readSize, stat.size - readSize);
fs.closeSync(fd);
const tail = buf.toString('utf8');
const holdingsLines = tail.split('\n').filter(l => l.includes('[HOLDINGS]'));
console.log("holdingsLines count:", holdingsLines.length);
if (holdingsLines.length > 0) {
    const lastLine = holdingsLines[holdingsLines.length - 1];
    console.log("lastLine:", lastLine);
    try {
        const jsonPart = lastLine.split(/\[HOLDINGS\]/i)[1].trim();
        const holdingsData = JSON.parse(jsonPart);
        console.log("Parse success!", holdingsData.positions.map(p => p.symbol));
    } catch(e) {
        console.log("Parse failed!", e);
    }
}
