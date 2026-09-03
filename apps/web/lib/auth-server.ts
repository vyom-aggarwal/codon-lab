import 'server-only'

import { registerServerToken } from '@/lib/auth'

/**
 * The server half of token retrieval, kept in a module no client component can
 * reach.
 *
 * `server-only` is the enforcement: importing this from a client component is a
 * build error naming this file, rather than a runtime failure somewhere else.
 * That matters because the mistake it prevents — pulling Clerk's server SDK
 * into a browser bundle — is exactly the one that happened while writing this,
 * and the error message pointed at the shared module rather than the cause.
 *
 * Imported for its side effect by `app/layout.tsx`. Every route in the app is
 * under that layout, so this module is loaded before any page renders, and the
 * getter is installed before the first server-side fetch runs.
 */
registerServerToken(async () => {
  // Imported here rather than at the top of the file so that a project with no
  // Clerk configured never loads the SDK at all.
  const { auth } = await import('@clerk/nextjs/server')
  const session = await auth()
  return session.getToken()
})
