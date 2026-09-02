import { LIPASE_SEQUENCE, SIGNAL_PEPTIDE_LENGTH, TRIAD_POSITIONS } from '@/lib/landing/lipase'

/**
 * The full 212-residue sequence of the protein in the viewer above, as one line.
 *
 * Real characters, not decoration: UniProt P37957, the same sequence the seeded
 * project designs against and the same one the 3D model is built from. It is
 * here because a protein-engineering product should show a sequence, and because
 * it makes two facts visible that the prose only asserts — how much of the
 * record is signal peptide, and how far apart in sequence three residues that sit
 * on top of each other in space are.
 *
 * The band deliberately runs off the edge of the viewport rather than wrapping
 * or shrinking. A sequence is long; pretending otherwise by compressing it to
 * fit is the same instinct as rounding a number to make it look tidier.
 */
export function SequenceBand() {
  const triad = new Set<number>(TRIAD_POSITIONS)

  return (
    <section aria-label="Target sequence" className="border-border border-y">
      <div className="mx-auto max-w-5xl px-6 pt-8 md:px-10">
        <p className="text-11 text-text-muted uppercase">The target</p>
      </div>

      <div className="mt-4 w-full overflow-x-auto">
        <p className="text-13 w-max px-6 font-mono whitespace-pre md:px-10">
          {Array.from(LIPASE_SEQUENCE).map((residue, index) => {
            const position = index + 1
            if (triad.has(position)) {
              return (
                <span key={position} className="text-warn font-strong">
                  {residue}
                </span>
              )
            }
            return (
              <span
                key={position}
                className={
                  position <= SIGNAL_PEPTIDE_LENGTH ? 'text-text-faint' : 'text-text-muted'
                }
              >
                {residue}
              </span>
            )
          })}
        </p>
      </div>

      <div className="mx-auto max-w-5xl px-6 pt-4 pb-8 md:px-10">
        <p className="text-12 text-text-muted max-w-3xl">
          <span className="text-text">P37957</span>, 212 residues.{' '}
          <span className="text-text-faint">The first 31</span> are the signal peptide, cleaved
          during secretion — which is why the project numbers the mature protein 31 lower, and
          why every mutation code in the app carries the scheme it was written in.{' '}
          <span className="text-warn">Ser108, Asp164, His187</span> are the catalytic triad: far
          apart here, adjacent in the fold above.
        </p>
      </div>
    </section>
  )
}
