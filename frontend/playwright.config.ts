import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 60_000,
  expect: {
    timeout: 5_000,
  },
  fullyParallel: true,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list']],
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:3100',
    headless: true,
    trace: 'on-first-retry',
    video: 'retain-on-failure',
  },
  webServer: {
    command: 'PORT=3100 npm run dev -- --hostname 127.0.0.1 --port 3100',
    url: 'http://127.0.0.1:3100',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  workers: process.env.CI ? 2 : undefined,
});
