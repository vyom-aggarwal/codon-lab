'use client'

import { SignInButton, SignedIn, SignedOut, UserButton } from '@clerk/nextjs'

import { authConfigured } from '@/lib/auth'

/**
 * Who is signed in, and the way in or out. Sits at the foot of the rail.
 *
 * Renders **nothing at all** when no identity provider is configured, which is
 * the local development mode. A disabled "Sign in" control on a machine where
 * signing in is not a thing would be exactly the dead affordance `AppFrame`'s
 * own comment says the rail must not have.
 *
 * `<SignedIn>` and `<SignedOut>` are Clerk's own boundaries rather than a
 * `useUser()` check, because they render correctly during the moment before the
 * session resolves. Doing it by hand flashes the signed-out state on every load.
 */
export function AccountControl() {
  if (!authConfigured()) return null

  return (
    <div className="border-border mt-auto border-t p-2">
      <SignedIn>
        <div className="flex items-center gap-2 px-1 py-1">
          {/* Where sign-out lands is set once on `<ClerkProvider>` rather
              than here, so every sign-out in the app agrees. */}
          <UserButton />
          <span className="text-12 text-text-muted truncate">Signed in</span>
        </div>
      </SignedIn>
      <SignedOut>
        <SignInButton mode="modal">
          <button
            type="button"
            className="h-control rounded-control text-13 text-text hover:bg-surface-sunk flex w-full items-center px-2"
          >
            Sign in
          </button>
        </SignInButton>
      </SignedOut>
    </div>
  )
}
