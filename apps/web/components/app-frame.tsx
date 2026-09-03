import Link from 'next/link'
import type { ReactNode } from 'react'

import { CodonMark } from './brand/codon-mark'
import { CommandPalette } from './command-palette'
import { DemoBanner } from './demo-banner'
import { ShortcutSheet } from './shortcut-sheet'

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
          <Link
            href="/"
            className="border-border hover:bg-surface-sunk flex h-12 items-center gap-2 border-b px-4"
          >
            <CodonMark className="text-accent" />
            <span className="text-13 font-strong">Codon Lab</span>
          </Link>
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

      {/* Global keyboard surfaces. Mounted here rather than per screen so
          `⌘K` and `?` work everywhere inside the application — and nowhere on
          the landing page, which `Shell` renders without this frame. */}
      <CommandPalette />
      <ShortcutSheet />
    </div>
  )
}
