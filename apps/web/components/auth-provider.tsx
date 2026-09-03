'use client'

import { ClerkProvider } from '@clerk/nextjs'
import { type ReactNode, useEffect, useState } from 'react'

import { authConfigured } from '@/lib/auth'

/**
 * Wraps the app in Clerk's provider, or in nothing.
 *
 * The "or in nothing" is the point. `<ClerkProvider>` throws when it renders
 * without a publishable key, so an unconditional wrap would make the app
 * unrunnable on any machine with no identity provider — which is every machine
 * running the gates, both Playwright flows, and local development. Importing it
 * is harmless; only rendering it is not, so the conditional is on the render.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const accent = useAccent()
  if (!authConfigured()) return <>{children}</>

  return (
    <ClerkProvider
      // Signing out returns to the landing page rather than to the screen they
      // were on, which would immediately 401 and read as an error rather than
      // as having signed out.
      afterSignOutUrl="/"
      // Spread rather than passed as `undefined`: tsconfig sets
      // `exactOptionalPropertyTypes`, under which an explicit undefined is not
      // the same as an absent property.
      {...(accent ? { appearance: { variables: { colorPrimary: accent } } } : {})}
    >
      {children}
    </ClerkProvider>
  )
}

/**
 * `--accent`, resolved to a real colour.
 *
 * Read from the DOM rather than written here for two reasons, and the second is
 * the one that forces it. `tokens.test.ts` fails the build on a hex literal
 * anywhere under `components/`, so the value cannot be spelled out. And Clerk
 * derives a whole colour scale from `colorPrimary` — it needs something it can
 * lighten and darken, so handing it the string `var(--accent)` does not work.
 *
 * Resolving it at runtime satisfies both, and has the property a hardcoded pair
 * could not: it follows the theme. A sign-in box in another product's blue is
 * the most obvious possible seam, and it is the first screen anybody sees.
 *
 * Returns null on the first render — there is no DOM to read during SSR — and
 * Clerk uses its own default until the effect lands.
 */
function useAccent(): string | null {
  const [accent, setAccent] = useState<string | null>(null)

  useEffect(() => {
    const value = getComputedStyle(document.documentElement)
      .getPropertyValue('--accent')
      .trim()
    setAccent(value || null)
  }, [])

  return accent
}
