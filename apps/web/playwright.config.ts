import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright, for the two claims that only a real browser can settle.
 *
 * `BRIEF.md` §9 asks for smoke flows in this phase. Everything else in this
 * repository is tested either hermetically (pytest, vitest) or over HTTP
 * (`scripts/verify_gates.py`). Both of those stop short of the same thing: a
 * *user*, with trusted input events, a real event loop and a real router.
 *
 * `HANDOFF.md` §7 records the owner's correction on exactly this point —
 * "verify that literally, count the clicks, rather than asserting the drawer
 * exists". The jsdom version of the two-clicks gate counts synthetic clicks;
 * this one counts `event.isTrusted` ones.
 *
 * **It does not start the stack.** The API, the worker and the database have to
 * be up, because these flows execute a real design run against a real Postgres.
 * `webServer` is deliberately not configured: a smoke flow that silently spins
 * up its own dependencies is a smoke flow that can pass while the thing the
 * user runs is broken.
 */
export default defineConfig({
  testDir: './e2e',
  // A run is enqueued and executed by a separate worker container; the flows
  // wait on real work, not on a mock.
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:3000',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
