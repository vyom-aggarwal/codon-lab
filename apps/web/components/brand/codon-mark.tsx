import { cn } from '@/lib/cn'

/**
 * The Codon Lab mark.
 *
 * **A segment of duplex DNA, twisting.** Two backbone strands run straight
 * through the middle and then flick away at the top left and the bottom right,
 * giving the segment a twist without the coiling that turns a small helix into
 * an illegible spring.
 *
 * Five rungs: three at full width across the straight core, and two shorter ones
 * out on the flares. The short pair is not a decorative flourish — as the duplex
 * rotates away from the viewer its base pairs foreshorten, so a rung further
 * into the twist is drawn narrower. Dropping them leaves a clean ladder that
 * reads as a ladder; keeping them is what makes the form read as turning.
 *
 * The form has 180-degree rotational symmetry, so it reads the same inverted and
 * needs no separate variant for a dark ground.
 *
 * Drawn at stroke 1.5 on a 24-unit grid — the same construction `DESIGN.md` §1.9
 * fixes for every icon in the product. That is deliberate: a mark drawn in a
 * different weight to the interface around it reads as an imported asset, and
 * this one is meant to read as part of the same drawing.
 *
 * `currentColor` throughout, so the mark takes whatever token its context sets
 * and never introduces a colour of its own.
 *
 * Geometry, so it can be reproduced rather than traced: the straight core runs
 * y=8 to y=16 at x=7 and x=17; the strands leave it on a curve to (4.5, 3) and
 * (19.5, 21). Full-width rungs sit on the core at y=8.5, 12 and 15.5; the
 * foreshortened pair spans x=9.5 to 14.5 at y=5 and y=19. Twelve alternatives
 * were drawn and compared at 16, 20, 24, 32 and 48px before this one; the ones
 * that failed did so by reading as something else — a bowtie, a euro sign, a
 * text-align icon, a document, a shopping trolley.
 */
export function CodonMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={cn('size-4', className)}
    >
      {/* Backbone strands. */}
      <path d="M4.5 3C6.5 4.8 7 6.2 7 8V16C7 17.8 7.5 19.2 9.5 21" />
      <path d="M19.5 21C17.5 19.2 17 17.8 17 16V8C17 6.2 16.5 4.8 14.5 3" />
      {/* Base pairs across the straight core. */}
      <path d="M7 8.5H17" />
      <path d="M7 12H17" />
      <path d="M7 15.5H17" />
      {/* Two more, foreshortened, where the duplex turns away. */}
      <path d="M9.5 5H14.5" />
      <path d="M9.5 19H14.5" />
    </svg>
  )
}

/**
 * Mark plus wordmark, the standard lockup.
 *
 * The wordmark is the UI face at weight 560 — the heaviest this product has,
 * since `DESIGN.md` §1.5 caps at 560 and bans 700 and above. Setting it in a
 * third face for the logo alone would be the first crack in a two-face system.
 */
export function CodonWordmark({
  className,
  markClassName,
  labelClassName,
}: {
  className?: string
  markClassName?: string
  labelClassName?: string
}) {
  return (
    <span className={cn('inline-flex items-center gap-2', className)}>
      <CodonMark className={cn('text-accent', markClassName)} />
      <span className={cn('text-13 font-strong text-text', labelClassName)}>Codon Lab</span>
    </span>
  )
}
