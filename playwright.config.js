const { defineConfig } = require('@playwright/test');
const { existsSync } = require('node:fs');
const baseURL = process.env.STUDIO_TEST_URL || 'http://127.0.0.1:8765';
const executablePath = process.env.PLAYWRIGHT_CHROMIUM_PATH || (existsSync('/usr/bin/chromium') ? '/usr/bin/chromium' : undefined);
const python = process.env.STUDIO_TEST_PYTHON || (existsSync('.venv/bin/python') ? '.venv/bin/python' : 'python3');
module.exports = defineConfig({
  testDir: './tests', testMatch: 'browser.spec.js', workers: 1,
  use: { baseURL, headless: true, viewport: { width: 1440, height: 1100 },
    screenshot: 'only-on-failure', trace: 'retain-on-failure',
    launchOptions: { executablePath } },
  webServer: process.env.STUDIO_TEST_URL ? undefined : {
    command: `${python} tests/browser_server.py`, url: `${baseURL}/api/health`,
    timeout: 30000, reuseExistingServer: false,
    gracefulShutdown: { signal: 'SIGTERM', timeout: 15000 },
  },
  reporter: 'list', timeout: 90000,
});
