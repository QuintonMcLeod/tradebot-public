function _formatSeconds(totalSec) {
    if (!totalSec || isNaN(totalSec) || totalSec < 0) return '--';
    const s = Math.floor(totalSec % 60);
    const m = Math.floor((totalSec / 60) % 60);
    const h = Math.floor((totalSec / 3600) % 24);
    const d = Math.floor(totalSec / 86400);

    const pad = (num) => num.toString().padStart(2, '0');
    if (d > 0) return `${pad(d)}:${pad(h)}:${pad(m)}:${pad(s)}`;
    return `${pad(h)}:${pad(m)}:${pad(s)}`;
}

console.log(_formatSeconds(3600)); // 01:00:00
console.log(_formatSeconds(86400 + 3600 + 120 + 5)); // 01:01:02:05
console.log(_formatSeconds(0)); // --
