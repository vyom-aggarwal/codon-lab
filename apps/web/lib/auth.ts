/**
 * The access token, on both sides of the server/client boundary.
 *
 * `lib/api.ts` is imported by server components *and* by client components, so
 * there is no single place to read a session from — the two runtimes have
 * different ones, and only one of them may see Clerk's server SDK.
 *
 * **Why this is not just a dynamic import.** The obvious version of this file
 * called `await import('@clerk/nextjs/server')` inside a `typeof window`
 * branch. That fails, and the failure is a build error rather than a subtle
 * one: bundlers resolve `import()` statically, so the server SDK — which is
 * marked `server-only` — was pulled into the client bundle of every component
 * that touches `lib/api.ts`, and Next refused to compile.
 *
 * So the server half registers itself instead. `lib/auth-server.ts` is imported
 * by the root layout, which is a server component, and installs its token
 * getter on `globalThis`. Nothing a client component imports ever names the
 * server SDK, which is what makes the client bundle clean.
 *
 * **Not configured is a supported state, not a broken one.** With no Clerk
 * publishable key the app behaves exactly as it did before authentication
 * existed: no sign-in, no header, every request anonymous. That mirrors the
 * API's `CODONLAB_AUTH=disabled` — which refuses to start once `CORS_ORIGINS`
 * names a real origin, so the pair cannot be deployed by accident. Keeping that
 * path real is what lets the gate checks and both Playwright flows run against
 * a stack with no identity provider in it.
 */

/** Whether an identity provider is wired up at all. */
export function authConfigured(): boolean {
  return Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY)
}

type TokenGetter = () => Promise<string | null>

interface TokenRegistry {
  __codonlabServerToken?: TokenGetter
}

/**
 * Called by `lib/auth-server.ts` at import time. The indirection exists so that
 * the server SDK is named in exactly one module, and that module is never
 * reachable from a client component.
 */
export function registerServerToken(getter: TokenGetter): void {
  ;(globalThis as TokenRegistry).__codonlabServerToken = getter
}

/** Clerk's browser global, once `<ClerkProvider>` has mounted. */
interface ClerkWindow {
  Clerk?: {
    session?: { getToken: () => Promise<string | null> }
  }
}

/**
 * `Authorization: Bearer <token>`, or `{}`.
 *
 * Returns an empty object rather than throwing when there is no session. A
 * signed-out caller should reach the API and be refused by it — the API is
 * where that decision belongs, and a client that refused locally would report
 * "not signed in" for a server that had actually gone down.
 */
export async function authHeader(): Promise<Record<string, string>> {
  if (!authConfigured()) return {}

  try {
    const token
      = typeof window === 'undefined' ? await serverToken() : await browserToken()
    return token ? { Authorization: `Bearer ${token}` } : {}
  } catch {
    // A token that cannot be minted is the same as not having one: let the
    // request go and let the API answer 401. Failing here would turn a
    // recoverable session refresh into a broken screen.
    return {}
  }
}

/** Server components and server actions, via the registered getter. */
async function serverToken(): Promise<string | null> {
  const getter = (globalThis as TokenRegistry).__codonlabServerToken
  return getter ? getter() : null
}

/** Client components, via Clerk's browser global. */
async function browserToken(): Promise<string | null> {
  const clerk = (window as unknown as ClerkWindow).Clerk
  if (!clerk?.session) return null
  return clerk.session.getToken()
}
