import { FlaskConical } from 'lucide-react'
import Link from 'next/link'
import type { ReactNode } from 'react'

import { DemoBanner } from './demo-banner'

/**
 * The application shell: left rail plus content.
 *
 * The rail lists only what exists. A navigation full of dead entries for screens
 * that have not been built teaches the user that this product's affordances lie.
 */
export function AppFrame({ demoMode, children }: { demoMode: boolean; children: ReactNode }) {
  return (
    <div className="bg-canvas flex h-dvh flex-col">
      {demoMode ? <DemoBanner /> : null}
      <div className="flex min-h-0 flex-1">
        <nav
          aria-label="Primary"
          className="w-rail border-border bg-surface flex shrink-0 flex-col border-r"
        >
          <div className="border-border flex h-12 items-center gap-2 border-b px-4">
            <FlaskConical className="text-accent size-4" strokeWidth={1.5} />
            <span className="text-13 font-strong">Codon Lab</span>
          </div>
          <ul className="p-2">
            <li>
              <Link
                href="/projects"
                className="h-control rounded-control text-13 text-text hover:bg-surface-sunk flex items-center px-2"
              >
                Projects
              </Link>
            </li>
            <li>
              <Link
                href="/scorecard"
                className="h-control rounded-control text-13 text-text hover:bg-surface-sunk flex items-center px-2"
              >
                Scorecard
              </Link>
            </li>
          </ul>
        </nav>
        <main className="min-w-0 flex-1 overflow-auto">{children}</main>
      </div>
    </div>
  )
}
