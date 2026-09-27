import { configDefaults, defineConfig } from 'vitest/config'

// Separate from `vite.config.ts` so the unit-test runner never discovers the
// Playwright suites in `e2e/` — they use `@playwright/test`'s own `test`,
// which vitest would reject (and did: the e2e specs appeared in `npm test`
// the day Playwright landed). Excluded explicitly rather than renamed, so
// both runners keep their conventional `*.spec.ts` naming.
export default defineConfig({
  test: {
    exclude: [...configDefaults.exclude, 'e2e/**'],
  },
})
