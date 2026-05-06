const fs = require('fs');
const path = require('path');
const stdoutPath = '/home/qchan/.config/tradebot-sci/logs/bot_stdout.log';
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
