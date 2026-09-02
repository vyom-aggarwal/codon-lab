# Vendored measured data

`BRIEF.md` §7 asks for "a deep-mutational-scanning dataset with real measured
values (ProteinGym is the right source) so the scorecard screen is demoable with
true numbers on day one." This directory is that dataset.

It is vendored rather than fetched at seed time for the same reason the
ThermoMPNN source is (`providers/_vendor`): a seed that reaches the network on
container start fails on a machine without one, and a moving upstream file would
silently change what the scorecard is demonstrating.

## `ESTA_BACSU_Nutschel_2020.csv`

| | |
| --- | --- |
| Retrieved from | `https://huggingface.co/datasets/OATML-Markslab/ProteinGym_v0.1/resolve/main/ProteinGym_substitutions/ESTA_BACSU_Nutschel_2020.csv` |
| Retrieved on | 2026-09-01 |
| SHA-256 | `15c895d371676e981538246b1313f999a840fb6942d728705a5f2f85763359fd` |
| Rows | 2,172 single substitutions |
| ProteinGym assay id | `ESTA_BACSU_Nutschel_2020` |
| Primary source | Nutschel et al. 2020, *J. Chem. Inf. Model.* 60(3), doi:[10.1021/acs.jcim.9b00954](https://doi.org/10.1021/acs.jcim.9b00954) |
| ProteinGym | Notin et al., doi:[10.48550/arXiv.2205.13760](https://doi.org/10.48550/arXiv.2205.13760). MIT licensed. |

### What the numbers are

`DMS_score` is **T50 in degrees Celsius** — the temperature at which half of the
enzyme's activity is lost. ProteinGym's reference file names the raw phenotype
`T50` with directionality `+1`, so **higher is better**. That direction is not
inferred anywhere in the code: the seed passes it explicitly, because which way
an assay points is a fact about the assay and `Experiment.higher_is_better` has
no default.

`DMS_score_bin` is ProteinGym's own median split. It is **not** imported —
a binarised copy of a number already present would be a second answer capable of
disagreeing with the first.

### Why this assay and not another

It is the seeded target. `ESTA_BACSU` is UniProt **P37957**, *Bacillus subtilis*
lipase A — the 212-residue protein `HANDOFF.md` §11 lists as one of the two
targets everything in this build is measured on. The sequence in ProteinGym's
reference file is byte-identical to the sequence this application fetched from
UniProt independently, checked on 2026-09-01.

Mutation codes in this file are written against the **full-length precursor**,
numbered from 1: the first row is `A32N`, and residue 32 is the first residue of
the mature protein. A project whose canonical scheme is the mature protein
therefore reads this file 31 positions off, which is not a defect in the file —
it is the exact situation `domain/joining`'s offset proposal exists for, and the
seeded import exercises it with real data rather than a contrived fixture.

### What it can and cannot demonstrate

It gives the scorecard a real rank statistic: ESM-2 650M scored ρ = 0.30 against
these 2,172 measurements on this machine, where the synthetic predictor scored
−0.06.

It **cannot** give the scorecard an MAE or a bias term, and that is the point
worth understanding rather than a gap to fill. A predicted ΔΔG is in kcal/mol
and a predicted log-likelihood ratio is unitless; a measured T50 is in degrees
Celsius. `BRIEF.md` §7 forbids claiming a Tm shift in °C from a ΔΔG prediction,
so `domain/scorecard.commensurable` refuses the subtraction and states why.
Exercising the error and bias terms with real data needs a measured **ΔΔG in
kcal/mol** from the same lab — which is what a user of this product uploads, and
which no public dataset was seeded for, because none was found whose quantity
could be verified to mean the same thing as ThermoMPNN's ΔΔG. Guessing that it
did would produce a confident MAE over two different physical quantities, which
is precisely the failure the commensurability gate exists to prevent.

## `ESTA_BACSU_target.fasta`

The 212-residue sequence the measurements above were made on, so the seed does
not have to write a protein sequence into a Python file. `seed.py`'s original
scope note refuses to do that — "writing a real protein sequence from memory is
exactly the kind of fabricated scientific content this product exists to
refuse" — and this file keeps that true: the seed reads a sourced artefact
rather than carrying a remembered one.

Taken verbatim from `target_seq` in ProteinGym's
`reference_files/DMS_substitutions.csv` for assay `ESTA_BACSU_Nutschel_2020`,
wrapped at 61 columns. Checked on 2026-09-01 against
`https://rest.uniprot.org/uniprotkb/P37957.fasta`: **byte-identical**, 212
residues. The header line is UniProt's own.

The seed still verifies the length and the residues it mutates before writing
anything, so a corrupted copy of this file fails loudly rather than seeding a
target whose numbering is quietly wrong.
