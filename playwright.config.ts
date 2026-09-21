import { defineConfig, devices } from '@playwright/test';

/**
 * E2E config for the EasyBillBro Django app. Targets the local dev server
 * (manage.py runserver on :8000) -- `reuseExistingServer: true` means it
 * will NOT try to start a second server if one's already running (the
 * common case during development), but CI environments with nothing
 * listening on :8000 yet will get one started automatically.
 */
export default defineConfig({
  testDir: './e2e/tests',
  fullyParallel: false, // tests share real DB state (tenant "leo") -- serialize to avoid cross-test interference
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [['html', { open: 'never' }], ['list']],
  timeout: 30_000,
  expect: { timeout: 8_000 },

  use: {
    baseURL: 'http://localhost:8000',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  webServer: {
    command: '.venv/Scripts/python.exe manage.py runserver 0.0.0.0:8000',
    url: 'http://localhost:8000/',
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
