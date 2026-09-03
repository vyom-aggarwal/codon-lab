'use client'

import { useEffect, useState } from 'react'

import { Dialog, DialogContent } from '@/components/ui'

/**
 * The `?` shortcut sheet. `BRIEF.md` §4, deferred to Phase 9 in `DESIGN.md` §9.
 *
 * `DESIGN.md` §9 says of this sheet: "It documents the shortcuts, so it follows
 * them." That is the rule the contents obey — **every binding listed here is one
 * that exists**, and the list is checked against the handlers in
 * `keyboard.test.tsx`. A shortcut sheet that lists a key nothing implements is
 * worse than no sheet: it is the product telling the user something untrue about
 * itself, and the user finds out by pressing the key.
 *
 * Opening on `?` deliberately ignores the key while a text field has focus,
 * because `?` is an ordinary character and a user typing a question mark into
 * the goal composer is not asking for help.
 */

/** Keys that exist. Anything added here needs a handler that answers to it. */
export const SHORTCUTS: { group: string; keys: [string, string][] }[] = [
  {
    group: 'Anywhere',
    keys: [
      ['⌘K  /  Ctrl K', 'Open the command palette'],
      ['?', 'Open this sheet'],
      ['Esc', 'Close the topmost layer'],
    ],
  },
  {
    group: 'Variant table',
    keys: [
      ['j  /  ↓', 'Move down a row'],
      ['k  /  ↑', 'Move up a row'],
      ['x', 'Select or deselect the focused row'],
      ['Enter', 'Open the focused row in the inspector'],
      ['Esc', 'Close the provenance drawer, then clear the selection'],
    ],
  },
  {
    group: 'Command palette',
    keys: [
      ['↑  /  ↓', 'Move through results'],
      ['Enter', 'Run the highlighted command'],
      ['Type a mutation code', 'Find it in the workbench, inside a run'],
    ],
  },
]

export function ShortcutSheet() {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== '?') return
      const target = event.target as HTMLElement | null
      // `?` is a character. Typing one into a field is not a request for help.
      if (
        target &&
        (['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) || target.isContentEditable)
      ) {
        return
      }
      event.preventDefault()
      setOpen((previous) => !previous)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent
        title="Keyboard shortcuts"
        description="Every key listed here is one the application answers to."
      >
        <div className="max-h-96 space-y-6 overflow-y-auto p-4">
          {SHORTCUTS.map((section) => (
            <section key={section.group}>
              <h3 className="text-11 text-text-muted uppercase">{section.group}</h3>
              <dl className="border-border mt-2 border-t">
                {section.keys.map(([key, meaning]) => (
                  <div
                    key={`${section.group}-${key}`}
                    className="border-border flex items-baseline gap-4 border-b py-2"
                  >
                    <dt className="w-40 shrink-0">
                      <kbd className="text-12 text-text border-border rounded-control border px-1.5 py-0.5 font-mono">
                        {key}
                      </kbd>
                    </dt>
                    <dd className="text-13 text-text-muted">{meaning}</dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  )
}
