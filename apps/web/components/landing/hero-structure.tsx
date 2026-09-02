'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

import { cn } from '@/lib/cn'

/**
 * The landing page's live 3D structure.
 *
 * Real coordinates, not an illustration: the AlphaFold model of UniProt P37957,
 * *Bacillus subtilis* lipase A — the same protein everything else in this build
 * is measured on. Served as a static asset so this page renders with the API,
 * the worker and the database all down (see `public/structures/README.md`).
 *
 * Mol\* is created headless, the same way `workbench/structure-viewer` does it,
 * so none of Mol\*'s own chrome appears. It is imported dynamically and only in
 * the browser: several megabytes and a WebGL context, neither of which belongs
 * in a landing page's initial payload.
 *
 * **Colour is read from the design tokens at runtime**, never written here.
 * `getComputedStyle` resolves `--accent` and friends off the document, so the
 * viewer cannot drift from the palette and no colour literal enters this file.
 *
 * Two honesty points that are on the page, not just in this comment: the model
 * is labelled predicted rather than experimental, and the residue buttons show
 * both numbering schemes, because the file numbers the full-length precursor
 * while the project's canonical scheme is the mature protein, 31 lower.
 */

/** Catalytic triad. Confirmed against the sequence and the coordinate file. */
export const TRIAD = [
  { mature: 'Ser77', authSeqId: 108, role: 'nucleophile' },
  { mature: 'Asp133', authSeqId: 164, role: 'acid' },
  { mature: 'His156', authSeqId: 187, role: 'base' },
] as const

const STRUCTURE_URL = '/structures/AF-P37957-F1-model_v6.pdb'

type Status = 'loading' | 'ready' | 'error'

/**
 * A design token's current value as a Mol\* colour, or null if it is not a hex.
 *
 * Mol\* has two similarly named parsers and only one of them takes the form CSS
 * writes. `Color.fromHexString` is `parseInt(s)` and expects `0xrrggbb`; handed
 * a CSS `#rrggbb` it returns `NaN`, which renders as black rather than throwing.
 * `Color.fromHexStyle` is the one that strips the `#`. Getting this wrong is
 * silent, which is why it is written down here.
 */
function tokenColour<T>(
  fromHexStyle: (value: string) => T,
  name: string,
  from: Element | null,
): T | null {
  if (typeof window === 'undefined' || !from) return null
  // Resolved from the viewer's own container, not from :root. The landing hero
  // scopes `data-theme="dark"` to a wrapper, and custom properties cascade — so
  // reading here is what makes the model's background follow the section it sits
  // in instead of the document's default theme.
  const value = getComputedStyle(from).getPropertyValue(name).trim()
  if (!/^#[0-9a-f]{6}$/i.test(value)) return null
  return fromHexStyle(value)
}

export function HeroStructure({ containerClassName }: { containerClassName?: string }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  // Typed as unknown so no Mol* type escapes this file — the same boundary the
  // workbench viewer keeps. ARCHITECTURE.md §2: the UI never imports a model
  // client, and it does not import a renderer's types into shared signatures.
  const pluginRef = useRef<unknown>(null)
  const [status, setStatus] = useState<Status>('loading')
  const [focused, setFocused] = useState<number | null>(null)

  useEffect(() => {
    let cancelled = false
    let observer: ResizeObserver | null = null

    async function boot() {
      if (!canvasRef.current || !containerRef.current) return
      try {
        const [{ PluginContext }, { DefaultPluginSpec }, { Color }] = await Promise.all([
          import('molstar/lib/mol-plugin/context'),
          import('molstar/lib/mol-plugin/spec'),
          import('molstar/lib/mol-util/color'),
        ])

        const plugin = new PluginContext(DefaultPluginSpec())
        await plugin.init()
        if (cancelled) {
          plugin.dispose()
          return
        }

        const ok = await plugin.initViewerAsync(canvasRef.current, containerRef.current)
        if (!ok) {
          plugin.dispose()
          if (!cancelled) setStatus('error')
          return
        }
        pluginRef.current = plugin

        const data = await plugin.builders.data.download(
          { url: STRUCTURE_URL, isBinary: false },
          { state: { isGhost: true } },
        )
        const trajectory = await plugin.builders.structure.parseTrajectory(data, 'pdb')
        if (cancelled) return

        // The stock preset builds the scene and frames it. Hand-building the
        // hierarchy instead — to drop the signal peptide from the picture —
        // was tried and produced a component that reported success and rendered
        // nothing, so the preset is what ships: a correct structure beats a
        // cleverer empty one. The signal peptide's disordered tail therefore
        // stays in view, and the caption says what it is rather than pretending
        // the model is all folded protein.
        await plugin.builders.structure.hierarchy.applyPreset(trajectory, 'default')
        if (cancelled) return

        const scope = containerRef.current
        const accent = tokenColour(Color.fromHexStyle, '--accent', scope)
        const flag = tokenColour(Color.fromHexStyle, '--warn', scope)

        // Recolour the preset's own representations rather than replacing them.
        try {
          const typed = plugin as {
            managers: {
              structure: {
                component: {
                  updateRepresentationsTheme: (
                    components: unknown,
                    params: unknown,
                  ) => Promise<void>
                }
                hierarchy: { current: { structures: { components: unknown }[] } }
              }
            }
          }
          const structure = typed.managers.structure.hierarchy.current.structures[0]
          if (structure && accent !== null) {
            await typed.managers.structure.component.updateRepresentationsTheme(
              structure.components,
              { color: 'uniform', colorParams: { value: accent } },
            )
          }
        } catch {
          /* Keep the preset's own colouring. */
        }

        // The triad as sticks, added on top of the preset so a failure here
        // costs the highlight and nothing else. It is the one part of the
        // picture that means more than "this is a protein".
        try {
          const { MolScriptBuilder: MS } = await import(
            'molstar/lib/mol-script/language/builder'
          )
          const entry = (
            plugin as {
              managers: { structure: { hierarchy: { current: { structures: { cell: unknown }[] } } } }
            }
          ).managers.structure.hierarchy.current.structures[0]
          if (entry) {
            const triad = await plugin.builders.structure.tryCreateComponentFromExpression(
              entry.cell as never,
              MS.struct.generator.atomGroups({
                'residue-test': MS.core.set.has([
                  MS.set(...TRIAD.map((residue) => residue.authSeqId)),
                  MS.struct.atomProperty.macromolecular.auth_seq_id(),
                ]),
              }),
              'catalytic-triad',
            )
            if (triad) {
              await plugin.builders.structure.representation.addRepresentation(triad, {
                type: 'ball-and-stick',
                ...(flag === null ? {} : { color: 'uniform', colorParams: { value: flag } }),
              })
            }
          }
        } catch {
          /* The cartoon alone is still correct. */
        }
        if (cancelled) return

        // Everything below is presentation. Each step is guarded on its own so a
        // Mol* API that has moved leaves a correct structure on screen rather
        // than an empty panel — the viewer degrades to default colouring, which
        // is still true, just less on-brand.
        //
        // The background is painted from the surface token rather than made
        // transparent. `transparentBackground` renders this scene as a thin
        // dark outline with no shaded body, which is a worse picture than a
        // matched opaque fill and was measured, not assumed.
        try {
          const background = tokenColour(Color.fromHexStyle, '--surface', containerRef.current)
          if (background !== null) {
            plugin.canvas3d?.setProps({ renderer: { backgroundColor: background } })
          }
        } catch {
          /* The default background is a cosmetic loss, not a failure. */
        }

        // Mol* sizes its drawing buffer from the container when the viewer is
        // created. In a responsive grid the container is often still laying out
        // at that moment, so the WebGL viewport keeps the stale size and the
        // scene renders into one small corner of a correctly sized canvas —
        // which is what happened here, and which looks like a broken renderer
        // rather than a sizing bug. Re-measuring after load fixes it; the
        // observer keeps it fixed when the column reflows.
        // `handleResize` is on the **PluginContext**, not on `canvas3d`.
        // Calling `plugin.canvas3d.handleResize?.()` is a silent no-op — the
        // property is simply undefined — and the symptom is a scene rendered
        // into a 114x114 corner of a 537x537 buffer with no error anywhere.
        // Mol* does subscribe to its own resize input, but that is driven by
        // window resize events, so a container that grows during layout without
        // the window changing never triggers it.
        const resize = () => {
          try {
            plugin.handleResize()
          } catch {
            /* Ignore. */
          }
        }
        resize()
        if (containerRef.current) {
          observer = new ResizeObserver(resize)
          observer.observe(containerRef.current)
        }

        // Mol*'s orientation gizmo is developer chrome. BRIEF.md §3 asks for an
        // embedded, *controlled* viewer; a landing page is not the place to
        // publish another product's debug widget.
        try {
          plugin.canvas3d?.setProps({
            camera: { helper: { axes: { name: 'off', params: {} } } },
          })
        } catch {
          /* Cosmetic. */
        }

        // Frame the model only after the resize has actually been applied. The
        // camera derives its distance from the viewport, so resetting in the
        // same frame as the resize re-frames against the stale size and leaves
        // the model small and off-centre.
        await new Promise((resolve) => requestAnimationFrame(() => resolve(null)))
        if (cancelled) return
        try {
          plugin.canvas3d?.requestCameraReset()
        } catch {
          /* Preset framing stands. */
        }

        // Honour reduced motion: ambient rotation is exactly what DESIGN.md §1.9
        // says to switch off, and a spinning protein is a vestibular problem for
        // some readers.
        const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches
        if (!still) {
          try {
            // `axis` is required, not optional: trackball's spin reads
            // `params.axis[0]` directly, so omitting it throws on the first
            // animation tick and the whole loop dies. Vec3(0, -1, 0) is the
            // default — rotation about the camera's up vector.
            plugin.canvas3d?.setProps({
              trackball: {
                animate: { name: 'spin', params: { speed: 0.08, axis: [0, -1, 0] } },
              },
            })
          } catch {
            /* A static model is fine. */
          }
        }

        if (!cancelled) setStatus('ready')
      } catch {
        if (!cancelled) setStatus('error')
      }
    }

    void boot()
    return () => {
      cancelled = true
      observer?.disconnect()
      const plugin = pluginRef.current as { dispose: () => void } | null
      if (plugin) {
        plugin.dispose()
        pluginRef.current = null
      }
    }
  }, [])

  /** Select and frame one residue, by the number the *file* uses. */
  const focus = useCallback(async (authSeqId: number) => {
    const plugin = pluginRef.current
    if (!plugin) return
    setFocused(authSeqId)
    try {
      const [{ Script }, { StructureSelection }] = await Promise.all([
        import('molstar/lib/mol-script/script'),
        import('molstar/lib/mol-model/structure'),
      ])
      const typed = plugin as {
        canvas3d?: { setProps: (props: unknown) => void }
        managers: {
          structure: {
            hierarchy: { current: { structures: { cell: { obj?: { data: unknown } } }[] } }
          }
          camera: { focusLoci: (loci: unknown) => void }
          interactivity: { lociSelects: { selectOnly: (input: { loci: unknown }) => void } }
        }
      }
      const data = typed.managers.structure.hierarchy.current.structures[0]?.cell.obj?.data
      if (!data) return

      // Stop the spin once someone takes control; a model that keeps turning
      // under a residue you just asked to look at is fighting the reader.
      try {
        typed.canvas3d?.setProps({ trackball: { animate: { name: 'off', params: {} } } })
      } catch {
        /* Ignore. */
      }

      const selection = Script.getStructureSelection(
        (q) =>
          q.struct.generator.atomGroups({
            'residue-test': q.core.rel.eq([
              q.struct.atomProperty.macromolecular.auth_seq_id(),
              authSeqId,
            ]),
          }),
        data as never,
      )
      const loci = StructureSelection.toLociWithSourceUnits(selection)
      typed.managers.interactivity.lociSelects.selectOnly({ loci })
      typed.managers.camera.focusLoci(loci)
    } catch {
      /* Focusing is a convenience; never take the panel down for it. */
    }
  }, [])

  return (
    <figure className="m-0">
      <div
        ref={containerRef}
        data-testid="hero-structure"
        data-status={status}
        className={cn(
          'bg-surface rounded-panel relative aspect-square w-full overflow-hidden',
          containerClassName ?? 'border-border border',
        )}
      >
        <canvas ref={canvasRef} className="absolute inset-0 size-full" />
        {status !== 'ready' ? (
          <div className="absolute inset-0 flex items-center justify-center p-6">
            <p className="text-12 text-text-muted text-center">
              {status === 'loading'
                ? 'Loading structure…'
                : 'This browser has no WebGL context, so the model cannot be drawn.'}
            </p>
          </div>
        ) : null}

        {status === 'ready' ? (
          <div className="absolute inset-x-0 bottom-0 flex flex-wrap items-center gap-1.5 p-3">
            <span className="text-11 text-text-muted mr-1">Catalytic triad</span>
            {TRIAD.map((residue) => (
              <button
                key={residue.authSeqId}
                type="button"
                onClick={() => void focus(residue.authSeqId)}
                aria-pressed={focused === residue.authSeqId}
                title={`${residue.mature} — the ${residue.role}. Numbered ${residue.authSeqId} in the coordinate file.`}
                className={
                  focused === residue.authSeqId
                    ? 'border-accent bg-accent text-surface rounded-control h-control-sm text-11 inline-flex items-center border px-2 font-mono'
                    : 'border-border bg-surface text-text hover:bg-surface-sunk rounded-control h-control-sm text-11 inline-flex items-center border px-2 font-mono'
                }
              >
                {residue.mature}
              </button>
            ))}
          </div>
        ) : null}
      </div>

      <figcaption className="text-11 text-text-muted mt-2">
        <i>Bacillus subtilis</i> lipase A (UniProt P37957), AlphaFold prediction — a model, not
        an experimental structure. Residues are labelled in the mature-protein scheme; the
        coordinate file numbers them 31 higher, which is the kind of disagreement this product
        exists to keep track of.
      </figcaption>
    </figure>
  )
}
