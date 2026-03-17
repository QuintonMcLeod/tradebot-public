const puppeteer = require('puppeteer-core');
const cp = require('child_process');
const path = require('path');

async function run() {
    console.log('[TEST] Starting Tradebot GUI with Puppeteer...');
    
    // The path to the Electron executable inside node_modules
    const electronPath = path.resolve(__dirname, 'node_modules', '.bin', 'electron');
    const appPath = path.resolve(__dirname, 'main.js');
    
    // Launch Electron via Puppeteer
    const browser = await puppeteer.launch({
        executablePath: electronPath,
        args: [appPath, '--remote-debugging-port=9222'],
        headless: false,
        defaultViewport: null
    });
    
    // Wait for the app to start and get the first page (window)
    const pages = await browser.pages();
    let page = pages[0];
    
    // If the first page is somehow not the main window, we can wait a bit
    if (!page.url().includes('index.html')) {
        await new Promise(r => setTimeout(r, 2000));
        const allPages = await browser.pages();
        page = allPages.find(p => p.url().includes('index.html')) || allPages[0];
    }
    
    console.log('[TEST] Window hooked. Waiting for load...');
    await page.waitForSelector('#nav-profiles');
    
    // Click on Profiles Tab
    console.log('[TEST] Clicking Profiles Nav Tab...');
    await page.click('#nav-profiles');
    
    // Give it a second to render
    await new Promise(r => setTimeout(r, 1000));
    
    console.log('[TEST] Verifying default profile was auto-created...');
    const profiles = await page.$$eval('#profile-list .profile-item', items => items.map(el => el.textContent.trim()));
    console.log('[TEST] Current Profiles in sidebar:', profiles.map(p => p.split('\\n')[0].trim()));
    
    if (profiles.some(p => p.includes('default'))) {
        console.log('[TEST] SUCCESS: Default profile found.');
    } else {
        console.log('[TEST] FAILED: Default profile not found.');
    }
    
    console.log('[TEST] Clicking New Profile button...');
    await page.click('#btn-new-profile');
    
    // Wait for the injected modal input
    await page.waitForSelector('#new-profile-input', { visible: true });
    console.log('[TEST] Modal opened successfully.');
    
    console.log('[TEST] Typing new profile name: crypto_test...');
    await page.type('#new-profile-input', 'crypto_test');
    
    console.log('[TEST] Clicking Create Profile in modal...');
    await page.click('#new-profile-create');
    
    // Wait a moment for it to render
    await new Promise(r => setTimeout(r, 1000));
    
    const newProfiles = await page.$$eval('#profile-list .profile-item', items => items.map(el => el.textContent.trim()));
    console.log('[TEST] New Profiles in sidebar:', newProfiles.map(p => p.split('\\n')[0].trim()));
    
    if (newProfiles.some(p => p.includes('crypto_test'))) {
        console.log('[TEST] SUCCESS: crypto_test profile created and rendered.');
    } else {
        console.log('[TEST] FAILED: crypto_test not in sidebar.');
    }
    
    console.log('[TEST] Closing app...');
    await browser.close();
}

run().catch(console.error);
