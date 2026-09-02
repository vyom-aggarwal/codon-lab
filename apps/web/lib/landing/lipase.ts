/**
 * The sequence the landing page's sequence band renders.
 *
 * *Bacillus subtilis* lipase A, UniProt **P37957**, 212 residues, full-length
 * precursor — the same protein the rest of this build is measured on.
 *
 * This is a copy. The source of truth is
 * `apps/api/codonlab/data/proteingym/ESTA_BACSU_target.fasta`, which the web
 * container cannot read: docker-compose mounts `apps/web` and `packages`, not
 * `apps/api`. A copy that could silently disagree with its source is exactly
 * what this codebase refuses elsewhere, so `landing.test.tsx` reads the FASTA
 * off disk and asserts byte-equality — the duplication is real, but the build
 * proves the two are identical rather than trusting that they are.
 */
export const LIPASE_SEQUENCE =
  'MKFVKRRIIALVTILMLSVTSLFALQPSAKAAEHNPVVMVHGIGGASFNFAGIKSYLVSQ' +
  'GWSRDKLYAVDFWDKTGTNYNNGPVLSRFVQKVLDETGAKKVDIVAHSMGGANTLYYIKN' +
  'LDGGNKVANVVTLGGANRLTTGKALPGTDPNQKILYTSIYSSADMIVMNYLSRLDGARNV' +
  'QIHGVGHIGLLYSSQVNSLIKEGLNGGGQNTN'

/** Residues 1-31 are the signal peptide, cleaved during secretion. */
export const SIGNAL_PEPTIDE_LENGTH = 31

/**
 * Catalytic triad, as positions in the sequence above (full-length numbering).
 * The mature scheme this project uses calls them Ser77, Asp133 and His156.
 */
export const TRIAD_POSITIONS = [108, 164, 187] as const
