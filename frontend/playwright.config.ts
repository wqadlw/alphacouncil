import { defineConfig } from '@playwright/test'

/**
 * Browser-level tests (spec 010) — the UI layer of the red-line enforcement
 * (constitution 12.1): assertions about *rendered* pages that no unit test
 * can make.
 *
 * Two environment facts shape this config:
 *
 * - The app is tested as its **built output** (`vite preview`), not a dev
 *   server — the build is part of the contract.
 * - Locally there is no Playwright browser download (the registry download is
 *   slow and gated on this network), so tests run on the system **Edge**
 *   (`channel: 'msedge'`). CI installs chromium instead.
 */
const isCI = !!process.env.CI

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  retries: isCI ? 1 : 0,
  reporter: isCI ? [['github'], ['list']] : [['list']],
  use: {
    baseURL: 'http://127.0.0.1:4173',
    trace: 'retain-on-failure',
    ...(isCI ? {} : { channel: 'msedge' }),
  },
  webServer: {
    command: 'npm run build && npm run preview -- --port 4173 --strictPort',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: !isCI,
    timeout: 120_000,
  },
})
