// @vitest-environment node
//
// Node rather than the project's default jsdom, because `apiConfigured()`
// branches on `typeof window` to decide whether `API_INTERNAL_URL` counts.
// Under jsdom a window always exists, so the server branch would never run.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/**
 * What a stranger is told when the API is not there.
 *
 * This exists because of a real defect on the deployed site: every screen that
 * needed data told the visitor to "start the stack with `docker compose up`".
 * That is correct advice for the one developer and useless to everybody else —
 * they are told to run a tool they do not have, for a machine that is not
 * theirs, and the reasonable conclusion is that the product is broken.
 *
 * The branch that matters most is the deployed one, and it is invisible during
 * development: running the app locally exercises only the development branch,
 * so without these tests the deployed wording is written once and never seen
 * again by anyone who could correct it.
 */

const ENV = { ...process.env }

async function fresh() {
  vi.resetModules()
  return import('@/lib/remedies')
}

beforeEach(() => {
  delete process.env.NEXT_PUBLIC_API_URL
  delete process.env.API_INTERNAL_URL
})

afterEach(() => {
  process.env = { ...ENV }
})

/** Anything a reader would have to install, run, or have a shell for. */
const DEVELOPER_TOOLING = /docker|compose|npm|pnpm|localhost|terminal|shell/i

describe('a developer running the stack locally', () => {
  beforeEach(() => {
    vi.stubEnv('NODE_ENV', 'development')
  })

  it('is told to start the stack, which is the thing that would fix it', async () => {
    const { unreachableRemedy } = await fresh()
    expect(unreachableRemedy()).toContain('docker compose up')
  })

  it('is told to reload or retry, matching what they were doing', async () => {
    const { unreachableRemedy } = await fresh()
    expect(unreachableRemedy('reload')).toContain('reload')
    expect(unreachableRemedy('retry')).toContain('retry')
  })

  it('is pointed at the api logs when the server answers with an error', async () => {
    const { serverErrorRemedy } = await fresh()
    expect(serverErrorRemedy()).toContain('docker compose logs api')
  })
})

describe('a deployment with no API address configured', () => {
  // The exact situation on codon-lab.vercel.app: the build went out without
  // NEXT_PUBLIC_API_URL, so `baseUrl()` falls back to localhost and the server
  // asks itself for port 8000.
  beforeEach(() => {
    vi.stubEnv('NODE_ENV', 'production')
  })

  it('says the address is missing, rather than blaming the reader', async () => {
    const { unreachableRemedy } = await fresh()
    const remedy = unreachableRemedy()

    expect(remedy).toContain('no API address configured')
    expect(remedy).toContain('NEXT_PUBLIC_API_URL')
  })

  it('never tells a visitor to run docker', async () => {
    const { unreachableRemedy, serverErrorRemedy, versionSkewRemedy, noWorkerRemedy }
      = await fresh()

    for (const remedy of [
      unreachableRemedy('reload'),
      unreachableRemedy('retry'),
      serverErrorRemedy(),
      versionSkewRemedy(),
      noWorkerRemedy(),
    ]) {
      expect(remedy, `leaks developer tooling: ${remedy}`).not.toMatch(DEVELOPER_TOOLING)
    }
  })
})

describe('a deployment whose API is configured but not answering', () => {
  beforeEach(() => {
    vi.stubEnv('NODE_ENV', 'production')
    vi.stubEnv('NEXT_PUBLIC_API_URL', 'https://codonlab-api.example.com')
  })

  it('says the service is down rather than that it is misconfigured', async () => {
    const { unreachableRemedy } = await fresh()
    const remedy = unreachableRemedy()

    // The distinction is the point. "Set NEXT_PUBLIC_API_URL" would send
    // somebody to change a setting that is already correct.
    expect(remedy).not.toContain('NEXT_PUBLIC_API_URL')
    expect(remedy).toMatch(/starting up|down/i)
  })

  it('still tells the reader what to do', async () => {
    const { unreachableRemedy } = await fresh()
    expect(unreachableRemedy('reload')).toContain('reload')
  })

  it('counts a server-side API_INTERNAL_URL as configured', async () => {
    // Docker Compose sets only API_INTERNAL_URL for server components. A
    // deployment doing the same must not be told its address is missing.
    vi.stubEnv('NEXT_PUBLIC_API_URL', '')
    vi.stubEnv('API_INTERNAL_URL', 'http://api:8000')

    const { unreachableRemedy } = await fresh()
    expect(unreachableRemedy()).not.toContain('no API address configured')
  })
})

describe('every remedy, in every environment', () => {
  it('says something actionable rather than only naming the fault', async () => {
    // The house rule: an error that does not say what fixes it is useless to
    // somebody who is busy. Asserted across both environments at once so a new
    // branch cannot be added without one.
    for (const environment of ['development', 'production']) {
      vi.stubEnv('NODE_ENV', environment)
      const { unreachableRemedy, serverErrorRemedy, versionSkewRemedy, noWorkerRemedy }
        = await fresh()

      for (const remedy of [
        unreachableRemedy(),
        serverErrorRemedy(),
        versionSkewRemedy(),
        noWorkerRemedy(),
      ]) {
        expect(remedy.length, `too terse in ${environment}: ${remedy}`).toBeGreaterThan(30)
        expect(remedy.trim().endsWith('.'), `unfinished sentence: ${remedy}`).toBe(true)
      }
    }
  })
})
