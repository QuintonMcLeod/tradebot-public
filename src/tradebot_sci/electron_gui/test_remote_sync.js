const puppeteer = require('puppeteer-core');
const path = require('path');

async function run() {
    console.log('[TEST] Starting Tradebot GUI in Remote Sync Mode with Puppeteer...');
    
    const electronPath = path.resolve(__dirname, 'node_modules', '.bin', 'electron');
    const appPath = path.resolve(__dirname, 'main.js');
    
    const browser = await puppeteer.launch({
        executablePath: electronPath,
        args: [appPath, '--remote-debugging-port=9222'],
        headless: false,
        defaultViewport: null,
        env: {
            ...process.env,
            GUI_WS_URL: 'ws://192.168.133.205:8080/ws'
        }
    });
    
    console.log('[TEST] Electron launched. Hooking main window...');
    const pages = await browser.pages();
    let page = pages[0];
    
    if (!page.url().includes('index.html')) {
        await new Promise(r => setTimeout(r, 2000));
        const allPages = await browser.pages();
        page = allPages.find(p => p.url().includes('index.html')) || allPages[0];
    }
    
    console.log('[TEST] Main window hooked. Waiting for #status-profile element...');
    await page.waitForSelector('#status-profile', { visible: true });
    
    console.log('[TEST] Monitoring #status-profile for active profile synchronization...');
    let activeProfile = '';
    let success = false;
    
    for (let i = 0; i < 20; i++) {
        activeProfile = await page.$eval('#status-profile', el => el.innerText.trim());
        console.log(`[TEST] Check ${i+1}/20: Current status-profile text = "${activeProfile}"`);
        
        if (activeProfile.includes('FOREX_CONTINUOUS')) {
            console.log('[TEST] SUCCESS: Active Profile successfully synchronized from remote Kubernetes backend!');
            success = true;
            break;
        }
        await new Promise(r => setTimeout(r, 1000));
    }
    
    if (!success) {
        console.log('[TEST] FAILED: Active Profile did not synchronize within 20 seconds.');
    }
    
    console.log('[TEST] Closing app...');
    await browser.close();
    process.exit(success ? 0 : 1);
}

run().catch(err => {
    console.error('[TEST] Execution error:', err);
    process.exit(1);
});
