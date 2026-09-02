'use client'

import { usePathname } from 'next/navigation'
import type { ReactNode } from 'react'

import { AppFrame } from './app-frame'

/**
 * Chooses between the application chrome and no chrome at all.
 *
 * The landing page at `/` is the one route that is **not** part of the
 * application: it has no left rail, no demo banner, and nothing that implies
 * the user is inside a project. `BRIEF.md` §4 bans a marketing hero *inside the
 * app*, and this is what keeps that true — the marketing surface and the
 * instrument are different documents that happen to share a domain.
 *
 * A route group (`app/(app)/…`) is the idiomatic Next.js way to split layouts,
 * and it was not used here because it would rename the import path of every
 * page under it for a one-route exception. This switch is smaller and its
 * failure mode is visible immediately.
 */
export function Shell({ demoMode, children }: { demoMode: boolean; children: ReactNode }) {
  const pathname = usePathname()

  if (pathname === '/') return <>{children}</>
  return <AppFrame demoMode={demoMode}>{children}</AppFrame>
}
