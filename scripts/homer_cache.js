const fs = require('fs');
const path = require('path');

class HomerCache {
    constructor(baseDir) {
        this.baseDir = baseDir;
        this.cacheDir = path.join(baseDir, '.homer_cache');
        this.ensureCacheDir();
    }

    ensureCacheDir() {
        if (!fs.existsSync(this.cacheDir)) {
            fs.mkdirSync(this.cacheDir, { recursive: true });
        }
    }

    getCacheFile(date) {
        return path.join(this.cacheDir, `${date}.json`);
    }

    getSeqFile(date) {
        return path.join(this.cacheDir, `seq_${date}.txt`);
    }

    loadCache(date) {
        const cacheFile = this.getCacheFile(date);
        try {
            const data = fs.readFileSync(cacheFile, 'utf8');
            return JSON.parse(data);
        } catch (e) {
            return {};
        }
    }

    saveCache(date, cache) {
        const cacheFile = this.getCacheFile(date);
        fs.writeFileSync(cacheFile, JSON.stringify(cache, null, 2));
    }

    getNextSeq(date) {
        const seqFile = this.getSeqFile(date);
        let num = 1;
        try {
            num = parseInt(fs.readFileSync(seqFile, 'utf8')) || 1;
        } catch (e) {}
        fs.writeFileSync(seqFile, String(num + 1));
        return num;
    }

    hasHomeRun(date, gameId, atBatIndex) {
        const cache = this.loadCache(date);
        const key = `${gameId}:${atBatIndex}`;
        return !!cache[key];
    }

    markHomeRun(date, gameId, atBatIndex) {
        const cache = this.loadCache(date);
        const key = `${gameId}:${atBatIndex}`;
        cache[key] = true;
        this.saveCache(date, cache);
    }
}

module.exports = HomerCache;