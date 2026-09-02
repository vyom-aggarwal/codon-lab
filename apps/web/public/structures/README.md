# Vendored structure

One file, served statically to the landing page's 3D viewer.

## `AF-P37957-F1-model_v6.pdb`

| | |
| --- | --- |
| Retrieved from | `https://alphafold.ebi.ac.uk/files/AF-P37957-F1-model_v6.pdb` |
| Resolved via | `https://alphafold.ebi.ac.uk/api/prediction/P37957` (v4 is gone; v6 is current) |
| Retrieved on | 2026-09-02 |
| SHA-256 | `91a9f8f0046c17452a7d4f56548b55a34450315ff412b47a6691096956d63ea8` |
| Residues | 212, numbered 1–212 (full-length precursor) |
| Licence | CC-BY-4.0, AlphaFold Protein Structure Database (EMBL-EBI / DeepMind) |

This is the same protein the rest of the build is measured on: UniProt **P37957**,
*Bacillus subtilis* lipase A. It is a **predicted** model, not an experimental
structure, and the landing page says so on the page rather than only here.

### Why it is vendored rather than fetched

The landing page must render when the API, the worker and the database are all
down — it is the page someone sees before any of that exists. Fetching through
`/targets/{id}/structure` would need a target id that only exists in a seeded
database, and fetching AlphaFold DB directly from the browser would put a
third-party CORS dependency in front of the first thing a visitor sees.

The API still fetches structures live for real work. This copy is a static asset
for one page, not a second source of truth: nothing in the application reads it.

### Numbering — read this before touching the viewer

The file numbers residues **1–212, full length**. The seeded project's canonical
scheme is the **mature protein**, which runs 31 lower because the signal peptide
is residues 1–31. The catalytic triad is therefore:

| Mature (canonical) | This file (`auth_seq_id`) | Residue |
| --- | --- | --- |
| Ser77 | 108 | SER |
| Asp133 | 164 | ASP |
| His156 | 187 | HIS |

Both numbers are shown in the interface, deliberately. Confirmed two ways on
2026-09-02: by translating the vendored FASTA (index 108 is S, sitting in the
`AHSMG` nucleophile elbow; 164 is D; 187 is H), and by reading the `CA` records
of this file directly.
