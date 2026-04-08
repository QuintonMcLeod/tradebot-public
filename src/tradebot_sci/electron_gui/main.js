// CODING RULE: Do NOT insert watermark tags (e.g. [AGENT_NAME], [AI FIX], etc.)
// into comments or log statements. Write clean, professional comments only.
// See AGENTS.md for full guidelines.

const { app, BrowserWindow, ipcMain, Menu, MenuItem } = require('electron');
const path = require('path');
const fs = require('fs');
const os = require('os');
const { exec } = require('child_process');
const logParser = require('./log_analytics');

// Suppress EPIPE errors on stdout/stderr — these are non-fatal pipe breaks
// when the parent process (terminal/launcher) closes before Electron finishes writing.
process.stdout?.on('error', (err) => { if (err.code !== 'EPIPE') throw err; });
process.stderr?.on('error', (err) => { if (err.code !== 'EPIPE') throw err; });

// Enable remote debugging so the renderer can be inspected via CDP
app.commandLine.appendSwitch('remote-debugging-port', '9223');

let mainWindow;
let settingsWindow;
let botRunning = false;

// Helper to determine OS
const isWindows = () => process.platform === 'win32';

// Helper to find repo root reliably
const DOTENV_PATH = path.join(__dirname, '../../../.env');
const PROFILES_PATH = path.join(__dirname, '../../../config/settings_profiles.yaml');
// Use the same XDG user data dir as the Python runtime (paths.py)
// Linux: ~/.config/tradebot-sci, macOS: ~/Library/Application Support/tradebot-sci
const USER_DATA_DIR = process.platform === 'darwin'
    ? path.join(os.homedir(), 'Library', 'Application Support', 'tradebot-sci')
    : path.join(process.env.XDG_CONFIG_HOME || path.join(os.homedir(), '.config'), 'tradebot-sci');
const CONFIG_JSON_PATH = path.join(USER_DATA_DIR, 'config.json');
// Fallback: if user data config doesn't exist but project root one does, use it
const LEGACY_CONFIG_JSON_PATH = path.join(__dirname, '../../../config.json');
const SECRETS_PATH = path.join(USER_DATA_DIR, '.env.secrets');
const LEGACY_SECRETS_PATH = path.join(__dirname, '../../../.env.secrets');

// Ensure user data directories exist before any writes
for (const sub of ['', 'data', 'logs']) {
    const dir = path.join(USER_DATA_DIR, sub);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

// Setup IPC handlers (called after app ready)
function setupIpcHandlers() {
    // IPC Handlers for Settings Data
    ipcMain.handle('read-env', async () => {
        if (!fs.existsSync(DOTENV_PATH)) return {};
        const content = fs.readFileSync(DOTENV_PATH, 'utf8');
        const env = {};
        content.split('\n').forEach(line => {
            const match = line.match(/^\s*([\w.-]+)\s*=\s*(.*)$/);
            if (match) env[match[1]] = match[2];
        });
        return env;
    });

    ipcMain.handle('save-env', async (event, updates) => {
        let content = fs.existsSync(DOTENV_PATH) ? fs.readFileSync(DOTENV_PATH, 'utf8') : '';
        let lines = content.split('\n');
        const keys = Object.keys(updates);

        keys.forEach(key => {
            let found = false;
            for (let i = 0; i < lines.length; i++) {
                if (lines[i].startsWith(`${key}=`)) {
                    lines[i] = `${key}=${updates[key]}`;
                    found = true;
                    break;
                }
            }
            if (!found) lines.push(`${key}=${updates[key]}`);
        });

        fs.writeFileSync(DOTENV_PATH, lines.join('\n'));

        // Notify all windows
        BrowserWindow.getAllWindows().forEach(win => {
            win.webContents.send('env-updated', updates);
        });

        return { success: true };
    });

    ipcMain.handle('read-profiles', async () => {
        if (!fs.existsSync(PROFILES_PATH)) return "";
        return fs.readFileSync(PROFILES_PATH, 'utf8');
    });

    ipcMain.handle('save-profiles', async (event, content) => {
        fs.writeFileSync(PROFILES_PATH, content);
        return { success: true };
    });

    ipcMain.handle('read-profiles-json', async () => {
        const yaml = require('js-yaml');
        if (!fs.existsSync(PROFILES_PATH)) return {};
        try {
            const content = fs.readFileSync(PROFILES_PATH, 'utf8');
            return yaml.load(content) || {};
        } catch (e) {
            console.error("[MAIN] YAML Load Error:", e);
            return {};
        }
    });

    ipcMain.handle('save-profiles-json', async (event, data) => {
        const yaml = require('js-yaml');
        try {
            const content = yaml.dump(data, { lineWidth: -1, noRefs: true });
            fs.writeFileSync(PROFILES_PATH, content);
            return { success: true };
        } catch (e) {
            console.error("[MAIN] YAML Save Error:", e);
            return { success: false, error: e.message };
        }
    });

    // =============================================
    // NEW: Unified config.json handlers
    // =============================================
    ipcMain.handle('read-config', async () => {
        // Prefer XDG user data dir, fallback to project root
        let configPath = CONFIG_JSON_PATH;
        if (!fs.existsSync(configPath) && fs.existsSync(LEGACY_CONFIG_JSON_PATH)) {
            configPath = LEGACY_CONFIG_JSON_PATH;
        }

        if (!fs.existsSync(configPath)) {
            console.warn("[MAIN] config.json not found, returning empty object");
            return {};
        }
        try {
            const content = fs.readFileSync(configPath, 'utf8');
            return JSON.parse(content);
        } catch (e) {
            console.error("[MAIN] Config JSON Load Error:", e);
            return {};
        }
    });

    ipcMain.handle('save-config', async (event, config) => {
        try {
            const content = JSON.stringify(config, null, 2);
            fs.writeFileSync(CONFIG_JSON_PATH, content);
            console.log("[MAIN] Saved config.json");

            // Notify all windows that config changed
            BrowserWindow.getAllWindows().forEach(win => {
                win.webContents.send('config-updated', config);
            });

            return { success: true };
        } catch (e) {
            console.error("[MAIN] Config JSON Save Error:", e);
            return { success: false, error: e.message };
        }
    });

    ipcMain.handle('export-config', async (event) => {
        const { dialog } = require('electron');
        try {
            const win = BrowserWindow.getFocusedWindow();
            const { filePath } = await dialog.showSaveDialog(win, {
                title: 'Export Settings',
                defaultPath: 'tradebot_config.json',
                filters: [{ name: 'JSON Files', extensions: ['json'] }]
            });
            if (!filePath) return { success: false, canceled: true };
            
            const configPath = fs.existsSync(CONFIG_JSON_PATH) ? CONFIG_JSON_PATH : LEGACY_CONFIG_JSON_PATH;
            if (!fs.existsSync(configPath)) {
                return { success: false, error: 'Config file not found to export.' };
            }
            
            // Parse config
            const content = fs.readFileSync(configPath, 'utf8');
            let configData;
            try { configData = JSON.parse(content); } catch(e) { configData = {}; }

            // Parse secrets to bundle
            const secretsPath = fs.existsSync(SECRETS_PATH) ? SECRETS_PATH : LEGACY_SECRETS_PATH;
            let secrets = {};
            if (fs.existsSync(secretsPath)) {
                const secretsContent = fs.readFileSync(secretsPath, 'utf8');
                secretsContent.split('\n').forEach(line => {
                    if (line.startsWith('#') || !line.trim()) return;
                    const match = line.match(/^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/);
                    if (match) secrets[match[1]] = match[2];
                });
            }

            // Inject secrets under special namespace
            configData._secrets = secrets;

            const liveLedgerPath = path.join(USER_DATA_DIR, 'data', 'ledger.json');
            const paperLedgerPath = path.join(USER_DATA_DIR, 'data', 'paper_ledger.json');
            if (fs.existsSync(liveLedgerPath)) try { configData._live_ledger = JSON.parse(fs.readFileSync(liveLedgerPath, 'utf8')); } catch(e) {}
            if (fs.existsSync(paperLedgerPath)) try { configData._paper_ledger = JSON.parse(fs.readFileSync(paperLedgerPath, 'utf8')); } catch(e) {}

            fs.writeFileSync(filePath, JSON.stringify(configData, null, 2));
            return { success: true, path: filePath };
        } catch (e) {
            console.error("[MAIN] Export Config Error:", e);
            return { success: false, error: e.message };
        }
    });

    ipcMain.handle('reset-config', async (event) => {
        try {
            let deletedSomething = false;

            const liveLedgerPath = path.join(USER_DATA_DIR, 'data', 'ledger.json');
            const paperLedgerPath = path.join(USER_DATA_DIR, 'data', 'paper_ledger.json');
            const DOT_ENV_PATH = path.join(process.cwd(), '.env');
            const pathsToDelete = [CONFIG_JSON_PATH, LEGACY_CONFIG_JSON_PATH, SECRETS_PATH, LEGACY_SECRETS_PATH, DOT_ENV_PATH, liveLedgerPath, paperLedgerPath];
            
            for (const p of pathsToDelete) {
                if (fs.existsSync(p)) {
                    fs.unlinkSync(p);
                    deletedSomething = true;
                }
            }
            
            if (deletedSomething) {
                app.relaunch();
                const cmd = isWindows() ? 'taskkill /F /IM python.exe' : 'pkill -9 -f "[r]un_dev_bot.py"';
                try { require('child_process').execSync(cmd); } catch (e) {}
                app.quit();
                return { success: true };
            }
            return { success: false, error: 'No configuration or secrets files found to delete.' };
        } catch (e) {
            console.error("[MAIN] Reset Config Error:", e);
            return { success: false, error: e.message };
        }
    });

    ipcMain.handle('import-config', async (event) => {
        const { dialog } = require('electron');
        try {
            const win = BrowserWindow.getFocusedWindow();
            const { filePaths } = await dialog.showOpenDialog(win, {
                title: 'Import Settings',
                filters: [{ name: 'JSON Files', extensions: ['json'] }],
                properties: ['openFile']
            });
            if (!filePaths || filePaths.length === 0) return { success: false, canceled: true };
            
            const sourcePath = filePaths[0];
            const content = fs.readFileSync(sourcePath, 'utf8');
            
            // Validate JSON
            let parsed;
            try {
                parsed = JSON.parse(content);
            } catch (je) {
                return { success: false, error: 'Invalid JSON file selected.' };
            }
            
            // Extract secrets if bundled
            if (parsed._secrets) {
                const secrets = parsed._secrets;
                delete parsed._secrets; // Remove from main config body
                
                let secretsContent = "# API Keys and Secrets - DO NOT COMMIT TO GIT\n\n";
                for (const [key, value] of Object.entries(secrets)) {
                    secretsContent += `${key}=${value}\n`;
                }
                fs.writeFileSync(SECRETS_PATH, secretsContent);
                console.log("[MAIN] Imported and saved .env.secrets");
            }
            
            const liveLedgerPath = path.join(USER_DATA_DIR, 'data', 'ledger.json');
            const paperLedgerPath = path.join(USER_DATA_DIR, 'data', 'paper_ledger.json');
            if (parsed._live_ledger) {
                fs.writeFileSync(liveLedgerPath, JSON.stringify(parsed._live_ledger, null, 2));
                delete parsed._live_ledger;
            }
            if (parsed._paper_ledger) {
                fs.writeFileSync(paperLedgerPath, JSON.stringify(parsed._paper_ledger, null, 2));
                delete parsed._paper_ledger;
            }
            
            // Save payload to active config path
            fs.writeFileSync(CONFIG_JSON_PATH, JSON.stringify(parsed, null, 2));
            console.log("[MAIN] Imported and saved config.json");
            
            // Notify all windows that config changed
            BrowserWindow.getAllWindows().forEach(win => {
                win.webContents.send('config-updated', parsed);
            });
            
            return { success: true };
        } catch (e) {
            console.error("[MAIN] Import Config Error:", e);
            return { success: false, error: e.message };
        }
    });

    ipcMain.handle('read-secrets', async () => {
        // Prefer XDG user data dir, fallback to project root
        let secretsPath = SECRETS_PATH;
        if (!fs.existsSync(secretsPath) && fs.existsSync(LEGACY_SECRETS_PATH)) {
            secretsPath = LEGACY_SECRETS_PATH;
        }
        if (!fs.existsSync(secretsPath)) return {};
        const content = fs.readFileSync(secretsPath, 'utf8');
        const secrets = {};
        content.split('\n').forEach(line => {
            if (line.startsWith('#') || !line.trim()) return;
            const match = line.match(/^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/);
            if (match) secrets[match[1]] = match[2];
        });
        return secrets;
    });

    ipcMain.handle('save-secrets', async (event, secrets) => {
        try {
            let content = "# API Keys and Secrets - DO NOT COMMIT TO GIT\n\n";
            for (const [key, value] of Object.entries(secrets)) {
                content += `${key}=${value}\n`;
            }
            fs.writeFileSync(SECRETS_PATH, content);
            return { success: true };
        } catch (e) {
            console.error("[MAIN] Secrets Save Error:", e);
            return { success: false, error: e.message };
        }
    });

    // City / Location Resolver (Ported Logic)
    ipcMain.handle('resolve-city', async (event, cityName) => {
        const https = require('https');
        // Fallbacks for speed
        const fallbacks = {
            "New York": { lat: 40.7128, lon: -74.0060, tz: "America/New_York" },
            "Los Angeles": { lat: 34.0522, lon: -118.2437, tz: "America/Los_Angeles" },
            "Chicago": { lat: 41.8781, lon: -87.6298, tz: "America/Chicago" },
            "Miami": { lat: 25.7617, lon: -80.1918, tz: "America/New_York" },
            "Jerusalem": { lat: 31.7683, lon: 35.2137, tz: "Asia/Jerusalem" },
            "London": { lat: 51.5074, lon: -0.1278, tz: "Europe/London" },
            "Atlanta": { lat: 33.7490, lon: -84.3880, tz: "America/New_York" }
        };

        if (fallbacks[cityName]) return fallbacks[cityName];

        return new Promise((resolve) => {
            const url = `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(cityName)}&format=json&limit=1`;
            const options = { headers: { 'User-Agent': 'TradeBotSCI/1.0 (Integration for Geocoding timezones)' } };
            https.get(url, options, (res) => {
                let data = '';
                res.on('data', chunk => data += chunk);
                res.on('end', () => {
                    try {
                        const parsed = JSON.parse(data);
                        if (parsed && parsed.length > 0) {
                            const lat = parseFloat(parsed[0].lat);
                            const lon = parseFloat(parsed[0].lon);
                            
                            // Chain request to get timezone from coordinates
                            https.get(`https://api.wheretheiss.at/v1/coordinates/${lat},${lon}`, (tzRes) => {
                                let tzData = '';
                                tzRes.on('data', chunk => tzData += chunk);
                                tzRes.on('end', () => {
                                    try {
                                        const tzParsed = JSON.parse(tzData);
                                        if (tzParsed && tzParsed.timezone_id) {
                                            resolve({ lat, lon, tz: tzParsed.timezone_id });
                                        } else {
                                            resolve({ lat, lon, tz: 'UTC' }); // fallback
                                        }
                                    } catch (e) { resolve({ lat, lon, tz: 'UTC' }); }
                                });
                            }).on('error', () => resolve({ lat, lon, tz: 'UTC' }));

                        } else {
                            resolve(null);
                        }
                    } catch (e) {
                        resolve(null);
                    }
                });
            }).on('error', () => resolve(null));
        });
    });

    ipcMain.handle('read-profile-strategies', async (event, profileName) => {
        const yaml = require('js-yaml');
        if (!fs.existsSync(PROFILES_PATH)) return null;
        const content = fs.readFileSync(PROFILES_PATH, 'utf8');
        const profiles = yaml.load(content);
        return profiles?.profiles?.[profileName]?.strategies || null;
    });

    ipcMain.handle('save-profile-strategies', async (event, profileName, strategies) => {
        const yaml = require('js-yaml');
        if (!fs.existsSync(PROFILES_PATH)) return { success: false, error: 'Profiles file missing' };
        const content = fs.readFileSync(PROFILES_PATH, 'utf8');
        const profiles = yaml.load(content);

        if (!profiles.profiles) profiles.profiles = {};
        if (!profiles.profiles[profileName]) profiles.profiles[profileName] = {};

        profiles.profiles[profileName].strategies = strategies;

        fs.writeFileSync(PROFILES_PATH, yaml.dump(profiles, { lineWidth: -1 }));
        return { success: true };
    });

    // Analytics IPC Handlers
    ipcMain.handle('get-trade-history', async (event, filter = '24h', paperMode = false) => {
        console.log('[ANALYTICS-IPC] get-trade-history called with filter:', filter, 'paperMode:', paperMode);
        try {
            const data = await logParser.getTradeHistory(filter, paperMode);
            console.log('[ANALYTICS-IPC] Trade history result - trades:', data.trades?.length, 'capital:', data.capital?.length);
            return { success: true, data };
        } catch (error) {
            console.error('[ANALYTICS-IPC] Error getting trade history:', error);
            return { success: false, error: error.message };
        }
    });

    ipcMain.handle('get-analytics-summary', async (event, filter = '24h', paperMode = false) => {
        console.log('[ANALYTICS-IPC] get-analytics-summary called with filter:', filter, 'paperMode:', paperMode);
        try {
            const data = await logParser.getTradeHistory(filter, paperMode);
            console.log('[ANALYTICS-IPC] Raw data - trades:', data.trades?.length, 'capital:', data.capital?.length);
            const summary = logParser.calculateAnalyticsSummary(data, paperMode);
            console.log('[ANALYTICS-IPC] Summary calculated - totalTrades:', summary.totalTrades);
            return { success: true, data: summary };
        } catch (error) {
            console.error('[ANALYTICS-IPC] Error calculating summary:', error);
            return { success: false, error: error.message };
        }
    });

    ipcMain.handle('get-log-files', async () => {
        try {
            const files = logParser.getLogFiles();
            return { success: true, data: files };
        } catch (error) {
            return { success: false, error: error.message };
        }
    });

    // =============================================
    // Help Documentation
    // =============================================
    const DOCS_DIR = path.join(__dirname, '../../../Documentation');
    const RTFM_DIR = path.join(DOCS_DIR, 'RTFM');

    // Dynamically build HELP_CATALOG from markdown frontmatter
    function _scanHelpCatalog() {
        const yaml = require('js-yaml');
        const catalog = [];
        const directories = ['', 'RTFM', 'adr'];
        
        for (const dir of directories) {
            const targetDir = path.join(DOCS_DIR, dir);
            if (!fs.existsSync(targetDir)) continue;
            
            const files = fs.readdirSync(targetDir);
            for (const file of files) {
                if (!file.endsWith('.md')) continue;
                
                const filePath = path.join(targetDir, file);
                const content = fs.readFileSync(filePath, 'utf8');
                
                const filename = dir ? `${dir}/${file}` : file;
                let meta = null;
                
                if (content.startsWith('---')) {
                    const parts = content.split('---');
                    if (parts.length >= 3) {
                        try {
                            const parsedMeta = yaml.load(parts[1].trim());
                            if (parsedMeta && parsedMeta.title && parsedMeta.description) {
                                meta = { 
                                    filename, 
                                    title: parsedMeta.title, 
                                    category: parsedMeta.category || 'rtfm', 
                                    icon: parsedMeta.icon || 'article', 
                                    description: parsedMeta.description,
                                    featured: !!parsedMeta.featured
                                };
                            }
                        } catch (e) {
                            console.error(`[MAIN] Failed to parse frontmatter in ${filename}:`, e.message);
                        }
                    }
                }
                
                // Only push if it has valid metadata
                if (meta) {
                    catalog.push(meta);
                }
            }
        }
        return catalog;
    }

    let HELP_CATALOG = [];
    try {
        HELP_CATALOG = _scanHelpCatalog();
        console.log(`[MAIN] Dynamically loaded ${HELP_CATALOG.length} documents from Documentation/`);
    } catch (e) {
        console.error('[MAIN] Failed to dynamically load doc catalog:', e);
    }

    try {
        // ── App Version ──
        ipcMain.handle('get-app-version', async () => {
            const versionFile = path.join(__dirname, '../../../VERSION');
            try {
                return fs.readFileSync(versionFile, 'utf8').trim();
            } catch (_) {
                return '0.0.0';
            }
        });

        ipcMain.handle('list-help-docs', async () => {
            // Re-scan on every request so new articles are discovered
            // without restarting the Electron app
            HELP_CATALOG = _scanHelpCatalog();
            console.log('[MAIN] list-help-docs handler called, returning', HELP_CATALOG.length, 'docs');
            return { success: true, data: HELP_CATALOG };
        });

        ipcMain.handle('read-help-doc', async (event, filename) => {
            try {
                // Security: only allow filenames from the catalog
                const valid = HELP_CATALOG.find(d => d.filename === filename);
                if (!valid) return { success: false, error: 'Invalid document' };

                const filePath = path.join(DOCS_DIR, filename);
                const resolved = path.resolve(filePath);
                if (!resolved.startsWith(path.resolve(DOCS_DIR))) {
                    return { success: false, error: 'Path traversal denied' };
                }

                if (!fs.existsSync(filePath)) {
                    return { success: false, error: `Document not found: ${resolved}` };
                }

                let content = fs.readFileSync(filePath, 'utf8');

                // Strip YAML frontmatter before sending to the UI
                if (content.startsWith('---')) {
                    const parts = content.split('---');
                    if (parts.length >= 3) {
                        content = parts.slice(2).join('---').trimStart();
                    }
                }

                // Resolve relative image paths to base64 data URIs so Electron can display them
                // (file:// protocol is blocked by webSecurity)
                const docDir = path.dirname(resolved);
                content = content.replace(/!\[([^\]]*)\]\((?!https?:\/\/|data:)([^)]+)\)/g, (match, alt, relPath) => {
                    try {
                        const absPath = path.resolve(docDir, relPath);
                        if (fs.existsSync(absPath)) {
                            const ext = path.extname(absPath).toLowerCase().replace('.', '');
                            const mime = { png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', gif: 'image/gif', svg: 'image/svg+xml', webp: 'image/webp' }[ext] || 'image/png';
                            const b64 = fs.readFileSync(absPath).toString('base64');
                            return `![${alt}](data:${mime};base64,${b64})`;
                        }
                    } catch (e) { console.warn('[MAIN] Failed to embed image:', relPath, e.message); }
                    return match;
                });

                // Also resolve <img src="..."> HTML tags (used in avatar dialogue tables)
                content = content.replace(/<img\s+src="(?!https?:\/\/|data:)([^"]+)"/g, (match, relPath) => {
                    try {
                        const absPath = path.resolve(docDir, relPath);
                        if (fs.existsSync(absPath)) {
                            const ext = path.extname(absPath).toLowerCase().replace('.', '');
                            const mime = { png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', gif: 'image/gif', svg: 'image/svg+xml', webp: 'image/webp' }[ext] || 'image/png';
                            const b64 = fs.readFileSync(absPath).toString('base64');
                            return `<img src="data:${mime};base64,${b64}"`;
                        }
                    } catch (e) { console.warn('[MAIN] Failed to embed HTML img:', relPath, e.message); }
                    return match;
                });

                return { success: true, data: { filename, title: valid.title, content } };
            } catch (error) {
                return { success: false, error: error.message };
            }
        });
        console.log('[MAIN] Help IPC handlers registered successfully');
    } catch (err) {
        console.error('[MAIN] FAILED to register help IPC handlers:', err);
    }

    // =============================================
    // Paper data lives in the XDG user data dir (same as Python _paths.DATA_DIR)
    const DATA_DIR = path.join(USER_DATA_DIR, 'data');

    // ── Theme persistence (filesystem-backed) ──
    const themePath = path.join(USER_DATA_DIR, 'theme-state.json');
    ipcMain.handle('save-theme', async (_event, themeId) => {
        try { fs.writeFileSync(themePath, JSON.stringify({ theme: themeId })); } catch (e) { }
        return true;
    });
    ipcMain.handle('get-theme', async () => {
        try {
            if (fs.existsSync(themePath)) {
                const data = JSON.parse(fs.readFileSync(themePath, 'utf8'));
                return data.theme || null;
            }
        } catch (e) { }
        return null;
    });

    ipcMain.handle('reset-paper-trading', async () => {
        console.log('[MAIN] Resetting paper trading...');

        // Step 1: Kill the bot process
        const killCmd = isWindows() ? 'taskkill /F /IM python.exe' : 'pkill -f "[r]un_dev_bot.py"';
        await new Promise((resolve) => {
            exec(killCmd, (err) => {
                if (err && err.code !== 1) console.warn('[MAIN] Kill during reset:', err.message);
                resolve();
            });
        });

        // Step 2: Wait until process is confirmed dead (poll up to 10s)
        const maxWaitMs = 10000;
        const pollMs = 500;
        let waited = 0;
        while (waited < maxWaitMs) {
            const alive = await new Promise(resolve => {
                exec('pgrep -f "[r]un_dev_bot.py"', (err, stdout) => {
                    resolve(!!(stdout && stdout.trim()));
                });
            });
            if (!alive) break;
            await new Promise(r => setTimeout(r, pollMs));
            waited += pollMs;
        }
        console.log(`[MAIN] Bot stopped after ${waited}ms`);

        // Load starting balance from config
        let initialBalance = 10000.0;
        try {
            // Use the same config path resolution as the read-config handler
            let configPath = CONFIG_JSON_PATH;
            if (!fs.existsSync(configPath) && fs.existsSync(LEGACY_CONFIG_JSON_PATH)) {
                configPath = LEGACY_CONFIG_JSON_PATH;
            }
            
            if (fs.existsSync(configPath)) {
                const configStr = fs.readFileSync(configPath, 'utf8');
                const conf = JSON.parse(configStr);
                const profList = conf.profiles || {};
                
                // Get active profile name
                let actProfName = conf.active_profile || 'default';
                let profRaw = profList[actProfName] || {};
                
                // Read from profile (settings UI saves as lowercase key via updateValue)
                const profBalance = profRaw.paper_balance ?? profRaw.PAPER_BALANCE;
                if (profBalance != null) {
                    initialBalance = parseFloat(profBalance);
                } else if (conf.global && (conf.global.paper_balance ?? conf.global.PAPER_BALANCE)) {
                    initialBalance = parseFloat(conf.global.paper_balance ?? conf.global.PAPER_BALANCE);
                }
                console.log(`[MAIN] Read PAPER_BALANCE=${initialBalance} from ${configPath} (profile=${actProfName})`);
            }
        } catch (e) {
            console.error('[MAIN] Failed to read PAPER_BALANCE from config, defaulting to 10000.0', e);
        }

        if (isNaN(initialBalance) || initialBalance <= 0) {
            initialBalance = 10000.0;
        }

        // Step 3: Delete paper trading data files
        try {
            const now = new Date().toISOString();

            // paper_state.json
            const paperState = {
                balance: initialBalance,
                positions: {},
                updated_at: now,
                last_reset_at: now
            };
            fs.writeFileSync(path.join(DATA_DIR, 'paper_state.json'), JSON.stringify(paperState, null, 2));

            // paper_ledger.json
            const paperLedger = {
                version: 1,
                last_updated: now,
                last_reset_at: now,
                sundown_timezone: "America/New_York",
                current_day: {
                    day_start: "",
                    pnl_realized: 0.0,
                    pnl_unrealized: 0.0,
                    trades: 0,
                    wins: 0,
                    losses: 0,
                    capital_at_start: initialBalance,
                    capital_now: initialBalance,
                    best_trade: 0.0,
                    worst_trade: 0.0,
                    by_symbol: {},
                    by_strategy: {},
                    spread_costs: 0.0,
                    trade_log: []
                },
                days: []
            };
            fs.writeFileSync(path.join(DATA_DIR, 'paper_ledger.json'), JSON.stringify(paperLedger, null, 2));

            // paper_trade_results.json
            fs.writeFileSync(path.join(DATA_DIR, 'paper_trade_results.json'), '[]');

            // Truncate ghost logs so log_analytics.js doesn't pull old trades into the UI
            const stdoutLog = path.join(USER_DATA_DIR, 'logs', 'bot_stdout.log');
            const tradebotLog = path.join(USER_DATA_DIR, 'logs', 'tradebot.log');
            if (fs.existsSync(stdoutLog)) fs.writeFileSync(stdoutLog, '');
            if (fs.existsSync(tradebotLog)) fs.writeFileSync(tradebotLog, '');

            console.log(`[MAIN] Paper trading files reset to $${initialBalance.toFixed(2)}, ghost logs truncated`);
        } catch (err) {
            console.error('[MAIN] Failed to reset paper files:', err.message);
            return { success: false, error: err.message };
        }

        // Step 4: Restart the bot
        setTimeout(() => {
            ipcMain.emit('start-bot');
        }, 1000);

        // Step 5: Reload all GUI windows to reflect clean state
        setTimeout(() => {
            BrowserWindow.getAllWindows().forEach(win => {
                win.webContents.send('fromMain', { type: 'gui-notice', message: `Paper Trading Reset to $${initialBalance.toLocaleString()}`, color: 'teal' });
                win.reload();
            });
        }, 3000);

        return { success: true };
    });

    ipcMain.handle('take-paper-payout', async (event, amount) => {
        try {
            const paperStatePath = path.join(DATA_DIR, 'paper_state.json');
            if (fs.existsSync(paperStatePath)) {
                let state = JSON.parse(fs.readFileSync(paperStatePath, 'utf8'));
                if (state.balance) {
                    state.balance -= amount;
                    state.updated_at = new Date().toISOString();
                    fs.writeFileSync(paperStatePath, JSON.stringify(state, null, 2));
                    console.log(`[MAIN] Payout simulated: deducted $${amount.toFixed(2)} from Paper balance.`);
                    // Let the bot know state changed if necessary
                    return { success: true };
                }
            }
            return { success: false, error: 'No paper state found' };
        } catch (e) {
            console.error('[MAIN] Payout Error:', e);
            return { success: false, error: e.message };
        }
    });

    // =============================================
    // Backtest — Recording Info & Execution
    // =============================================
    const CANDLE_HISTORY_DIR = path.join(USER_DATA_DIR, 'data', 'candle_history');

    ipcMain.handle('get-recording-info', async () => {
        try {
            if (!fs.existsSync(CANDLE_HISTORY_DIR)) {
                return { symbols: [], earliest: null, latest: null };
            }
            const symbols = [];
            let globalEarliest = null;
            let globalLatest = null;

            const dirs = fs.readdirSync(CANDLE_HISTORY_DIR, { withFileTypes: true });
            for (const d of dirs) {
                if (!d.isDirectory()) continue;
                symbols.push(d.name);
                const symDir = path.join(CANDLE_HISTORY_DIR, d.name);
                const files = fs.readdirSync(symDir).filter(f => f.endsWith('.jsonl'));
                for (const f of files) {
                    const match = f.match(/_(\d{4}-\d{2}-\d{2})\.jsonl$/);
                    if (match) {
                        const date = match[1];
                        if (!globalEarliest || date < globalEarliest) globalEarliest = date;
                        if (!globalLatest || date > globalLatest) globalLatest = date;
                    }
                }
            }
            return { symbols: symbols.sort(), earliest: globalEarliest, latest: globalLatest };
        } catch (e) {
            console.error('[MAIN] get-recording-info error:', e);
            return { symbols: [], earliest: null, latest: null };
        }
    });

    ipcMain.handle('run-backtest', async (_event, config) => {
        console.log('[MAIN] run-replay called (Replayer):', JSON.stringify(config));
        try {
            const { spawn } = require('child_process');

            // ── Resolve engine_replay.py path (Minovsky Engine) ───────────────
            const minovskyPath = path.join(__dirname, '../../../tools/engine/engine_replay.py');
            const replayPath = path.join(__dirname, '../../../tools/paper_replay.py');
            const enginePath = fs.existsSync(minovskyPath) ? minovskyPath : replayPath;
            if (!fs.existsSync(enginePath)) {
                return { error: 'Minovsky Engine (engine_replay.py) not found.' };
            }

            let args;
            if (enginePath === minovskyPath) {
                // Minovsky Engine mode — uses date range and symbols
                args = [enginePath, '--api-fallback'];
                if (config.start_date) args.push('--start-date', config.start_date);
                if (config.end_date) args.push('--end-date', config.end_date);
                if (config.symbols && config.symbols.length > 0) {
                    args.push('--symbols', config.symbols.join(','));
                }
                if (config.balance) args.push('--balance', String(config.balance));
                if (config.strategy) args.push('--strategy', config.strategy);
                if (config.risk_rate) args.push('--risk-rate', String(config.risk_rate));
            } else {
                // Fallback: paper_replay.py
                args = [enginePath, '--json-output', '--speed', '0', '--api-fallback'];
                if (config.start_date) args.push('--start-date', config.start_date);
                if (config.end_date) args.push('--end-date', config.end_date);
                if (config.symbols && config.symbols.length > 0) {
                    args.push('--symbols', config.symbols.join(','));
                }
                if (config.balance) args.push('--balance', String(config.balance));
                if (config.strategy) args.push('--strategy', config.strategy);
                if (config.risk_rate) args.push('--risk-rate', String(config.risk_rate));
            }
            // ── Find Python ───────────────────────────────────────────────────
            let pythonExe = 'python3';
            for (const candidate of ['python3', 'python']) {
                try {
                    require('child_process').execSync(`${candidate} --version`, { stdio: 'pipe' });
                    pythonExe = candidate;
                    break;
                } catch (_) { continue; }
            }

            console.log(`[MAIN] Spawning: ${pythonExe} ${args.join(' ')}`);
            console.log(`[MAIN] config.risk_rate=${config.risk_rate} (type=${typeof config.risk_rate})`);

            // ── Get the sender window for live streaming ──────────────────────
            const senderWindow = BrowserWindow.getAllWindows()[0];

            return new Promise((resolve) => {
                let stdoutBuf = '';
                let stderrBuf = '';
                const proc = spawn(pythonExe, args, {
                    cwd: path.join(__dirname, '../../..'),
                    env: { ...process.env },
                    timeout: 1800000, // 30 min max for long replays
                    maxBuffer: 1024 * 1024 * 500, // 500 MB max buffer for massive date ranges
                    detached: true // Detach from parent Node thread
                });

                // ── Stream progress to GUI in real time ───────────────────────────
                let logThrottle = null;
                let progressState = {}; // { SYMBOL: { pct, ticks, total } }
                
                proc.stderr.on('data', (data) => {
                    stderrBuf += data.toString();
                    const lines = stderrBuf.split('\n');
                    stderrBuf = lines.pop(); // keep incomplete line buffered
                    
                    let updated = false;
                    for (const line of lines) {
                        if (!line.trim()) continue;
                        
                        // Look for structured JSON progress from Python
                        if (line.includes('{"_type": "progress"')) {
                            try {
                                // In case there's logging prefix, extract just the JSON
                                const jsonStr = line.substring(line.indexOf('{'));
                                const p = JSON.parse(jsonStr);
                                if (p._type === 'progress') {
                                    progressState[p.symbol] = p;
                                    updated = true;
                                }
                            } catch (e) {
                                // hide parse errors
                            }
                        }
                    }

                    if (updated && !logThrottle) {
                        logThrottle = setTimeout(() => {
                            if (senderWindow && !senderWindow.isDestroyed()) {
                                senderWindow.webContents.send('backtest-progress', progressState);
                            }
                            logThrottle = null;
                        }, 250); // 250ms interval prevents freezing UI
                    }
                });

                proc.stdout.on('data', (data) => {
                    stdoutBuf += data.toString();
                });

                proc.on('close', (code) => {
                    console.log(`[MAIN] Replayer exited with code ${code}`);

                    // Force final 100% progress update before UI renders results
                    if (senderWindow && !senderWindow.isDestroyed()) {
                        senderWindow.webContents.send('backtest-progress', {
                            'Engine': { pct: 100, symbol: 'Engine', details: '(Merging Results)' }
                        });
                        if (stderrBuf.trim()) {
                            senderWindow.webContents.send('backtest-progress', stderrBuf.trim());
                        }
                    }

                    if (code !== 0) {
                        resolve({ error: `Replayer failed (exit ${code}). Check the log stream for details.` });
                        return;
                    }

                    // ── Parse JSON summary from stdout ────────────────────────
                    try {
                        let jsonResult = null;
                        const trimmed = stdoutBuf.trim();
                        // Optimization: avoid split('\n') on massive buffers which causes V8 OOM
                        let lastBrace = trimmed.lastIndexOf('\n{');
                        if (lastBrace === -1 && trimmed.startsWith('{')) lastBrace = 0;
                        
                        if (lastBrace !== -1) {
                            const possibleJson = trimmed.substring(lastBrace).trim();
                            if (possibleJson.startsWith('{') && possibleJson.endsWith('}')) {
                                jsonResult = JSON.parse(possibleJson);
                            }
                        }
                        resolve(jsonResult || { error: 'Replay complete but no JSON summary found', raw: stdoutBuf.slice(-300) });
                    } catch (parseErr) {
                        resolve({ error: `Failed to parse replay results: ${parseErr.message}` });
                    }
                });

                proc.on('error', (err) => {
                    resolve({ error: `Failed to start Replayer: ${err.message}` });
                });
            });
        } catch (e) {
            console.error('[MAIN] run-backtest (replayer) error:', e);
            return { error: e.message };
        }
    });

    // =============================================
    // AI Recommend — Profile Optimization
    // =============================================
    ipcMain.handle('ai-recommend', async (_event, profileName, goal = 'balanced') => {
        console.log(`[MAIN] AI Recommend requested for profile: ${profileName} with goal: ${goal}`);
        try {
            // 1. Read profile data
            const yaml = require('js-yaml');
            const profilesRaw = fs.readFileSync(PROFILES_PATH, 'utf8');
            const profilesData = yaml.load(profilesRaw);
            const profile = profilesData?.profiles?.[profileName];
            if (!profile) {
                return { success: false, error: `Profile '${profileName}' not found` };
            }

            // 2. Read AI provider config from env + secrets
            const envData = {};
            if (fs.existsSync(DOTENV_PATH)) {
                fs.readFileSync(DOTENV_PATH, 'utf8').split('\n').forEach(line => {
                    const match = line.match(/^([^#=]+)=(.*)$/);
                    if (match) envData[match[1].trim()] = match[2].trim();
                });
            }
            // Also read secrets
            const secretsFile = fs.existsSync(SECRETS_PATH) ? SECRETS_PATH : LEGACY_SECRETS_PATH;
            if (fs.existsSync(secretsFile)) {
                fs.readFileSync(secretsFile, 'utf8').split('\n').forEach(line => {
                    const match = line.match(/^([^#=]+)=(.*)$/);
                    if (match) envData[match[1].trim()] = match[2].trim();
                });
            }
            // Also read config.json
            let configJson = {};
            const cfgPath = fs.existsSync(CONFIG_JSON_PATH) ? CONFIG_JSON_PATH : LEGACY_CONFIG_JSON_PATH;
            if (fs.existsSync(cfgPath)) {
                configJson = JSON.parse(fs.readFileSync(cfgPath, 'utf8'));
            }

            // Merge: env data + config.json ai section
            const aiConfig = configJson.ai || {};
            const merged = { ...envData, ...aiConfig };
            const get = (key) => merged[key] || merged[key.toLowerCase()] || merged[key.toUpperCase()] || '';
            const provider = get('provider') || get('TRADE_SCI_PROVIDER') || 'openrouter';
            const apiKeyRaw = get('TRADE_SCI_API_KEY') || get('CHATGPT_KEY') || get('OPENAI_API_KEY') || '';
            const defaultModels = { deepseek: 'deepseek-chat', openai: 'gpt-4o', claude: 'claude-3-5-sonnet-20241022', gemini: 'gemini-2.0-flash', openrouter: 'google/gemini-2.0-flash-001', local: 'llama3' };
            const model = get('model') || get('TRADE_SCI_MODEL_NAME') || defaultModels[provider] || 'deepseek-chat';
            let baseUrl = get('base_url') || get('TRADE_SCI_API_BASE_URL') || '';

            // Guard: ignore placeholder values from stale .env.example copies
            const isPlaceholder = (v) => !v || /example\.com|your_.*_here|placeholder|changeme|xxx/i.test(v);
            if (isPlaceholder(baseUrl)) baseUrl = '';
            const apiKey = isPlaceholder(apiKeyRaw) ? '' : apiKeyRaw;

            console.log(`[MAIN] AI Recommend - provider: ${provider}, model: ${model}, baseUrl: ${baseUrl}, apiKey: ${apiKey ? '***' + apiKey.slice(-6) : 'MISSING'}`);

            // No hard gate — if no API key, we fall back to GhostSpotter relay below

            // Resolve base URL from provider
            if (!baseUrl) {
                const providerUrls = {
                    openai: 'https://api.openai.com/v1',
                    openrouter: 'https://openrouter.ai/api/v1',
                    deepseek: 'https://api.deepseek.com',
                    local: 'http://localhost:11434/v1',
                };
                baseUrl = providerUrls[provider] || 'https://openrouter.ai/api/v1';
            }

            // 3. Classify symbols into asset classes
            const symbols = profile.symbols || [];
            const cryptoSuffixes = ['USD', 'USDT', 'BTC', 'ETH'];
            const forexPairs = ['EUR', 'GBP', 'JPY', 'CHF', 'AUD', 'NZD', 'CAD'];
            const assetClasses = new Set();
            for (const sym of symbols) {
                const s = sym.toUpperCase();
                if (cryptoSuffixes.some(suf => s.endsWith(suf) && s.length <= 10 && !forexPairs.some(fp => s.startsWith(fp)))) {
                    // Check if it's a forex pair (6 chars, both parts are currencies)
                    if (s.length === 6 && forexPairs.some(fp => s.startsWith(fp)) && forexPairs.concat(['USD']).some(fp => s.endsWith(fp))) {
                        assetClasses.add('forex');
                    } else {
                        assetClasses.add('crypto');
                    }
                } else if (s.length === 6 && forexPairs.concat(['USD']).some(fp => s.startsWith(fp))) {
                    assetClasses.add('forex');
                } else {
                    assetClasses.add('stocks');
                }
            }

            // 4. Gather account context for smarter recommendations
            // -- Capital by broker --
            let capitalContext = '';
            const ledgerPath = path.join(DATA_DIR, 'ledger.json');
            const oandaPosPath = path.join(DATA_DIR, 'oanda_tracked_positions.json');
            const ccxtHoldsPath = path.join(DATA_DIR, 'position_holds.json');
            const stdoutLogPath = path.join(USER_DATA_DIR, 'logs', 'bot_stdout.log');

            let totalCapital = 0;
            let brokerCapitals = {};
            let activePositions = [];
            let recentPnl = { trades: 0, wins: 0, losses: 0, pnl: 0.0 };

            // Read ledger for capital + recent performance
            if (fs.existsSync(ledgerPath)) {
                try {
                    const ledger = JSON.parse(fs.readFileSync(ledgerPath, 'utf8'));
                    totalCapital = ledger.current_day?.capital_now || ledger.current_day?.capital_at_start || 0;
                    // Last 7 days performance
                    const allDays = [...(ledger.days || []).slice(-7), ledger.current_day].filter(Boolean);
                    for (const d of allDays) {
                        recentPnl.trades += d.trades || 0;
                        recentPnl.wins += d.wins || 0;
                        recentPnl.losses += d.losses || 0;
                        recentPnl.pnl += d.pnl || 0;
                    }
                } catch (_) { /* ignore */ }
            }

            // Parse last heartbeat for live broker split
            if (fs.existsSync(stdoutLogPath)) {
                try {
                    const stat = fs.statSync(stdoutLogPath);
                    const readSize = Math.min(stat.size, 80000);
                    const fd = fs.openSync(stdoutLogPath, 'r');
                    const buf = Buffer.alloc(readSize);
                    fs.readSync(fd, buf, 0, readSize, stat.size - readSize);
                    fs.closeSync(fd);
                    const tail = buf.toString('utf8');
                    const lines = tail.split('\n');

                    // Find last OANDA Account Summary (NAV)
                    for (let i = lines.length - 1; i >= 0; i--) {
                        if (lines[i].includes('[OANDA] Account Summary:')) {
                            const m = lines[i].match(/NAV=([\d.,]+)/);
                            if (m) { brokerCapitals['OANDA'] = parseFloat(m[1].replace(/,/g, '')); break; }
                        }
                    }
                    // Find last CCXT capital
                    for (let i = lines.length - 1; i >= 0; i--) {
                        if (lines[i].includes('[CCXT] get_liquid_capital') && lines[i].includes('Cash=')) {
                            const m = lines[i].match(/Cash=\$([\d.,]+)/);
                            if (m) { brokerCapitals['Gemini (CCXT)'] = parseFloat(m[1].replace(/,/g, '')); break; }
                        }
                    }

                    // Active positions from last HOLDINGS heartbeat
                    for (let i = lines.length - 1; i >= 0; i--) {
                        if (lines[i].includes('[HOLDINGS]')) {
                            try {
                                const jsonPart = lines[i].split(/\[HOLDINGS\]/i)[1].trim();
                                const holdingsData = JSON.parse(jsonPart);
                                if (holdingsData.positions) {
                                    activePositions = holdingsData.positions.map(p => ({
                                        symbol: p.symbol,
                                        side: p.side || p.direction || 'long',
                                        size: p.size,
                                        entry: p.entry_price || p.avg_price,
                                        pnl: p.unrealized_pnl,
                                        strategy: p.strategy
                                    }));
                                }
                            } catch (_) { }
                            break;
                        }
                    }
                } catch (_) { /* ignore log read errors */ }
            }

            // Determine active brokers and fee schedules
            const ccxtExchange = (envData['CCXT_EXCHANGE_ID'] || envData['ccxt_exchange_id'] || '').toLowerCase();
            const oandaActive = !!(envData['OANDA_API_TOKEN'] || envData['OANDA_ACCOUNT_ID']);
            const ibkrActive = !!(envData['IBKR_HOST'] || envData['IBKR_PORT']);

            let feeInfo = '';
            if (ccxtExchange.includes('gemini') || envData['GEMINI_API_KEY']) {
                feeInfo += `• Gemini (Crypto): Taker fee 0.40%, Maker fee ~0.20%. Gemini does NOT support native market orders — the bot uses limit orders with a small offset. Maker-first mode tries to fill as maker for lower fees.\n`;
            }
            if (ccxtExchange.includes('coinbase')) {
                feeInfo += `• Coinbase (Crypto): Taker fee 0.60%, Maker fee ~0.40%.\n`;
            }
            if (ccxtExchange.includes('kraken')) {
                feeInfo += `• Kraken (Crypto): Taker fee 0.26%, Maker fee 0.16%.\n`;
            }
            if (oandaActive) {
                feeInfo += `• OANDA (Forex): Commission-free, but pays the bid/ask spread (typically 1-3 pips on majors). Tighter spreads on EUR/USD, wider on exotic pairs.\n`;
            }
            if (ibkrActive) {
                feeInfo += `• Interactive Brokers (Stocks/ETF): Commission ~$0.005/share. Very tight spreads.\n`;
            }
            if (!feeInfo) feeInfo = '• No broker fee info detected.\n';

            // Build the capital context string
            const brokerLines = Object.entries(brokerCapitals).map(([b, v]) => `  ${b}: $${v.toFixed(2)}`).join('\n');
            const posLines = activePositions.map(p => `  ${p.symbol} ${p.side} ${p.size}@${p.entry} | PnL: $${(p.pnl || 0).toFixed(2)} | Strategy: ${p.strategy || '?'}`).join('\n');
            const winRate = recentPnl.trades > 0 ? ((recentPnl.wins / recentPnl.trades) * 100).toFixed(0) : 'N/A';

            // 5. Build the comprehensive prompt
            const prompt = `You are a trading bot configuration expert. A user has a profile called "${profileName}" with these symbols:

${symbols.join(', ')}

Asset classes detected: ${[...assetClasses].join(', ')}
Strategies configured: ${JSON.stringify(profile.strategies || {})}

═══════════════════════════════════════════════════
ACCOUNT CONTEXT (use this to calibrate risk, sizing, and strategy aggressiveness)
═══════════════════════════════════════════════════
Total Capital: $${totalCapital.toFixed(2)}
Capital by Broker:
${brokerLines || '  (not available)'}

Active Brokers & Fee Schedules:
${feeInfo}
Active Positions:
${posLines || '  (none)'}

Recent Performance (last 7 days):
  Trades: ${recentPnl.trades} | Wins: ${recentPnl.wins} | Losses: ${recentPnl.losses} | Win Rate: ${winRate}% | Net PnL: $${recentPnl.pnl.toFixed(2)}

KEY CONSTRAINTS:
• This is a SMALL ACCOUNT — risk sizing must account for broker fees eating a larger % of each trade.
• On Gemini, each round-trip costs ~0.80% in fees. A 1% take-profit barely breaks even after fees. Factor this into R:R targets.
• If OANDA is active, forex spreads are the hidden cost — wider stops absorb spread better.
• Greed guard targets should be proportional to actual account size, not arbitrary large numbers.

    Analyze these symbols and asset classes, then recommend OPTIMAL settings across these 4 categories.
    
    USER OPTIMIZATION GOAL: ${goal.toUpperCase().replace('_', ' ')}
    ${goal === 'capital_preservation' ? '• Focus strictly on capital preservation. Recommend the safest strategies (e.g. ones with low drawdowns). Set risk per trade very low (0.5% or less), enable all safety shields, use tight stop losses, and take profits early.' : ''}
    ${goal === 'capital_flipping' ? '• Focus on aggressive growth (Capital Flipping). Recommend high-frequency, high-reward strategies. Increase risk per trade (2-3%), loosen safety shields, use wider stops to avoid getting chopped out, and aim for large trend-following runners.' : ''}
    ${goal === 'balanced' ? '• Focus on a balanced approach of steady growth and reasonable safety. Use normal risk limits (1-2%).' : ''}
    
    IMPORTANT: Do NOT recommend conflicting settings. For example, don't enable both Stability Mode AND aggressive multipliers.
    IMPORTANT: This is a DAY TRADING bot operating on 5-minute charts. Trades should be held for minutes to hours, NOT days. Max hold times should be 4-12 hours, never 24-48 hours. Favor quick entries, tight stops, and decisive exits. This is NOT a swing trading or position trading system.

═══════════════════════════════════════════════════
CATEGORY 1: STRATEGY WORKSHOP
═══════════════════════════════════════════════════

── Strategy Per Asset Class ──
Choose the best strategy for each detected asset class. Set ONLY env keys for asset classes present in this profile.

Available env keys:
• STRATEGY_CRYPTO (string): Strategy for crypto symbols
• STRATEGY_FOREX (string): Strategy for forex pairs
• STRATEGY_STOCKS (string): Strategy for individual stocks
• STRATEGY_ETF (string): Strategy for ETFs
• STRATEGY_METALS (string): Strategy for precious metals
• STRATEGY_FUTURES (string): Strategy for futures contracts

Available strategies (pick one per asset class):
• "rubberband_reaper" — Anti-Martingale Mean Reversion. Uses Bollinger Bands + RSI to catch reversals at extremes. Increases size after wins, decreases after losses. Best for: ranging markets, volatile assets. Risk: Adaptive.
• "robocop" — Aggressive High-Frequency ICC. Lightning-fast with minimal confirmation. Best for: trending markets, high volatility. Risk: High.
• "evolution" — NTZ Range Scalper. Trades liquidity sweeps at range edges. Best for: sideways markets, consolidation. Risk: Low-Medium.
• "quantum" — Trend-Following SMA Pullback. Waits for pullback to 20 SMA, enters with HTF/LTF alignment. Risk: Medium.
• "mean_reversion" — Bollinger + RSI Extremes. Enters when price breaks outside bands with RSI confirmation. Best for: ranging crypto and forex. Risk: Medium.
• "hyper_scalper" — EMA Crossover Speed Trading. High-frequency 5min scalper using 9/21/200 EMA. Risk: High.
• "london_breakout" — Session Opening Range Breakout. Trades London session range breakout. Best for: GBP pairs, European session. Risk: Medium.
• "volatility_breakout" — Range Expansion Momentum. Catches breakouts from 20-period range with RSI. Risk: Medium-High.
• "icc_core" — Pure ICT methodology. Displacement + OTE zone pullback + FVG entry. Best for: aligned trends. Risk: Low-Medium.
• "supply_demand" — Supply & Demand zones with Break of Structure. Risk: Low-Medium.
• "meta_sci" — AI-Enhanced Ensemble. Runs multiple strategies simultaneously; AI picks the best one per trade. Risk: Dynamic.
• "trend_rider" — EMA Pullback in Strong Trend. Waits for pullback to 21 EMA during confirmed trend. Risk: Medium.
• "session_momentum" — VWAP + Volume Surge at session open. Active first 30 min of London/NY. Risk: Medium-High.
• "bearish_engulfing" — Engulfing candle pattern at key structure with HTF alignment. Best for: reversal zones. Risk: Medium.
• "crypto_rsi_macd" — RSI + MACD combo for 24/7 crypto. No session gating. Best for: trending crypto, BTC/ETH swings. Risk: Medium.
• "crypto_vwap_reversion" — Mean reversion to VWAP using Bollinger bands + volume. Best for: ranging crypto, high-volume pairs. Risk: Medium.
• "crypto_double_macd" — Dual-timeframe MACD scalper for tight crypto scalps. Best for: active crypto, BTC/SOL. Risk: High.
• "crypto_grid" — Virtual grid trading with dynamic ATR-based levels. Best for: sideways/ranging crypto. Risk: Medium-High.
• "conductor" — The Forex Conductor. Regime-based strategy router: trending → Trend Rider (EMA pullback), ranging → Mean Reversion (Bollinger bounce), transitional → Session Breakout, choppy → BLOCK all entries. Conservative gates: HTF/LTF alignment required, 2h entry cooldown, loss streak cooldown. Cuts losers to ~$3-8, trades in bursts when conditions align. Best for: all forex regimes (EUR/USD, GBP/USD). Risk: Dynamic (conservative gates).

═══════════════════════════════════════════════════
BACKTESTED STRATEGY RATINGS (14-day audit, real broker fees, realistic exits)
═══════════════════════════════════════════════════
Use these ratings to guide your recommendations. Prefer A-rated strategies for each asset class.

── FOREX Ratings (OANDA, ~1.4 pip EUR/USD, ~2.0 pip GBP/USD spread) ──
Results on $2K capital / $100 capital (14 days):
A  london_breakout  — Best forex strategy. +$254/$12.68 (67% WR). Low DD (5.4%). London session 08-12 UTC.
A  volatility_breakout — Strong. +$122/$6.08 (34% WR). Good R:R on breakout moves. Asian session 00-08 UTC.
B  hyper_scalper    — Profitable. +$104/$5.20 (44% WR). Quick EMA scalps with proper stops. All sessions.
B  icc_core         — Profitable. +$78/$3.88 (55% WR). ICT methodology solid on forex. All sessions.
B  meta_sci         — Profitable. +$38/$1.91 (36% WR). Judge system selects proven winners per session.
B  orb_breakout     — Profitable. +$33/$1.64 (33% WR). US open session 13-16 UTC.
D  session_momentum — Near breakeven. -$18 (50% WR). Only 2 trades, needs more data.
D  evolution        — Slight loss. -$57 (36% WR). NTZ margin tight after fees.
D  crypto_double_macd — -$73 (41% WR). Close to breakeven with tuning.
D  bearish_engulfing — -$142 (26% WR). Pattern timing needs work.
F  robocop          — -$245 (33% WR). High variance, needs wider stops.
F  supply_demand    — -$250 (25% WR). Zone detection noisy on 15m.
F  trend_rider      — -$341 (29% WR). EMA pullbacks too frequent on choppy forex.
F  quantum          — -$454 (18% WR). Trend following loses on choppy forex.

── CRYPTO Ratings (Gemini ActiveTrader, 0.25% taker per side = 0.50% RT) ──
ALL STRATEGIES UNPROFITABLE on crypto due to 0.50% round-trip fees.
Fee drag makes 15m strategies unviable. Consider longer timeframes or lower-fee exchanges.
D  rubberband_reaper — Nearly breakeven. -$57 (80% WR). Best crypto option if forced.
F  All others — Heavy losses. 0.5% RT fees dominate profit on every strategy.
F  supply_demand    — -$1908 (13% WR). Zone detection too noisy on crypto.
F  meta_sci         — -$1959 (21% WR). AI ensemble picks losers on crypto.

── RATING KEY ──
A = Highly recommended. Backtested profitable with good consistency.
B = Recommended. Backtested profitable, some limitations.
C = Acceptable. Profitable but low confidence (few trades or high variance).
D = Not recommended. Marginal or unprofitable after fees.
F = Avoid. Lost significant capital in backtesting.

── Global Risk Limits ──
• RISK_PER_TRADE_PCT (number, 0.1-20): Percentage of account equity risked per trade. Conservative=1-2%, moderate=2-4%, aggressive=4+%.
• MAX_EXPOSURE_PCT (number, 5-100): Maximum total portfolio exposure across all open positions.
• LIMIT_LOSS_DAILY_PCT (number, 1-20): Circuit breaker — stops all trading for the day if this % is lost. Safety net.
• RISK_PER_TRADE_DOLLARS (number): Fixed dollar amount risked per trade. Overrides % if set. Use 0 to disable.
• MAX_LOSS_PER_TRADE_DOLLARS (number): Hard dollar cap on any single trade loss.

── Pyramid Configuration ──
• MAX_PYRAMID_ENTRIES (number, 1-20): Max times the bot adds to a winning position. 1=no pyramiding.
• PYRAMID_RISK_LOAD (number, 5-100): Risk % for the first pyramid add.
• PYRAMID_RISK_SCALE (number, 5-50): Risk % for subsequent pyramid adds (usually lower than load).

── Breakeven Trail ──
• BREAKEVEN_TRAIL_AFTER_PYRAMIDS (number, 0-10): Move stop to breakeven after N pyramid entries. 0=disabled.

── Exit Configuration ──
• AUTO_FLATTEN_ON_CLOSE (boolean): Auto-close all positions at market session end.
• TRAILING_STOP_ENABLED (boolean): Enable trailing stop that follows price up, locking in profits.
• RISK_REWARD_RATIO (number, 1-5): Target reward as multiple of risk. 2.0 = risk $1, target $2.
• TRAILING_STOP_MIN_PROFIT_PCT (number, 0-10): Minimum profit % before trailing stop activates.

── Stop-and-Reverse (Conductor Strategy) ──
Enable these ONLY when the Conductor strategy is active. The Conductor uses these to flip direction when a stop loss fires — catching the move that just stopped us out.
• STOP_AND_REVERSE_ENABLED (boolean): When a stop fires, immediately enter in the opposite direction. Works best in trending markets. Default: true for Conductor, false for others.
• REVERSAL_TP_R (number, 0.5-3.0): Take-profit target for reversal trades, as a multiple of risk. 1.0 = quick 1R grab. Higher values let reversals run but reduce win rate. Default: 1.0.
• REVERSAL_COST_AWARE_TP (boolean): Pad the reversal TP target by the broker spread/fee so the NET profit is a true 1R. Essential for OANDA where spread eats ~10% of a typical reversal. Default: true.
• REVERSAL_RISK_PER_TRADE (number, 0.01-0.10): Risk % of capital on each reversal trade. Higher than normal entry risk because reversals catch confirmed momentum. Default: 0.045 (4.5%).
• SCALE_OUT_FRACTION (number, 0.25-1.0): Fraction of position to close on de-risk (loss mitigation). 0.95 = close 95% at -0.3R, leaving only 5% for the stop to hit. Default: 0.95.

── Hold Time Rules ──
• MIN_HOLD_HOURS (number, 0-48): Minimum time to hold a trade. Prevents premature exits from noise.
• MAX_HOLD_HOURS (number, 0-168): Force exit stale positions. 0=disabled.
• HTF_NEUTRAL_EXIT_BARS (number, 0-200): Exit after N bars of neutral higher-timeframe trend.

═══════════════════════════════════════════════════
CATEGORY 2: SAFETY & SHIELDS (no nuclear overrides)
═══════════════════════════════════════════════════

── Position Protection ──
• MULTI_POSITION_ENABLED (boolean): Allow trading multiple symbols simultaneously.
• MAX_CONCURRENT_POSITIONS (number, 1-10): Max open positions at once.
• SMART_POSITIONS_ENABLED (boolean): Fund new position risk using unrealized profits from existing winners.

── Account Safety ──
• SAFETY_STABILITY_MODE_ENABLED (boolean): Forces 1% max risk + 75+ quality score floor. Emergency brake for bleeding accounts.
• SAFETY_ATR_SHIELD_ENABLED (boolean): Volatility-adjusted stop-loss & breakeven protection (ATR Armor).
• STOP_ATR_MULTIPLIER (number, 0.5-5): Stop distance as multiple of ATR. Lower=tighter stops, higher=wider stops.
• BREAKEVEN_TRAIL_PCT (number, 0-5): Lock in risk-free at this profit level %.
• SAFETY_DRAWDOWN_BREAKER_ENABLED (boolean): Emergency circuit breaker — stops trading if account drawdown from HWM exceeds threshold. Uses adaptive scaling by default.
• SAFETY_DRAWDOWN_MAX_PCT (number, 0.05-0.25): Maximum drawdown % before Drawdown Breaker triggers (0.05=5%, 0.25=25%). The bot auto-scales this based on account size (25% for <$100, 15% for $500, 10% for $1K, 5% for $10K+). Set this to override the auto-scaled value — but the bot will always use whichever is MORE generous (higher) between your setting and the adaptive calculation.
• SAFETY_SESSION_LOCKOUT_ENABLED (boolean): Block new entries after a cutoff time.
• SAFETY_ROLLOVER_DEADZONE_ENABLED (boolean): Block entries during the 5 PM EST Oanda spread spike.
• SAFETY_SESSION_LOCKOUT_HOUR (number): EST hour for session lockout (e.g., 16 = 4PM).
• SAFETY_GREED_GUARD_ENABLED (boolean): Stops trading after hitting daily profit target.
• SAFETY_GREED_GUARD_TARGET (number, 5-500): Dollar profit amount that triggers greed guard lockout. REQUIRED when GREED_GUARD is enabled. Scale to account size (e.g., $50 acct → $5-10, $500 acct → $25-50, $5000 acct → $100-250).
• SAFETY_CHURN_BURNER_ENABLED (boolean): Rate limiter — prevents overtrading.
• SAFETY_CHURN_BURNER_MAX (number, 1-20): Max trades allowed per hour.
• SAFETY_LEVERAGE_SENTRY_ENABLED (boolean): Block entries above leverage cap.
• SAFETY_MAX_TOTAL_LEVERAGE (number, 1-50): Maximum total leverage allowed.
• SAFETY_VOLATILITY_VETO_ENABLED (boolean): Block entries if ATR is too Low or too High.
• SAFETY_STREAK_BREAKER_ENABLED (boolean): Pauses a symbol for 4h after 3 consecutive losses.
• SAFETY_OPENING_SENTRY_ENABLED (boolean): Avoid first 15 mins of market open (9:30-9:45 ET). Only relevant for stocks/forex.

── Advanced Exit Shields ──
• SAFETY_STALE_SNIPER_ENABLED (boolean): Terminate trades after N bars of no progress.
• SAFETY_STALE_SNIPER_BARS (number, 5-100): Max bars before stale sniper kills the trade.
• SAFETY_FLASH_TRAP_ENABLED (boolean): Exit instantly on extreme ATR spikes (flash crash protection).
• SAFETY_REGIME_FLIP_ENABLED (boolean): Exit if higher-timeframe trend turns against position.
• BLOCK_COUNTER_TREND_ENTRIES (boolean): Block entries that go against the higher-timeframe trend.

═══════════════════════════════════════════════════
CATEGORY 3: PERFORMANCE & PROFITS
═══════════════════════════════════════════════════

── Risk Foundation (pick EXACTLY ONE) ──
• PERFORMANCE_MODE_NONE (boolean): Standard fixed % risk per trade. The baseline.
• PERFORMANCE_MODE_STABILITY (boolean): Survival mode — 1% cap + 75+ quality floor. CONFLICTS with aggressive multipliers.
• PERFORMANCE_MODE_KELLY (boolean): Kelly Criterion — mathematical optimal sizing based on win rate.
• PERFORMANCE_MODE_FLYWHEEL (boolean): Compound flywheel — increases risk at profit milestones.
• PERFORMANCE_MODE_SMOOTH (boolean): Equity smoothing — cuts risk on losing days, boosts on winning days.

── Multipliers (stackable, enable any combination) ──
• PERFORMANCE_MODE_SNIPER (boolean): 1.5x risk on A+ setups (confidence score >90).
• PERFORMANCE_MODE_REGIME_SYNC (boolean): Adjust risk 0.5x-1.5x based on HTF trend strength.
• PERFORMANCE_MODE_HOUSE_MONEY (boolean): 1.5x risk when financed by locked profit from another trade.
• PERFORMANCE_MODE_WHALE (boolean): 1.3x boost on volume 2x above average (institutional activity).
• PERFORMANCE_MODE_CONTRARIAN (boolean): 1.5x boost on RSI reversal fades (contrarian plays).
• PERFORMANCE_MODE_SURFER (boolean): 2.0x boost on post-news volatility compression breakouts.
• PERFORMANCE_MODE_HYDRA (boolean): Correlation-aware sizing — prevents double-risk on correlated pairs.
• PERFORMANCE_MODE_COIL (boolean): 2x risk on breakouts from extended low-volatility periods.
• PERFORMANCE_MODE_ALPHA (boolean): 1.2x boost during key session overlaps (London/NY).
• PERFORMANCE_MODE_GAMMA (boolean): 1.2x boost on vertical price velocity surges. CONFLICTS with standard trailing stops.
• PERFORMANCE_MODE_GHOST (boolean): 1.5x boost at psychological price levels (round numbers, order blocks).
• PERFORMANCE_MODE_PHOENIX (boolean): Recovery boost on first trade after a losing streak pause.
• PERFORMANCE_MODE_RUNNER (boolean): Keep 50% position open with trail after target (moonshot catcher).

── Wealth Weapons (Advanced Exits) ──
• WEALTH_EXIT_GAMMA_ENABLED (boolean): Exponentially tighter trailing stop on vertical moves.
• WEALTH_EXIT_MOONSHOT_ENABLED (boolean): Double target if 1R profit is hit in <3 bars.
• WEALTH_EXIT_BLOWOFF_ENABLED (boolean): Sell 100% on volatility exhaustion peak.

── P&L Targets ──
• TARGET_PROFIT_DAILY_PCT (number, 0-10): Stop trading for the day once this % profit is reached.

═══════════════════════════════════════════════════
CATEGORY 4: TREND DETECTION
═══════════════════════════════════════════════════

── Trend Strength ──
• TREND_ADX_ENABLED (boolean): Blocks entries when market has no clear trend. Essential filter.
• TREND_ADX_THRESHOLD (number, 0-60): Entries blocked below this ADX value.

── Momentum ──
• TREND_RSI_ENABLED (boolean): Relative Strength Index. Detects overbought/oversold. Good for all markets.
• TREND_MACD_ENABLED (boolean): MACD crossover. Catches momentum shifts. Good for trending markets.

── Volatility ──
• TREND_BOLLINGER_ENABLED (boolean): Bollinger Band squeeze detection. Catches pre-breakout compression.

── Direction Detection ──
• TREND_SUPERTREND_ENABLED (boolean): Always gives clear UP/DOWN signal. Can conflict with EMA Ribbon in choppy markets — avoid enabling both unless the profile trades strongly trending assets.
• TREND_EMA_RIBBON_ENABLED (boolean): 8/21/55 EMA ribbon for structural trend alignment. Best all-rounder.
• TREND_ICHIMOKU_ENABLED (boolean): Full trend picture via cloud. Needs 52+ candles. Best for crypto.
• TREND_PARABOLIC_SAR_ENABLED (boolean): Dots that flip on trend reversal. Good for catching reversals.
• TREND_HULL_MA_ENABLED (boolean): Fast moving average with minimal lag. Good for scalping.

── Volume ──
• TREND_VWAP_ENABLED (boolean): Volume-weighted average price. Only useful where real volume data exists (crypto, stocks). NOT useful for forex (tick volume only).

═══════════════════════════════════════════════════

RULES:
1. Pick EXACTLY ONE Performance Foundation (set it to true, all others false).
2. Do NOT enable STABILITY mode and aggressive multipliers together.
3. For Trend Detection, enable 3-5 indicators max — too many creates indecision.
4. VWAP is useless for forex-only profiles.
5. Opening Sentry is irrelevant for 24/7 crypto-only profiles.
6. Gamma Squeeze multiplier conflicts with standard trailing stop logic.
7. CONDUCTOR STRATEGY OVERRIDE — MANDATORY: If you pick \"conductor\" for ANY asset class, you MUST use these EXACT settings. The Conductor is a self-contained strategy with its own internal pyramiding, de-risk, and exit logic. External settings that conflict with it (like fixed R:R or low pyramid caps) will BREAK the strategy. These values were tuned through extensive backtesting and are NON-NEGOTIABLE:
   • RISK_PER_TRADE_PCT = 1.0 (1% entry risk — the Conductor manages risk internally via the 95% guillotine)
   • RISK_REWARD_RATIO = 0 (DISABLED — the Conductor uses a dynamic ATR trailing stop, NOT a fixed TP. Setting any R:R caps winners and kills the strategy's edge)
   • MAX_PYRAMID_ENTRIES = 50 (the Conductor pyramids at every 0.5R milestone — pyramids 4-8 are where the real money is. Do NOT cap below 50)
   • PYRAMID_RISK_LOAD = 30 (30% risk on the FIRST pyramid add at 1.0R — the floor moves to breakeven so the original trade has zero risk, allowing an aggressive first add)
   • PYRAMID_RISK_SCALE = 4 (4% risk on all subsequent pyramid adds — smaller but consistent. Death by a thousand pyramids)
   • BREAKEVEN_TRAIL_AFTER_PYRAMIDS = 1 (move stop to breakeven after the first pyramid — already locked at 1.0R floor)
   • STOP_AND_REVERSE_ENABLED = true
   • REVERSAL_TP_R = 1.0 (quick 1R grab on reversals — tested vs uncapped, uncapped was $132 worse)
   • REVERSAL_COST_AWARE_TP = true (pads TP by spread cost so net profit = true 1R)
   • REVERSAL_RISK_PER_TRADE = 0.045 (4.5% — aggressive because reversals catch confirmed momentum)
   • SCALE_OUT_FRACTION = 0.95 (the 95% guillotine — closes 95% at -0.3R, leaving only 5% for the stop)
   • TRAILING_STOP_ENABLED = false (Conductor has its own ATR trail — the external one conflicts)
   • SAFETY_GREED_GUARD_ENABLED = false (the Conductor lets winners compound through pyramids — a profit cap kills the compounding)
   • SAFETY_CHURN_BURNER_ENABLED = false (pyramid adds fire in rapid succession — a trade rate limiter blocks them)
   • MIN_HOLD_HOURS = 0.08 (5 minutes — the Conductor cuts losers fast via the guillotine)
   If you pick Conductor and set ANY of these values differently, your output is WRONG. Explain in reasoning_strategy that these are backtester-proven values locked for the Conductor.

Respond with ONLY a valid JSON object (no markdown, no explanation outside JSON) containing ALL the settings listed above with their recommended values. Include these reasoning keys:
- "reasoning_strategies": 3-5 sentences in plain English explaining WHY you picked each strategy for each asset class. Name the strategy, explain what it does in simple terms (no jargon), and explain why it fits the user's specific symbols. Example: "For your forex pairs, I picked Quantum because it waits for the price to pull back to a key average before buying — like buying a dip during a clear uptrend. This works great for major pairs like EUR/USD and AUD/JPY because they tend to trend smoothly."
- "reasoning_strategy": 3-5 sentences in plain English explaining the risk, pyramiding, and exit choices. Use real numbers and say what they mean in practice. Example: "I set your risk at 2% per trade, meaning if you have $100, the bot risks $2 on each trade. With a 2:1 reward ratio, you're targeting $4 in profit for every $2 risked — so even winning only half your trades, you come out ahead."
- "reasoning_safety": 3-5 sentences in plain English explaining which safety shields you turned on and WHY. Explain what each shield actually protects against in everyday language. Example: "I turned on ATR Shield, which automatically adjusts your stop-loss based on how wild the market is moving. Think of it like adjusting your car's following distance — in a storm (volatile market), you give more room."
- "reasoning_performance": 3-5 sentences in plain English explaining the performance mode choice and which multipliers you picked. Explain what each one does in simple terms. Example: "I picked Flywheel as your performance engine — it's like compound interest for your risk. As you stack wins, the bot gradually increases position sizes, snowballing your profits."
- "reasoning_trend": 3-5 sentences in plain English explaining which trend indicators you enabled and what each one actually checks. Example: "ADX tells the bot whether the market is trending or just wandering sideways. RSI checks if something is overbought or oversold — like checking if a stock has been bought up too much too fast."
- "reasoning_summary": 2-3 sentences giving a plain-English bottom line of the entire configuration. Summarize the philosophy — is this setup aggressive, balanced, or conservative? What's the overall approach?`;

            // 5. Call the AI — either user's own key or GhostSpotter relay
            const https = require('https');
            const http = require('http');
            const crypto = require('crypto');

            const GHOSTSPOTTER_RELAY_URL = 'https://ghostspotter.com/backend/api/tradebot/optimize';
            const GHOSTSPOTTER_TRADEBOT_KEY = 'af048332b5805de7024726eaa25af42e4cdb6c2c983dd7903653f5989c14d27f';

            let aiResponse;

            if (apiKey) {
                // ── User has their own AI key → direct OpenAI-compatible call ──
                console.log('[MAIN] Using user AI key for optimization');
                const url = new URL(baseUrl + '/chat/completions');
                const isSecure = url.protocol === 'https:';
                const requestModule = isSecure ? https : http;

                const requestBody = JSON.stringify({
                    model: model,
                    messages: [
                        { role: 'system', content: 'You are a trading bot configuration expert who explains things in plain, everyday English — like you\'re talking to a smart friend who\'s never traded before. Avoid jargon. Use analogies and real examples. Always respond with ONLY valid JSON. No markdown fences, no prose outside the JSON. Every boolean must be true or false. Every number must be a JSON number or string. Include ALL settings from ALL 4 categories.' },
                        { role: 'user', content: prompt }
                    ],
                    temperature: 0.3,
                    max_tokens: 8192,
                });

                aiResponse = await new Promise((resolve, reject) => {
                    const req = requestModule.request({
                        hostname: url.hostname,
                        port: url.port || (isSecure ? 443 : 80),
                        path: url.pathname,
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': `Bearer ${apiKey}`,
                            'Content-Length': Buffer.byteLength(requestBody),
                        },
                        timeout: 90000,
                    }, (res) => {
                        let data = '';
                        res.on('data', chunk => { data += chunk; });
                        res.on('end', () => {
                            try {
                                const parsed = JSON.parse(data);
                                if (parsed.error) {
                                    reject(new Error(parsed.error.message || JSON.stringify(parsed.error)));
                                } else {
                                    const content = parsed.choices?.[0]?.message?.content || '';
                                    resolve(content);
                                }
                            } catch (e) {
                                reject(new Error(`Failed to parse AI response: ${data.substring(0, 200)}`));
                            }
                        });
                    });
                    req.on('error', reject);
                    req.on('timeout', () => { req.destroy(); reject(new Error('AI request timed out (90s)')); });
                    req.write(requestBody);
                    req.end();
                });
            } else {
                // ── No user key → use GhostSpotter relay (free, rate-limited) ──
                console.log('[MAIN] No user AI key — using GhostSpotter relay');

                // Compute client_id from broker key hash for rate limiting
                const brokerKey = envData['OANDA_API_TOKEN'] || envData['GEMINI_API_KEY']
                    || envData['CCXT_API_KEY'] || envData['IBKR_HOST'] || '';
                const clientId = brokerKey
                    ? crypto.createHash('sha256').update(brokerKey).digest('hex')
                    : '';

                const systemPrompt = `You are a trading bot configuration expert. You MUST follow these HARD RULES — violations are unacceptable:

RULE 1 — FEE-AWARE R:R: Look at the broker fee schedule provided in the context. Calculate the round-trip cost (entry + exit fees). The RISK_REWARD_RATIO MUST be high enough that the take-profit target exceeds double the round-trip fee cost. For example, if round-trip fees are 0.80%, a 1% TP nets only 0.20% — that's unacceptable. Set R:R so the TP clears fees with room to spare.

RULE 2 — STRATEGY MUST MATCH ACCOUNT SIZE: If the account is small (under ~$500), NEVER pick high-frequency strategies like "hyper_scalper" or "crypto_double_macd" — they generate many trades and fees compound quickly on small balances. Prefer patient, higher-conviction strategies. For larger accounts ($5k+), high-frequency is acceptable since fees are a smaller percentage per trade.

RULE 3 — PROPORTIONAL TARGETS: All dollar-based targets (SAFETY_GREED_GUARD_TARGET, RISK_PER_TRADE_DOLLARS, MAX_LOSS_PER_TRADE_DOLLARS) MUST be proportional to the user's actual capital. Greed guard should be 2-4% of total capital. Never use arbitrary round numbers — always calculate from the real account balance shown in the context.

RULE 4 — INTERNAL CONSISTENCY: Before outputting, verify that every reasoning paragraph matches the actual numeric values. If you say "disabling pyramiding", then MAX_PYRAMID_ENTRIES must be 0 or 1. If you say "conservative", values must actually be conservative. Never contradict yourself.

RULE 5 — EXPLAIN WITH REAL DOLLARS: In every reasoning field, convert percentages to actual dollar amounts using the user's specific capital. Say "risking $X per trade" alongside the percentage so users understand their real exposure.

RULE 6 — RISK SCALES WITH CAPITAL: Smaller accounts need tighter risk per trade (1-2%) because a few bad trades can wipe significant portions. Larger accounts can afford 2-4%. Scale recommendations to the user's actual balance, not a generic default.

RULE 7 — FOREX vs CRYPTO AWARENESS: If OANDA is the forex broker, note that spread costs are the hidden fee — wider stops absorb spreads better. If a crypto exchange has explicit taker fees, factor those into R:R. VWAP is irrelevant for forex-only profiles. Opening Sentry is irrelevant for 24/7 crypto-only profiles.

RULE 8 — PERFORMANCE FOUNDATION IS MANDATORY: If total capital is under $500, you MUST select PERFORMANCE_MODE_SMOOTH. This is non-negotiable — any other choice for accounts under $500 will be considered undeliverable. For accounts over $500, choose the foundation that best fits the user's situation from the available options.

RULE 9 — DON'T USE ARBITRARY ROUND NUMBERS: Do NOT pick convenient round numbers like $10, $20, $50 for dollar-denominated targets. Always calculate the target as a percentage of the user's actual capital first, then convert to dollars. Show your math in the reasoning.

Respond in plain English a smart friend would understand. No jargon. Use analogies. Respond with ONLY valid JSON — no markdown fences, no text outside JSON. Every boolean must be true/false. Every number must be a number. Include ALL settings from ALL 4 categories.`;
                let fullPrompt = systemPrompt + '\n\n' + prompt;
                // Remove PERFORMANCE_MODE_NONE from available options — force the AI to pick a real foundation
                fullPrompt = fullPrompt.replace('• PERFORMANCE_MODE_NONE (boolean): Standard fixed % risk per trade. The baseline.\n', '');

                const relayUrl = new URL(GHOSTSPOTTER_RELAY_URL);
                const relayBody = JSON.stringify({ prompt: fullPrompt, client_id: clientId });

                aiResponse = await new Promise((resolve, reject) => {
                    const req = https.request({
                        hostname: relayUrl.hostname,
                        port: 443,
                        path: relayUrl.pathname,
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'x-api-key': GHOSTSPOTTER_TRADEBOT_KEY,
                            'Content-Length': Buffer.byteLength(relayBody),
                        },
                        timeout: 120000, // Gemini may take longer
                    }, (res) => {
                        let data = '';
                        res.on('data', chunk => { data += chunk; });
                        res.on('end', () => {
                            try {
                                const parsed = JSON.parse(data);
                                if (!parsed.success) {
                                    reject(new Error(parsed.error || 'GhostSpotter relay returned an error'));
                                } else {
                                    // Relay returns { success: true, result: { ...JSON... } }
                                    // Gemini structured output — result IS the JSON, stringify for consistent downstream parsing
                                    resolve(JSON.stringify(parsed.result));
                                }
                            } catch (e) {
                                reject(new Error(`Failed to parse relay response: ${data.substring(0, 200)}`));
                            }
                        });
                    });
                    req.on('error', reject);
                    req.on('timeout', () => { req.destroy(); reject(new Error('AI request timed out (120s). Try again.')); });
                    req.write(relayBody);
                    req.end();
                });
            }

            // 6. Parse the AI response — extract JSON from possible markdown wrapping
            let recommendations;
            try {
                let jsonStr = aiResponse.trim();
                // Strip markdown code fences if present
                if (jsonStr.startsWith('```')) {
                    jsonStr = jsonStr.replace(/^```(?:json)?\n?/, '').replace(/\n?```$/, '');
                }
                recommendations = JSON.parse(jsonStr);

                // Unwrap if Gemini nested everything under a profile name key
                // e.g., { "forex_crypto_hybrid": { ...actual settings... } }
                const topKeys = Object.keys(recommendations);
                if (topKeys.length === 1 && typeof recommendations[topKeys[0]] === 'object' && !Array.isArray(recommendations[topKeys[0]])) {
                    const inner = recommendations[topKeys[0]];
                    // Check if the inner object has category keys or reasoning — that's the real payload
                    const innerKeys = Object.keys(inner);
                    const looksLikePayload = innerKeys.some(k => k.startsWith('category_') || k.startsWith('reasoning_') || k === 'STRATEGY_FOREX' || k === 'STRATEGY_CRYPTO');
                    if (looksLikePayload) {
                        console.log(`[MAIN] Unwrapping AI response from nested key: "${topKeys[0]}"`);
                        recommendations = inner;
                    }
                }

                // Flatten category_N wrapper keys if present (Gemini structured output groups by category)
                // e.g., { category_1: { strategy_per_asset_class: {...}, ... }, category_2: {...} }
                const catKeys = Object.keys(recommendations).filter(k => k.startsWith('category_'));
                if (catKeys.length > 0) {
                    const flattened = {};
                    for (const key of Object.keys(recommendations)) {
                        if (key.startsWith('category_') && typeof recommendations[key] === 'object') {
                            // Merge all sub-objects within each category
                            for (const [subKey, subVal] of Object.entries(recommendations[key])) {
                                if (typeof subVal === 'object' && !Array.isArray(subVal)) {
                                    Object.assign(flattened, subVal);
                                } else {
                                    flattened[subKey] = subVal;
                                }
                            }
                        } else {
                            // Reasoning keys, etc. — keep as-is
                            flattened[key] = recommendations[key];
                        }
                    }
                    console.log('[MAIN] Flattened category_N wrappers from AI response');
                    recommendations = flattened;
                }
            } catch (e) {
                console.error('[MAIN] AI response parse error:', aiResponse);
                return { success: false, error: 'AI returned invalid JSON. Try again.' };
            }

            console.log('[MAIN] AI recommendations:', JSON.stringify(recommendations));

            // Post-processing: If using GhostSpotter relay and AI stubbornly picked NONE for
            // performance mode, override to SMOOTH — every account benefits from risk smoothing.
            // This only applies to the relay path (Gemini Flash-Lite tends to default to NONE).
            if (!apiKey && recommendations.PERFORMANCE_MODE_NONE === true) {
                console.log('[MAIN] Overriding PERFORMANCE_MODE_NONE → SMOOTH (relay fallback)');
                recommendations.PERFORMANCE_MODE_NONE = false;
                recommendations.PERFORMANCE_MODE_SMOOTH = true;
                // Update reasoning if present
                if (recommendations.reasoning_performance) {
                    recommendations.reasoning_performance += ' [Auto-adjusted: Smooth mode enabled as a baseline risk management foundation — it averages out position sizing to prevent wild swings, which benefits accounts of any size.]';
                }
            }

            return { success: true, recommendations };

        } catch (err) {
            console.error('[MAIN] AI Recommend error:', err.message);
            return { success: false, error: err.message };
        }
    });

    // =============================================
    // Payout AI Mentor
    // =============================================
    ipcMain.handle('generate-take-profit-advice', async (event, data) => {
        try {
            const { pnl, state, context } = data;

            // Re-read config for API keys (unified parsing)
            const envPath = path.join(USER_DATA_DIR, '.env');
            let envData = {};
            if (fs.existsSync(envPath)) {
                envData = require('dotenv').parse(fs.readFileSync(envPath, 'utf8'));
            }
            let configJson = {};
            if (fs.existsSync(CONFIG_PATH)) {
                try { configJson = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8')); } catch (e) { }
            }
            const aiConfig = configJson.ai || {};
            const merged = { ...envData, ...aiConfig };
            const get = (key) => merged[key] || merged[key.toLowerCase()] || merged[key.toUpperCase()] || '';
            
            const provider = get('provider') || get('TRADE_SCI_PROVIDER') || 'gemini';
            const apiKeyRaw = get('TRADE_SCI_API_KEY') || get('api_key') || get('CHATGPT_KEY') || get('OPENAI_API_KEY') || get('ANTHROPIC_API_KEY') || get('GEMINI_API_KEY') || '';
            const isPlaceholder = (v) => !v || /example\.com|your_.*_here|placeholder|changeme|xxx/i.test(v);
            const apiKey = isPlaceholder(apiKeyRaw) ? '' : apiKeyRaw;
            
            const defaultModels = { deepseek: 'deepseek-chat', openai: 'gpt-4o', claude: 'claude-3-5-sonnet-latest', gemini: 'gemini-2.5-flash', openrouter: 'google/gemini-2.0-flash-001', local: 'llama3' };
            const model = get('model') || get('TRADE_SCI_MODEL_NAME') || defaultModels[provider] || 'gpt-4o';
            
            let baseUrl = get('base_url') || get('TRADE_SCI_API_BASE_URL') || '';
            if (isPlaceholder(baseUrl)) baseUrl = '';
            if (!baseUrl) {
                const providerUrls = {
                    openai: 'https://api.openai.com/v1',
                    openrouter: 'https://openrouter.ai/api/v1',
                    deepseek: 'https://api.deepseek.com',
                    local: 'http://localhost:11434/v1',
                };
                baseUrl = providerUrls[provider] || 'https://api.openai.com/v1';
            }

            const systemPrompt = `You are a brutally honest, hilarious trading mentor for Tradebot SCI that speaks EXACTLY like the legendary comedian Patrice O'Neal. Your job is to provide exactly 2-3 sentences of psychological guidance regarding payouts (withdrawals of profit). 
The user is looking at their current analytics dashboard.
Current State: ${state.toUpperCase()}
Recent Profit/Loss: $${pnl.toFixed(2)}
Context: ${context}

RULES:
1. Speak exactly like Patrice O'Neal. Be brutally honest, slightly condescending but ultimately trying to help them not be stupid with their money. Use his cadence, pauses, and rhetorical questions. 
2. If State is WAITING: Tell them to sit their ass down and stop touching buttons while risk is floating. Call out their lack of patience.
3. If State is DRAWDOWN: Address the reality that they are under water. Tell them to back off and let the math work, instead of panicking like a rookie. 
4. If State is CASHOUT: Tell them to take the money and actually put it in their bank account before the market takes it back. Act like it's a miracle they actually made money and tell them to secure it.`;

            let aiResponse = '';

            if (apiKey || provider === 'local') {
                if (provider === 'gemini') {
                    const aiUrl = new URL(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`);
                    const geminiRes = await new Promise((resolve, reject) => {
                        const req = https.request({
                            hostname: aiUrl.hostname,
                            path: aiUrl.pathname + aiUrl.search,
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' }
                        }, (res) => {
                            let data = '';
                            res.on('data', chunk => { data += chunk; });
                            res.on('end', () => resolve(JSON.parse(data)));
                        });
                        req.on('error', reject);
                        req.write(JSON.stringify({
                            contents: [{ role: 'user', parts: [{ text: systemPrompt + '\\n\\nGenerate the Payout Mentor Advice.' }] }],
                            generationConfig: { temperature: 0.3 }
                        }));
                        req.end();
                    });
                    if (geminiRes.candidates && geminiRes.candidates[0].content.parts[0]) {
                        aiResponse = geminiRes.candidates[0].content.parts[0].text;
                    }
                } else if (provider === 'claude') {
                    const claudeRes = await new Promise((resolve, reject) => {
                        const req = https.request({
                            hostname: 'api.anthropic.com',
                            path: '/v1/messages',
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'x-api-key': apiKey,
                                'anthropic-version': '2023-06-01'
                            }
                        }, (res) => {
                            let data = '';
                            res.on('data', chunk => { data += chunk; });
                            res.on('end', () => resolve(JSON.parse(data)));
                        });
                        req.on('error', reject);
                        req.write(JSON.stringify({
                            model: model,
                            system: systemPrompt,
                            messages: [{ role: 'user', content: 'Generate the Payout Mentor Advice.' }],
                            max_tokens: 300,
                            temperature: 0.3
                        }));
                        req.end();
                    });
                    if (claudeRes.content && claudeRes.content[0]) {
                        aiResponse = claudeRes.content[0].text;
                    }
                } else {
                    // Universal OpenAI Compatible (OpenAI, DeepSeek, OpenRouter, Local, Custom)
                    const isSecure = baseUrl.startsWith('https:');
                    const requestModule = isSecure ? https : require('http');
                    const url = new URL(baseUrl + '/chat/completions');
                    const headers = { 'Content-Type': 'application/json' };
                    if (apiKey) Object.assign(headers, { 'Authorization': `Bearer ${apiKey}` });
                    // OpenRouter specific headers recommended
                    if (provider === 'openrouter') {
                        Object.assign(headers, { 'HTTP-Referer': 'https://tradebot-sci.com', 'X-Title': 'Tradebot SCI' });
                    }
                    
                    const oaiRes = await new Promise((resolve, reject) => {
                        const req = requestModule.request({
                            hostname: url.hostname,
                            port: url.port || (isSecure ? 443 : 80),
                            path: url.pathname + url.search,
                            method: 'POST',
                            headers: headers
                        }, (res) => {
                            let data = '';
                            res.on('data', chunk => { data += chunk; });
                            res.on('end', () => resolve(JSON.parse(data)));
                        });
                        req.on('error', reject);
                        req.write(JSON.stringify({
                            model: model,
                            messages: [
                                { role: 'system', content: systemPrompt },
                                { role: 'user', content: 'Generate the Payout Mentor Advice.' }
                            ],
                            temperature: 0.3
                        }));
                        req.end();
                    });
                    if (oaiRes.choices && oaiRes.choices[0]) {
                        aiResponse = oaiRes.choices[0].message.content;
                    }
                }
            } else {
                // Fallback: Pre-written responses to avoid GhostSpotter 1hr cooldown
                if (state === 'waiting') {
                    aiResponse = "Active risk is currently floating in the market. Withdrawing capital right now artificially spikes margin utilization. Sit on your hands until the current cycle resolves.";
                } else if (state === 'drawdown') {
                    aiResponse = "We are currently under water. Shield algorithms are active. Do not withdraw capital; allow the math to play out and recover the high water mark.";
                } else {
                    if (context && context.toLowerCase().includes('anomaly')) {
                        aiResponse = "Massive anomaly spike detected. Protect this windfall by transferring the recommended percentage to a real bank account before the market reverts to the mean.";
                    } else {
                        aiResponse = "Consistency is the engine of wealth. Secure the bag by transferring this steady profit to a real bank account, and allow the base to compound.";
                    }
                }
            }

            if (aiResponse) {
                // Clean up any markdown blocks if the AI messed up
                let cleanResponse = aiResponse.replace(/```/g, '').trim();
                return { success: true, advice: cleanResponse };
            } else {
                return { success: false, error: 'Empty response' };
            }

        } catch (err) {
            console.error('[MAIN] TP Mentor error:', err.message);
            return { success: false, error: err.message };
        }
    });

    // =============================================
    // Self-Update via Git Pull
    // =============================================
    const REPO_ROOT = path.join(__dirname, '../../../');

    ipcMain.handle('check-for-updates', async () => {
        return new Promise((resolve) => {
            exec('git fetch origin', { cwd: REPO_ROOT }, (fetchErr) => {
                if (fetchErr) {
                    console.error('[MAIN] git fetch failed:', fetchErr.message);
                    return resolve({ available: false, error: fetchErr.message });
                }

                // Detect the remote's default branch (main for public, master for private)
                exec('git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null || echo ""', { cwd: REPO_ROOT }, (brErr, brOut) => {
                    let branch = brOut.trim().replace('refs/remotes/origin/', '');
                    if (!branch) {
                        // Fallback: check if origin/main exists, else origin/master
                        exec('git rev-parse --verify origin/main 2>/dev/null && echo main || echo master', { cwd: REPO_ROOT }, (fbErr, fbOut) => {
                            branch = fbOut.trim().split('\n').pop();
                            compareWithBranch(branch, resolve);
                        });
                        return;
                    }
                    compareWithBranch(branch, resolve);
                });
            });
        });

        function compareWithBranch(branch, resolve) {
            exec(`git rev-list HEAD..origin/${branch} --count`, { cwd: REPO_ROOT }, (err, stdout) => {
                if (err) {
                    console.error('[MAIN] git rev-list failed:', err.message);
                    return resolve({ available: false, error: err.message });
                }

                const behind = parseInt(stdout.trim(), 10) || 0;
                if (behind === 0) {
                    return resolve({ available: false, behind: 0 });
                }

                exec(`git log HEAD..origin/${branch} --oneline --max-count=10`, { cwd: REPO_ROOT }, (logErr, logOut) => {
                    const summary = logErr ? '' : logOut.trim();
                    console.log(`[MAIN] Updates available: ${behind} commits behind origin/${branch}`);
                    resolve({ available: true, behind, summary, branch });
                });
            });
        }
    });

    ipcMain.handle('apply-update', async () => {
        console.log('[MAIN] Applying update...');

        // Detect the remote's default branch
        const branch = await new Promise((resolve) => {
            exec('git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null || echo ""', { cwd: REPO_ROOT }, (brErr, brOut) => {
                let b = brOut.trim().replace('refs/remotes/origin/', '');
                if (!b) {
                    exec('git rev-parse --verify origin/main 2>/dev/null && echo main || echo master', { cwd: REPO_ROOT }, (fbErr, fbOut) => {
                        resolve(fbOut.trim().split('\n').pop());
                    });
                    return;
                }
                resolve(b);
            });
        });
        console.log(`[MAIN] Detected branch for update: ${branch}`);

        // Step 1: Stop bot if running
        const killCmd = isWindows() ? 'taskkill /F /IM python.exe' : 'pkill -f "[r]un_dev_bot.py"';
        await new Promise((resolve) => {
            exec(killCmd, (err) => {
                if (err && err.code !== 1) console.warn('[MAIN] Kill during update:', err.message);
                resolve();
            });
        });

        // Step 2: Force-reset to remote branch (download-only, no merge conflicts)
        const pullResult = await new Promise((resolve) => {
            exec(`git fetch origin ${branch} && git reset --hard origin/${branch}`, { cwd: REPO_ROOT, timeout: 30000 }, (err, stdout, stderr) => {
                if (err) {
                    console.error('[MAIN] git reset failed:', err.message);
                    return resolve({ success: false, error: stderr || err.message });
                }
                console.log('[MAIN] git reset output:', stdout.trim());
                resolve({ success: true, output: stdout.trim() });
            });
        });

        if (!pullResult.success) {
            return { success: false, error: pullResult.error };
        }

        // Step 3: Reload the Electron window (picks up new HTML/JS/CSS)
        if (mainWindow && !mainWindow.isDestroyed()) {
            mainWindow.webContents.send('fromMain', {
                type: 'gui-notice',
                message: 'Update applied! Restarting bot...',
                color: 'blue'
            });

            // Small delay so the notice is visible
            await new Promise(r => setTimeout(r, 1500));
            mainWindow.reload();
        }

        // Step 4: Restart bot — kill again to be sure, wait for it to die, then start fresh
        const postKillCmd = isWindows() ? 'taskkill /F /IM python.exe' : 'pkill -f "[r]un_dev_bot.py"';
        await new Promise((resolve) => {
            exec(postKillCmd, () => resolve());
        });

        // Wait for the old process to fully exit
        await new Promise((resolve) => {
            let attempts = 0;
            const waitForDeath = setInterval(() => {
                exec('pgrep -f "[r]un_dev_bot.py"', (err, stdout) => {
                    const stillRunning = !!(stdout && stdout.trim());
                    attempts++;
                    if (!stillRunning || attempts >= 10) {
                        clearInterval(waitForDeath);
                        resolve();
                    }
                });
            }, 500);
        });

        console.log('[MAIN] Old bot process confirmed dead. Starting fresh...');
        // Small extra delay for cleanup
        await new Promise(r => setTimeout(r, 1000));
        ipcMain.emit('start-bot');

        return { success: true, output: pullResult.output };
    });
}

// Watch profiles for external changes
function startProfilesWatcher(win) {
    if (!fs.existsSync(PROFILES_PATH)) return;

    let watchTimeout;
    fs.watch(PROFILES_PATH, (event) => {
        if (event === 'change') {
            // Debounce to avoid multiple triggers during one write
            clearTimeout(watchTimeout);
            watchTimeout = setTimeout(async () => {
                const yaml = require('js-yaml');
                try {
                    const content = fs.readFileSync(PROFILES_PATH, 'utf8');
                    const json = yaml.load(content);
                    console.log("[MAIN] Profiles YAML changed externally, notifying UI...");
                    if (win) win.webContents.send('profiles-updated', json);
                    // Also notify settings window if open
                    if (settingsWindow) settingsWindow.webContents.send('profiles-updated', json);
                } catch (e) {
                    console.error("[MAIN] Error reading profiles on change:", e);
                }
            }, 100);
        }
    });
}

// Handle Log Tailing
function startLogWatcher(win) {
    const logPath = path.join(USER_DATA_DIR, 'logs', 'tradebot.log');
    if (!fs.existsSync(logPath)) return;

    // Start fresh — don't replay stale log history.
    // The GUI log panel should only show entries from the current session.
    win.webContents.send('fromMain', { type: 'log-clear' });

    let fileSize = fs.statSync(logPath).size;

    fs.watchFile(logPath, { interval: 500 }, (curr, prev) => {
        if (curr.mtime <= prev.mtime) return;
        const newFileSize = curr.size;
        const sizeDiff = newFileSize - fileSize;
        if (sizeDiff <= 0) {
            fileSize = newFileSize;
            return;
        }
        
        // Clamp massive throughput (e.g. Backtesting) to prevent V8 OOM
        let bytesToRead = sizeDiff;
        let position = fileSize;
        const MAX_BYTES = 100 * 1024; // 100 KB max UI tail chunk

        if (bytesToRead > MAX_BYTES) {
            bytesToRead = MAX_BYTES;
            position = newFileSize - MAX_BYTES;
        }

        const buffer = Buffer.alloc(bytesToRead);
        const fd = fs.openSync(logPath, 'r');
        fs.readSync(fd, buffer, 0, bytesToRead, position);
        fs.closeSync(fd);
        fileSize = newFileSize;
        
        let chunkStr = buffer.toString();
        if (sizeDiff > MAX_BYTES) {
            const firstNL = chunkStr.indexOf('\n');
            if (firstNL !== -1) chunkStr = chunkStr.substring(firstNL + 1);
            chunkStr = "\n[SYSTEM] ... massive log throughput omitted (tailing end only) ...\n" + chunkStr;
        }

        if (!win.isDestroyed()) {
            win.webContents.send('fromMain', { type: 'log-update', line: chunkStr });
        }
    });
}

function checkBotStatus(win, force = false) {
    exec('pgrep -f "[r]un_dev_bot.py"', (err, stdout) => {
        const isProcessRunning = !!(stdout && stdout.trim());
        
        // The Start/Stop (Panic) button strictly reflects the execution process
        // We decouple this from WebSocket health to prevent the button reverting to "Start" during network glitches
        if (force || isProcessRunning !== botRunning) {
            botRunning = isProcessRunning;
            console.log(`[MAIN] Bot Status changed: ${botRunning ? 'RUNNING' : 'STOPPED'} (Process: ${isProcessRunning})`);
            if (win && !win.isDestroyed()) {
                win.webContents.send('bot-status', { running: botRunning });
            }
        }
    });
}

function createSettingsWindow() {
    if (settingsWindow) {
        settingsWindow.focus();
        return;
    }

    settingsWindow = new BrowserWindow({
        width: 1615,
        height: 850,
        backgroundColor: '#020617',
        frame: false,
        resizable: true,
        icon: path.join(__dirname, 'assets/icon_robot.png'),
        webPreferences: {
            preload: path.join(__dirname, 'settings_preload.js'),
            nodeIntegration: false,
            contextIsolation: true,
        },
    });

    settingsWindow.loadFile('settings.html');

    // Enable native Copy/Paste context menu for settings window
    settingsWindow.webContents.on('context-menu', (event, params) => {
        const menu = new Menu();
        let hasItems = false;

        if (params.selectionText) {
            menu.append(new MenuItem({ label: 'Copy Text', role: 'copy' }));
            hasItems = true;
        }

        if (params.isEditable) {
            menu.append(new MenuItem({ label: 'Paste', role: 'paste' }));
            menu.append(new MenuItem({ label: 'Cut', role: 'cut' }));
            hasItems = true;
        }

        if (hasItems) {
            menu.popup(settingsWindow);
        }
    });

    settingsWindow.on('closed', () => { settingsWindow = null; });
}

function createWindow() {
    const statePath = path.join(USER_DATA_DIR, 'window-state.json');
    let state = { width: 1611, height: 1368 };
    try {
        if (fs.existsSync(statePath)) state = JSON.parse(fs.readFileSync(statePath, 'utf8'));
    } catch (e) { }

    const win = new BrowserWindow({
        x: state.x, y: state.y, width: state.width, height: state.height,
        resizable: true,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            nodeIntegration: false,
            contextIsolation: true,
        },
        backgroundColor: '#020617',
        frame: false,
        icon: path.join(__dirname, 'assets/icon_robot.png'),
    });

    win.loadFile('index.html');
    mainWindow = win;

    // Enable native Copy/Paste context menu
    win.webContents.on('context-menu', (event, params) => {
        const menu = new Menu();
        let hasItems = false;

        if (params.selectionText) {
            menu.append(new MenuItem({ label: 'Copy Text', role: 'copy' }));
            hasItems = true;
        }

        if (params.isEditable) {
            menu.append(new MenuItem({ label: 'Paste', role: 'paste' }));
            menu.append(new MenuItem({ label: 'Cut', role: 'cut' }));
            hasItems = true;
        }

        if (hasItems) {
            menu.popup(win);
        }
    });

    win.on('close', () => {
        try { fs.writeFileSync(statePath, JSON.stringify(win.getBounds())); } catch (e) { }
        if (settingsWindow) {
            settingsWindow.close();
            settingsWindow = null;
        }
    });

    win.webContents.once('did-finish-load', () => {
        startLogWatcher(win);
        startProfilesWatcher(win);
        setInterval(() => checkBotStatus(win), 2000);
    });

    ipcMain.on('start-bot', async () => {
        console.log('[MAIN] Start signal received.');
        const debugLogPath = path.join(USER_DATA_DIR, 'logs', 'gui_start_debug.log');
        const timestamp = new Date().toISOString();
        fs.appendFileSync(debugLogPath, `[${timestamp}] START SIGNAL RECEIVED\n`);

        // 1. Check if already running
        let isStarted = await new Promise(resolve => {
            exec('pgrep -f "[r]un_dev_bot.py"', (err, stdout) => {
                resolve(!!(stdout && stdout.trim()));
            });
        });

        if (isStarted) {
            console.log('[MAIN] Bot already running.');
            mainWindow.webContents.send('fromMain', { type: 'gui-notice', message: "Bot already running", color: 'teal' });
            return;
        }

        // 2. Clear old stdout log to get fresh errors
        const stdoutPath = path.join(USER_DATA_DIR, 'logs', 'bot_stdout.log');
        try { if (fs.existsSync(stdoutPath)) fs.truncateSync(stdoutPath); } catch (e) { }

        // 3. Command construction
        // The GUI user clicking "Start" IS their trading confirmation — inject it
        // so the daemon doesn't die waiting for interactive stdin confirmation.
        let spawnCmd = isWindows()
            ? `cd /d "${path.join(__dirname, '../../../')}" && ".venv/Scripts/python.exe" scripts/run_dev_bot.py --daemon`
            : `bash "${path.join(__dirname, '../../../scripts/tradebot.sh')}" --daemon`;

        console.log(`[MAIN] Executing: ${spawnCmd}`);
        fs.appendFileSync(debugLogPath, `[${timestamp}] EXEC: ${spawnCmd}\n`);

        const envOpts = { ...process.env, TRADING_CONFIRMATION: 'YES', PYTHONPATH: 'src' };
        exec(spawnCmd, { env: envOpts }, (error, stdout, stderr) => {
            if (error) {
                console.error(`[MAIN] Exec Error: ${error}`);
                fs.appendFileSync(debugLogPath, `[${timestamp}] EXEC ERROR: ${error.message}\n[${timestamp}] STDERR: ${stderr}\n`);
                mainWindow.webContents.send('fromMain', { type: 'gui-notice', message: "Start Command Failed", color: 'red' });
                return;
            }

            // 4. VERIFICATION LOOP
            // We wait and check up to 5 times over 10 seconds to allow the python process time to spawn
            let successes = 0;
            let attempts = 0;
            const checkInterval = setInterval(() => {
                attempts++;
                exec('pgrep -f "[r]un_dev_bot.py"', (err, stdout) => {
                    const running = !!(stdout && stdout.trim());
                    if (running) {
                        console.log('[MAIN] Verification: Bot is running.');
                        successes++;
                        if (successes >= 2) {
                            clearInterval(checkInterval);
                            mainWindow.webContents.send('fromMain', { type: 'gui-notice', message: "Bot Started Successfully", color: 'teal' });
                            checkBotStatus(mainWindow, true);
                        }
                    } else {
                        console.log(`[MAIN] Verification: Bot not found yet (Attempt ${attempts}/5).`);
                        if (attempts >= 5) {
                            console.error('[MAIN] Verification: Bot FAILED to start or stay alive.');
                            clearInterval(checkInterval);
    
                            // Read stdout + main log for error capture
                            let errorDetail = "Process died unexpectedly or took too long to spawn.";
                            const userDataDir = process.env.TRADEBOT_DATA_DIR
                                || (process.platform === 'darwin'
                                    ? path.join(require('os').homedir(), 'Library/Application Support/tradebot-sci')
                                    : path.join(process.env.XDG_CONFIG_HOME || path.join(require('os').homedir(), '.config'), 'tradebot-sci'));
                            const logPaths = [
                                stdoutPath,
                                path.join(userDataDir, 'logs', 'bot_stdout.log'),
                                path.join(userDataDir, 'logs', 'tradebot.log'),
                            ];
                            let combinedTail = '';
                            for (const lp of logPaths) {
                                try {
                                    if (fs.existsSync(lp)) {
                                        const content = fs.readFileSync(lp, 'utf8');
                                        const tailLines = content.split('\n').filter(l => l.trim()).slice(-5);
                                        const parsedTail = tailLines.map(line => {
                                            try {
                                                const obj = JSON.parse(line);
                                                if (obj.message) {
                                                    return obj.level ? `[${obj.level}] ${obj.message}` : obj.message;
                                                }
                                            } catch(e) {}
                                            return line;
                                        }).join('\n');
                                        if (parsedTail) combinedTail += parsedTail + '\n';
                                    }
                                } catch (e) { }
                            }
                            if (combinedTail.trim()) {
                                errorDetail = combinedTail.split('\n').filter(l => l.trim()).slice(-3).join('\n') || errorDetail;
                            }
    
                            // Detect "No broker configured" and show a popup dialog
                            if (combinedTail.includes('No broker configured')) {
                                const { dialog } = require('electron');
                                dialog.showMessageBox(mainWindow, {
                                    type: 'warning',
                                    title: 'No Broker Configured',
                                    message: 'The bot requires at least one broker with valid API credentials to start.',
                                    detail: 'Go to Settings → Broker Suite and configure one of the following:\n\n' +
                                        '• Apex / FTMO / FundedNext (Prop Firms)\n' +
                                        '• OANDA (Forex) — Account ID + API Key\n' +
                                        '• Gemini (Crypto) — API Key + Secret\n' +
                                        '• CCXT (Any Exchange) — API Key + Secret\n' +
                                        '• IBKR (Stocks/Futures) — TWS/Gateway connection\n\n' +
                                        'Need help? See Documentation → How to Use (Step 2: API Setup)',
                                    buttons: ['Open Broker Settings', 'Close'],
                                    defaultId: 0,
                                }).then(({ response }) => {
                                    if (response === 0) {
                                        // Navigate to settings and switch to Live Brokers tab
                                        mainWindow.webContents.send('fromMain', { type: 'navigate', target: 'settings', tab: 'brokers' });
                                    }
                                });
                            }
    
                            mainWindow.webContents.send('fromMain', {
                                type: 'gui-notice',
                                message: "Bot Startup Failed",
                                detail: errorDetail,
                                color: 'red'
                            });
                            checkBotStatus(mainWindow, true);
                        }
                    }
                });
            }, 2000);
        });
    });

    ipcMain.on('stop-bot', () => {
        console.log('[MAIN] Stopping bot...');
        const cmd = isWindows() ? 'taskkill /F /IM python.exe' : 'pkill -9 -f "[r]un_dev_bot.py"';

        try { require('child_process').execSync(cmd); } catch (e) {}
        setTimeout(() => checkBotStatus(mainWindow, true), 1000);
    });

    ipcMain.on('restart-bot', () => {
        console.log('[MAIN] Restarting bot...');
        const killCmd = isWindows() ? 'taskkill /F /IM python.exe' : 'pkill -f "[r]un_dev_bot.py"';

        exec(killCmd, () => {
            setTimeout(() => {
                // Re-trigger start logic
                ipcMain.emit('start-bot');

                // Poll for the bot to come back online, then notify the renderer
                let pollAttempts = 0;
                const pollInterval = setInterval(() => {
                    pollAttempts++;
                    exec('pgrep -f "[r]un_dev_bot.py"', (err, stdout) => {
                        if (stdout && stdout.trim()) {
                            clearInterval(pollInterval);
                            console.log('[MAIN] Bot confirmed running after restart.');
                            // Give the WS server a moment to bind
                            setTimeout(() => {
                                if (mainWindow && !mainWindow.isDestroyed()) {
                                    mainWindow.webContents.send('bot-restarted');
                                }
                            }, 2000);
                        } else if (pollAttempts >= 15) {
                            // Timeout after ~15s — notify anyway so the UI isn't stuck
                            clearInterval(pollInterval);
                            console.warn('[MAIN] Bot restart poll timed out.');
                            if (mainWindow && !mainWindow.isDestroyed()) {
                                mainWindow.webContents.send('bot-restarted');
                            }
                        }
                    });
                }, 1000);
            }, 2000);
        });
    });

    ipcMain.on('get-bot-status', () => { checkBotStatus(mainWindow, true); });



    ipcMain.on('minimize-window', (e) => {
        const win = BrowserWindow.fromWebContents(e.sender);
        if (win) win.minimize();
    });

    ipcMain.on('maximize-window', (e) => {
        const win = BrowserWindow.fromWebContents(e.sender);
        if (win) {
            if (win.isMaximized()) win.unmaximize();
            else win.maximize();
        }
    });

    ipcMain.on('close-window', (e) => {
        const win = BrowserWindow.fromWebContents(e.sender);
        if (win) win.close();
    });

    ipcMain.on('open-settings', () => createSettingsWindow());
    ipcMain.on('close-settings', () => { if (settingsWindow) settingsWindow.close(); });

    ipcMain.on('log-notice', (event, { message, color }) => {
        const timestamp = new Date().toISOString();
        const logMsg = `[GUI-NOTICE] [${timestamp}] ${message} (${color})\n`;
        const debugLogPath = path.join(USER_DATA_DIR, 'logs', 'gui_notices.log');
        try {
            fs.appendFileSync(debugLogPath, logMsg);
        } catch (e) {
            console.error("Failed to write gui notice:", e);
        }
        // Echo to all windows
        BrowserWindow.getAllWindows().forEach(win => {
            win.webContents.send('fromMain', { type: 'gui-notice', message, color, timestamp });
        });
    });
    ipcMain.handle('fetch-ai-models', async (event, provider, baseUrl, apiKey) => {
        return new Promise((resolve) => {
            const defaultM = {
                'gemini': ['gemini-2.5-pro', 'gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-2.0-flash-lite-preview-02-05', 'gemini-1.5-pro', 'gemini-1.5-flash'],
                'openai': ['o3-mini', 'o1', 'o1-mini', 'gpt-4.5-preview', 'gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo'],
                'deepseek': ['deepseek-chat', 'deepseek-reasoner'],
                'claude': ['claude-3-7-sonnet-latest', 'claude-3-5-sonnet-latest', 'claude-3-opus-latest', 'claude-3-haiku-20240307'],
                'local': ['llama3', 'mistral', 'qwen2.5', 'phi3']
            };

            const fallbacks = defaultM[provider] || [];

            if (!apiKey && provider !== 'local') return resolve({ success: true, models: fallbacks, notice: 'Showing defaults (No API key provided)' });

            if (provider === 'gemini') {
                const https = require('https');
                const urlObj = new URL(`https://generativelanguage.googleapis.com/v1beta/models?key=${apiKey}`);
                const req = https.get(urlObj.href, (res) => {
                    let data = '';
                    res.on('data', chunk => data += chunk);
                    res.on('end', () => {
                        try {
                            const parsed = JSON.parse(data);
                            if (parsed.models) {
                                resolve({ success: true, models: parsed.models.map(m => m.name.replace('models/', '')).filter(n => n.includes('gemini')) });
                            } else {
                                resolve({ success: true, models: fallbacks, notice: 'Showing defaults (API request failed)' });
                            }
                        } catch (e) { resolve({ success: true, models: fallbacks, notice: 'Parse error' }); }
                    });
                });
                req.on('error', (e) => resolve({ success: true, models: fallbacks, notice: e.message }));
                return;
            }

            // OpenAI / DeepSeek / Local compatible /v1/models
            if (provider === 'claude') {
                return resolve({ success: true, models: fallbacks });
            }

            let endpoint = baseUrl;
            if (!endpoint) {
                if (provider === 'deepseek') endpoint = 'https://api.deepseek.com';
                else if (provider === 'openrouter') endpoint = 'https://openrouter.ai/api/v1';
                else if (provider === 'local') endpoint = 'http://localhost:11434/v1';
                else endpoint = 'https://api.openai.com/v1';
            }
            // Strip trailing slash if present
            endpoint = endpoint.replace(/\/$/, '');
            let requestModule = endpoint.startsWith('http://') ? require('http') : require('https');
            
            const urlObj = new URL(`${endpoint}/models`);
            const req = requestModule.get({
                hostname: urlObj.hostname,
                port: urlObj.port,
                path: urlObj.pathname,
                headers: { 'Authorization': `Bearer ${apiKey}` }
            }, (res) => {
                let data = '';
                res.on('data', chunk => data += chunk);
                res.on('end', () => {
                    try {
                        const parsed = JSON.parse(data);
                        if (parsed.data && Array.isArray(parsed.data)) {
                            let models = parsed.data.map(m => m.id);
                            resolve({ success: true, models: models.sort() });
                        } else {
                            resolve({ success: true, models: fallbacks, notice: 'Showing defaults (API request failed)' });
                        }
                    } catch (e) { resolve({ success: true, models: fallbacks, notice: 'Parse error' }); }
                });
            });
            req.on('error', (e) => resolve({ success: true, models: fallbacks, notice: e.message }));
        });
    });

}

app.whenReady().then(() => {
    setupIpcHandlers();
    createWindow();
    startProfilesWatcher(null); // Will be attached in createWindow
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
});
