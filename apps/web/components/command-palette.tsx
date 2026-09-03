'use client'

import * as DialogPrimitive from '@radix-ui/react-dialog'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, Search } from 'lucide-react'
import { usePathname, useRouter } from 'next/navigation'
import type { Route } from 'next'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { cn } from '@/lib/cn'
import { fetchProjects } from '@/lib/api'
import { useWorkbench } from '@/lib/workbench-store'

/**
 * The `⌘K` command palette. `BRIEF.md` §4, deferred to Phase 9 in `DESIGN.md` §9.
 *
 * The brief names four things it must do: "jump to project, add a constraint,
 * start a run, open a variant by typing `A123V`". Three of those are only
 * meaningful somewhere — you cannot add a constraint without a target — so the
 * palette reads its context out of the pathname and offers exactly the actions
 * that are reachable from where the user actually is. Offering "add a
 * constraint" with nowhere to add it would be a dead entry, and a navigation
 * full of dead entries teaches the user that this product's affordances lie.
 *
 * **It is a dialog on purpose.** `DESIGN.md` §2 reserves modals for
 * interruptions that genuinely block and sends anything referenced *while
 * working* to the inspector. A command palette is the former: it blocks by
 * definition, it is dismissed by `Esc`, and nothing is lost behind it. Radix's
 * Dialog gives the focus trap, the `aria-modal` semantics and the restore-focus
 * behaviour, none of which is worth reimplementing for a keyboard surface whose
 * whole point is being correct for keyboard users.
 *
 * Rendered from `AppFrame`, so it exists on every application screen and on none
 * of the landing page — which has no projects to jump to and no chrome.
 */

interface Command {
  id: string
  label: string
  /** Shown right-aligned: what kind of thing this is. */
  kind: string
  run: () => void
  /** Extra text the query matches against, never displayed. */
  keywords?: string
}

/** `S77A`, `p.Ser77Ala`, `A10V/S77A` — anything that could name a variant. */
const LOOKS_LIKE_A_CODE = /^(p\.)?[A-Za-z]{1,3}-?\d+[A-Za-z]{0,3}([/,+]\s*[A-Za-z]{1,3}-?\d+[A-Za-z]{0,3})*$/

export function CommandPalette() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const listRef = useRef<HTMLUListElement>(null)

  const router = useRouter()
  const pathname = usePathname()
  const setFilter = useWorkbench((state) => state.setFilter)
  const focusVariant = useWorkbench((state) => state.focus)

  // Only fetched while the palette is open: the projects list is not needed by
  // any screen that is not showing it, and this component mounts on all of them.
  const { data: projects, isError } = useQuery({
    queryKey: ['projects'],
    queryFn: fetchProjects,
    enabled: open,
  })

  const targetId = /^\/targets\/([^/]+)/.exec(pathname)?.[1] ?? null
  const runId = /^\/runs\/([^/]+)/.exec(pathname)?.[1] ?? null

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key.toLowerCase() === 'k' && (event.metaKey || event.ctrlKey)) {
        event.preventDefault()
        setOpen((previous) => !previous)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  const go = useCallback(
    (href: string) => {
      setOpen(false)
      router.push(href as Route)
    },
    [router],
  )

  const commands = useMemo<Command[]>(() => {
    const found: Command[] = [
      { id: 'nav-projects', label: 'Projects', kind: 'Go to', run: () => go('/projects') },
      {
        id: 'nav-scorecard',
        label: 'Scorecard, all targets',
        kind: 'Go to',
        keywords: 'predictor spearman validation',
        run: () => go('/scorecard'),
      },
    ]

    if (targetId) {
      found.push(
        {
          id: 'target-constraints',
          label: 'Add a constraint',
          kind: 'This target',
          keywords: 'catalytic ligand disulfide do not touch',
          run: () => go(`/targets/${targetId}/constraints`),
        },
        {
          id: 'target-goal',
          label: 'Start a design run',
          kind: 'This target',
          keywords: 'goal composer objective parse confirm',
          run: () => go(`/targets/${targetId}/goal`),
        },
        {
          id: 'target-measurements',
          label: 'Import measured results',
          kind: 'This target',
          keywords: 'bench upload csv join',
          run: () => go(`/targets/${targetId}/measurements`),
        },
        {
          id: 'target-scorecard',
          label: 'Scorecard for this target',
          kind: 'This target',
          run: () => go(`/targets/${targetId}/scorecard`),
        },
      )
    }

    if (runId) {
      found.push(
        {
          id: 'run-workbench',
          label: 'Variant workbench',
          kind: 'This run',
          run: () => go(`/runs/${runId}/workbench`),
        },
        {
          id: 'run-view',
          label: 'Run stages and provenance',
          kind: 'This run',
          run: () => go(`/runs/${runId}`),
        },
        {
          id: 'run-design-sets',
          label: 'Design sets',
          kind: 'This run',
          keywords: 'stack epistasis order',
          run: () => go(`/runs/${runId}/design-sets`),
        },
      )
    }

    for (const project of projects ?? []) {
      found.push({
        id: `project-${project.id}`,
        label: project.name,
        kind: 'Project',
        keywords: project.organism ?? '',
        run: () => go(`/projects/${project.id}`),
      })
    }

    return found
  }, [go, projects, runId, targetId])

  const trimmed = query.trim()

  /**
   * A mutation code becomes its own command, and only inside a run.
   *
   * It sets the workbench's filter and focuses the code rather than inventing a
   * second way to locate a row — the filter is already the tested path, and a
   * code that matches nothing then shows the table's own empty state with its
   * reason instead of this palette claiming a variant exists.
   */
  const codeCommand = useMemo<Command | null>(() => {
    if (!runId || !trimmed || !LOOKS_LIKE_A_CODE.test(trimmed)) return null
    const code = trimmed.toUpperCase()
    return {
      id: 'find-variant',
      label: `Find ${code} in the workbench`,
      kind: 'Variant',
      run: () => {
        setFilter('query', code)
        focusVariant(code)
        go(`/runs/${runId}/workbench`)
      },
    }
  }, [focusVariant, go, runId, setFilter, trimmed])

  const results = useMemo(() => {
    const needle = trimmed.toLowerCase()
    const matched = needle
      ? commands.filter(
          (command) =>
            command.label.toLowerCase().includes(needle) ||
            command.kind.toLowerCase().includes(needle) ||
            (command.keywords ?? '').toLowerCase().includes(needle),
        )
      : commands
    return codeCommand ? [codeCommand, ...matched] : matched
  }, [codeCommand, commands, trimmed])

  useEffect(() => setActive(0), [query, open])

  // Keep the highlighted row in view when the keyboard moves past the fold.
  useEffect(() => {
    listRef.current?.querySelector('[data-active="true"]')?.scrollIntoView({ block: 'nearest' })
  }, [active])

  function onInputKeyDown(event: React.KeyboardEvent) {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActive((index) => Math.min(results.length - 1, index + 1))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActive((index) => Math.max(0, index - 1))
    } else if (event.key === 'Enter') {
      event.preventDefault()
      results[active]?.run()
    }
  }

  return (
    <DialogPrimitive.Root open={open} onOpenChange={setOpen}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="bg-text/20 fixed inset-0 z-50" />
        <DialogPrimitive.Content
          aria-label="Command palette"
          className={cn(
            'fixed left-1/2 top-24 z-50 w-full max-w-xl -translate-x-1/2',
            'rounded-dialog border-border bg-surface shadow-dialog border',
            'animate-[layer-in_var(--duration-base)_var(--ease-out-quint)]',
          )}
        >
          <DialogPrimitive.Title className="sr-only">Command palette</DialogPrimitive.Title>
          <DialogPrimitive.Description className="sr-only">
            Search for a project, an action on the current target or run, or a mutation code.
          </DialogPrimitive.Description>

          <div className="border-border flex items-center gap-2 border-b px-3">
            <Search aria-hidden="true" className="text-text-muted size-4 shrink-0" strokeWidth={1.5} />
            <input
              autoFocus
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={onInputKeyDown}
              placeholder="Jump to a project, an action, or a mutation code"
              aria-label="Command"
              aria-controls="command-results"
              aria-activedescendant={results[active] ? `command-${results[active].id}` : undefined}
              className="text-13 text-text placeholder:text-text-faint h-12 w-full bg-transparent focus:outline-none"
            />
            <kbd className="text-11 text-text-muted border-border rounded-control shrink-0 border px-1.5 py-0.5 font-mono">
              Esc
            </kbd>
          </div>

          <ul
            id="command-results"
            ref={listRef}
            role="listbox"
            aria-label="Commands"
            className="max-h-80 overflow-y-auto p-1"
          >
            {results.map((command, index) => (
              <li key={command.id}>
                <button
                  type="button"
                  id={`command-${command.id}`}
                  role="option"
                  aria-selected={index === active}
                  data-active={index === active}
                  onMouseEnter={() => setActive(index)}
                  onClick={() => command.run()}
                  className={cn(
                    'rounded-control h-control flex w-full items-center gap-2 px-2 text-left',
                    index === active ? 'bg-accent-sunk text-text' : 'text-text',
                  )}
                >
                  <span className="text-13 truncate">{command.label}</span>
                  <span className="text-11 text-text-muted ml-auto shrink-0 uppercase">
                    {command.kind}
                  </span>
                  {index === active ? (
                    <ArrowRight aria-hidden="true" className="text-text-muted size-4 shrink-0" strokeWidth={1.5} />
                  ) : null}
                </button>
              </li>
            ))}

            {results.length === 0 ? (
              <li className="px-2 py-6">
                <p className="text-13 text-text">Nothing matches {`"${trimmed}"`}.</p>
                <p className="text-12 text-text-muted mt-1">
                  {isError
                    ? 'The projects list could not be loaded, so projects are missing from these results. Check the api service.'
                    : runId
                      ? 'Try a project name, or a mutation code such as S77A.'
                      : 'Try a project name. Actions for a target or a run appear once you are inside one.'}
                </p>
              </li>
            ) : null}
          </ul>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}
