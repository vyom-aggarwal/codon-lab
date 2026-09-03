import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { CodonMark, CodonWordmark } from '@/components/brand/codon-mark'
import { Shell } from '@/components/shell'
import { TRIAD } from '@/components/landing/hero-structure'
import {
  LIPASE_SEQUENCE,
  SIGNAL_PEPTIDE_LENGTH,
  TRIAD_POSITIONS,
} from '@/lib/landing/lipase'

/** Swapped per test; read by the hoisted `next/navigation` mock below. */
let currentPath = '/'

vi.mock('next/navigation', () => ({
  usePathname: () => currentPath,
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
}))

/**
 * The brand mark, the landing page's structural claims, and the one piece of
 * arithmetic on that page that could be wrong in the way this whole product
 * exists to prevent.
 */

describe('the mark', () => {
  it('is drawn with five rungs and two strands', () => {
    // The count is the concept: a codon is three bases, and the outer pair are
    // the same base pairs foreshortened as the duplex turns. Losing one is a
    // different mark, so the number is asserted rather than eyeballed.
    const { container } = render(<CodonMark />)
    expect(container.querySelectorAll('path')).toHaveLength(7)
  })

  it('introduces no colour of its own', () => {
    const { container } = render(<CodonMark />)
    const svg = container.querySelector('svg')
    expect(svg?.getAttribute('stroke')).toBe('currentColor')
    expect(svg?.getAttribute('fill')).toBe('none')
    // Nothing in the mark may carry a literal colour; it inherits its token.
    expect(container.innerHTML).not.toMatch(/#[0-9a-fA-F]{3,8}/)
  })

  it('is drawn at the same stroke weight as the icon set', () => {
    // DESIGN.md §1.9 fixes every icon at 1.5. A mark at a different weight
    // reads as an imported asset next to the interface it sits in.
    const { container } = render(<CodonMark />)
    expect(container.querySelector('svg')?.getAttribute('stroke-width')).toBe('1.5')
  })

  it('is hidden from assistive technology, since the wordmark carries the name', () => {
    const { container } = render(<CodonMark />)
    expect(container.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true')
  })

  it('locks up with the product name', () => {
    render(<CodonWordmark />)
    expect(screen.getByText('Codon Lab')).toBeInTheDocument()
  })
})

describe('the catalytic triad the 3D demo focuses', () => {
  it('names three residues', () => {
    expect(TRIAD).toHaveLength(3)
  })

  it('keeps the mature and file numbering exactly 31 apart', () => {
    // The coordinate file numbers the full-length precursor; the seeded
    // project's canonical scheme is the mature protein, which starts at
    // residue 32 of that file. Getting this offset wrong is the single most
    // expensive error this application can make, and here it would silently
    // point the camera at the wrong residue while the label stayed right.
    for (const residue of TRIAD) {
      const mature = Number(residue.mature.replace(/^[A-Za-z]{3}/, ''))
      expect(residue.authSeqId - mature, residue.mature).toBe(31)
    }
  })

  it('names the residues in the order they act', () => {
    expect(TRIAD.map((residue) => residue.role)).toEqual(['nucleophile', 'acid', 'base'])
  })

  it('uses the three-letter residue names the structure file uses', () => {
    expect(TRIAD.map((residue) => residue.mature)).toEqual(['Ser77', 'Asp133', 'His156'])
  })
})

describe('the shell keeps the landing page outside the application chrome', () => {
  /**
   * The pathname is swapped through a module-level variable rather than by
   * re-mocking and dynamically re-importing `Shell` per test.
   *
   * The dynamic-import version passed in isolation and timed out inside the
   * full suite — `vi.doMock` plus `await import()` depends on a module registry
   * that other test files have already touched, and the failure mode is a hang
   * rather than a message. A hoisted `vi.mock` is applied before any import in
   * this file resolves, so it does not care what ran first.
   */
  beforeEach(() => {
    currentPath = '/'
  })

  function renderShell() {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    return render(
      <QueryClientProvider client={client}>
        <Shell demoMode={true}>
          <p>content</p>
        </Shell>
      </QueryClientProvider>,
    )
  }

  it('renders the landing route bare', () => {
    currentPath = '/'
    renderShell()
    // No rail, and no demo bar: BRIEF.md §4 bans a marketing hero inside the
    // app, and this is what makes the landing page not be inside it.
    expect(screen.queryByRole('navigation', { name: 'Primary' })).toBeNull()
    expect(screen.queryByText(/Demo data/)).toBeNull()
    expect(screen.getByText('content')).toBeInTheDocument()
  })

  it('renders every other route inside the chrome', () => {
    currentPath = '/projects'
    renderShell()
    expect(screen.getByRole('navigation', { name: 'Primary' })).toBeInTheDocument()
    expect(screen.getByText(/Demo data/)).toBeInTheDocument()
  })
})

describe('the sequence the landing page renders', () => {
  /**
   * `lib/landing/lipase.ts` is a copy: the web container cannot read
   * `apps/api`, which docker-compose does not mount. A copy that can silently
   * disagree with its source is exactly what this codebase refuses elsewhere,
   * so the build proves the two identical rather than trusting that they are.
   */
  const fasta = readFileSync(
    join(
      import.meta.dirname,
      '..',
      '..',
      'api',
      'codonlab',
      'data',
      'proteingym',
      'ESTA_BACSU_target.fasta',
    ),
    'utf8',
  )
  const source = fasta
    .split('\n')
    .filter((line) => line.trim() && !line.startsWith('>'))
    .map((line) => line.trim())
    .join('')

  it('is byte-identical to the vendored FASTA the API seeds from', () => {
    expect(LIPASE_SEQUENCE).toBe(source)
  })

  it('is 212 residues', () => {
    expect(LIPASE_SEQUENCE).toHaveLength(212)
  })

  it('carries the triad residues at the positions the band highlights', () => {
    // Ser, Asp, His — in the file's own full-length numbering, which is what
    // the band renders. Getting these wrong would colour the wrong letters.
    expect(TRIAD_POSITIONS.map((p) => LIPASE_SEQUENCE[p - 1])).toEqual(['S', 'D', 'H'])
  })

  it('agrees with the 3D viewer about which residues those are', () => {
    expect([...TRIAD_POSITIONS]).toEqual(TRIAD.map((residue) => residue.authSeqId))
  })

  it('puts the signal peptide boundary where the mature scheme starts', () => {
    // The mature protein begins at residue 32, so the offset every mutation
    // code on this target is written against is exactly this constant.
    expect(SIGNAL_PEPTIDE_LENGTH).toBe(31)
    expect(LIPASE_SEQUENCE[SIGNAL_PEPTIDE_LENGTH]).toBe('A')
  })
})
