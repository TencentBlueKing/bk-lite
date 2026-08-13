import { defineConfig, devices } from '@playwright/test';

const port = process.env.PLAYWRIGHT_TOUR_PORT || '4173';
const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: './browser-tests/opspilot-tour',
  testMatch: 'tour-position.spec.ts',
  fullyParallel: false,
  retries: 0,
  reporter: 'line',
  use: {
    ...devices['Desktop Chrome'],
    baseURL,
  },
  webServer: {
    command: `pnpm exec vite browser-tests/opspilot-tour/fixture --host 127.0.0.1 --port ${port}`,
    url: baseURL,
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
