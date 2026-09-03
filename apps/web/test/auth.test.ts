// @vitest-environment node
//
// Node, not the project's default jsdom. `authHeader()` branches on
// `typeof window`, and under jsdom a window always exists — so the *server*
// path, which is the one every server component takes, would never run. The
// browser path is exercised below by defining a window explicitly, which makes
// both runtimes visible in the test rather than one of them being whichever the
// environment happened to give.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/**
 * The token header, and the mode where there is no token.
 *
 * The unconfigured branch is the one that matters most here. It is what the 248
 * gate checks, the three Playwright flows and every local run exercise, so a
 * regression in it breaks the whole verification story rather than one feature.
 * It is also the branch that is easy to lose by accident: adding a `throw` for
 * "not signed in" would look like tightening security and would in fact make
 * the app unrunnable everywhere it is currently tested.
 *
 * `lib/auth.ts` is re-imported per test because `authConfigured()` reads
 * `process.env` and Next inlines those at build; a module-level capture would
 * make the second test see the first one's environment.
 */

const KEY = 'NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY'

async function freshAuth() {
  vi.resetModules()
  return import('@/lib/auth')
}

const original = process.env[KEY]

beforeEach(() => {
  delete process.env[KEY]
  delete (globalThis as { __codonlabServerToken?: unknown }).__codonlabServerToken
})

afterEach(() => {
  if (original === undefined) delete process.env[KEY]
  else process.env[KEY] = original
})

describe('when no identity provider is configured', () => {
  it('reports itself unconfigured', async () => {
    const auth = await freshAuth()
    expect(auth.authConfigured()).toBe(false)
  })

  it('sends no Authorization header at all', async () => {
    const auth = await freshAuth()
    expect(await auth.authHeader()).toEqual({})
  })

  it('does not consult the server getter, even if one is registered', async () => {
    // Guards the order of the checks. If `authHeader` looked for a token before
    // checking whether auth is configured, a stale registration would start
    // attaching headers on a local instance.
    const auth = await freshAuth()
    const getter = vi.fn(async () => 'a-token')
    auth.registerServerToken(getter)

    expect(await auth.authHeader()).toEqual({})
    expect(getter).not.toHaveBeenCalled()
  })
})

describe('when a provider is configured', () => {
  beforeEach(() => {
    process.env[KEY] = 'pk_test_example'
  })

  it('reports itself configured', async () => {
    const auth = await freshAuth()
    expect(auth.authConfigured()).toBe(true)
  })

  it('attaches the registered server token as a bearer header', async () => {
    const auth = await freshAuth()
    auth.registerServerToken(async () => 'header.payload.signature')

    expect(await auth.authHeader()).toEqual({
      Authorization: 'Bearer header.payload.signature',
    })
  })

  it('sends nothing when there is no session rather than a header with no token', async () => {
    // `Bearer null` is a token as far as the API is concerned: it would be
    // parsed, fail verification, and produce a 401 that reads like a broken
    // session instead of an anonymous request.
    const auth = await freshAuth()
    auth.registerServerToken(async () => null)

    expect(await auth.authHeader()).toEqual({})
  })

  it('sends nothing when the token cannot be minted, rather than throwing', async () => {
    // A session refresh that fails must not take the screen down with it. The
    // request goes anyway and the API decides — which also means a server that
    // is merely down does not get reported as "not signed in".
    const auth = await freshAuth()
    auth.registerServerToken(async () => {
      throw new Error('network')
    })

    expect(await auth.authHeader()).toEqual({})
  })

  it('sends nothing when no server getter was ever registered', async () => {
    // The registration happens as a side effect of the root layout importing
    // `lib/auth-server`. If that import is ever dropped, this is the behaviour:
    // anonymous requests and 401s from the API, not a crash.
    const auth = await freshAuth()
    expect(await auth.authHeader()).toEqual({})
  })
})

describe('in the browser', () => {
  beforeEach(() => {
    process.env[KEY] = 'pk_test_example'
  })

  afterEach(() => {
    delete (globalThis as { window?: unknown }).window
  })

  /** Enough of Clerk's browser global to reach the token. */
  function mountClerk(getToken: () => Promise<string | null>) {
    ;(globalThis as { window?: unknown }).window = {
      Clerk: { session: { getToken } },
    }
  }

  it('reads the token from Clerk rather than the server getter', async () => {
    const auth = await freshAuth()
    const server = vi.fn(async () => 'server-token')
    auth.registerServerToken(server)
    mountClerk(async () => 'browser-token')

    expect(await auth.authHeader()).toEqual({ Authorization: 'Bearer browser-token' })
    expect(server, 'the server getter must not run in a browser').not.toHaveBeenCalled()
  })

  it('sends nothing before the session has resolved', async () => {
    // `<ClerkProvider>` mounts before the session exists. Attaching a header
    // during that window would send `Bearer undefined` on the first request of
    // every page load.
    const auth = await freshAuth()
    ;(globalThis as { window?: unknown }).window = { Clerk: {} }

    expect(await auth.authHeader()).toEqual({})
  })

  it('sends nothing when Clerk has not loaded at all', async () => {
    const auth = await freshAuth()
    ;(globalThis as { window?: unknown }).window = {}

    expect(await auth.authHeader()).toEqual({})
  })
})
