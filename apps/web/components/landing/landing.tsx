import { ArrowRight } from 'lucide-react'
import type { Route } from 'next'
import Link from 'next/link'

import { CodonMark } from '@/components/brand/codon-mark'

import { HeroStructure } from './hero-structure'
import { SequenceBand } from './sequence-band'

/**
 * The landing page.
 *
 * `BRIEF.md` §4 bans a marketing hero **inside the app**, and this is not inside
 * it: `Shell` renders this route with no left rail, no demo banner and nothing
 * implying the reader is in a project. Everything else the brief bans still
 * applies and is respected — no gradients, no glassmorphism, no card shadows, no
 * three-column feature-card grid, no pill buttons, no emoji, one accent colour.
 * `tokens.test.ts` enforces most of it mechanically, scanning this directory
 * like any other.
 *
 * **The dark sections are the design system, not an exception to it.**
 * `DESIGN.md` §1.2 has defined real dark values since Phase 1 and nothing had
 * ever reached them. Scoping `data-theme="dark"` to a section re-points every
 * token underneath it, so the hero is built from exactly the same utilities as
 * the light sections and cannot drift from the palette. The 3D viewer resolves
 * its colours from its own container for the same reason.
 *
 * **Every number on this page is one this build measured**, with the conditions
 * it was measured under. A page whose product claim is "no fabricated numbers"
 * cannot round, dramatise or invent one — including the unflattering ones. There
 * are no customer logos, no testimonials, and no metric that was not produced by
 * running the thing.
 */

const REPO = 'https://github.com/vyom-aggarwal/codon-lab'

export function Landing() {
  return (
    <div className="bg-canvas text-text min-h-dvh">
      <Hero />
      <SequenceBand />
      <Invariants />
      <ValidationLoop />
      <Pipeline />
      <Refusals />
      <LandingFooter />
    </div>
  )
}

/* -------------------------------------------------------------------------- */

function Section({
  id,
  label,
  title,
  children,
}: {
  id?: string
  label: string
  title: string
  children: React.ReactNode
}) {
  return (
    <section id={id} className="border-border border-b">
      <div className="mx-auto max-w-5xl px-6 py-20 md:px-10 md:py-24">
        <p className="text-11 text-accent uppercase">{label}</p>
        <h2 className="text-24 md:text-32 text-text mt-3 max-w-2xl">{title}</h2>
        <div className="mt-12">{children}</div>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */

function Hero() {
  return (
    <div data-theme="dark" className="bg-canvas text-text">
      <header className="border-border border-b">
        <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-6 md:px-10">
          <span className="inline-flex items-center gap-2">
            <CodonMark className="text-accent size-5" />
            <span className="text-15 font-strong text-text">Codon Lab</span>
          </span>
          <nav aria-label="Landing" className="flex items-center gap-5">
            <a
              href={REPO}
              className="text-12 text-text-muted hover:text-text hidden sm:inline"
              target="_blank"
              rel="noreferrer"
            >
              Source
            </a>
            <Link
              href={'/projects' as Route}
              className="bg-text text-canvas rounded-control h-control-sm text-12 inline-flex items-center gap-1.5 px-2.5 font-medium hover:opacity-90"
            >
              Open the workbench
              <ArrowRight aria-hidden="true" className="size-4" strokeWidth={1.5} />
            </Link>
          </nav>
        </div>
      </header>

      <section className="mx-auto max-w-5xl px-6 py-20 md:px-10 md:py-24">
        <div className="grid items-center gap-14 lg:grid-cols-2 lg:gap-16">
          <div>
            <p className="text-11 text-accent uppercase">Protein engineering copilot</p>

            <h1 className="text-32 sm:text-44 md:text-56 text-text mt-5">
              Every number traces back to the model that made it.
            </h1>

            <p className="text-15 text-text-muted mt-6 max-w-xl">
              Codon Lab turns a plain-language engineering goal into a ranked list of specific
              point mutations. Each one traces in two clicks to a model, a version and a weights
              hash. Each one is checked against what the bench actually measured.
            </p>

            <div className="mt-9 flex flex-wrap items-center gap-3">
              <Link
                href={'/projects' as Route}
                className="bg-text text-canvas rounded-control h-control text-13 inline-flex items-center gap-1.5 px-4 font-medium hover:opacity-90"
              >
                Open the workbench
                <ArrowRight aria-hidden="true" className="size-4" strokeWidth={1.5} />
              </Link>
              <Link
                href={'/#validation' as Route}
                className="border-border-strong text-text hover:bg-surface rounded-control h-control text-13 inline-flex items-center border px-4 font-medium"
              >
                See what it refuses to do
              </Link>
            </div>
          </div>

          {/* Borderless on the dark ground, so the model reads as an object in
              the page rather than a screenshot pasted into it. */}
          <HeroStructure containerClassName="bg-transparent" />
        </div>

        <dl className="border-border mt-20 grid grid-cols-1 gap-10 border-t pt-10 sm:grid-cols-3">
          <Stat value="263" label="automated gate checks, run against a live stack" />
          <Stat value="2,172" label="measured bench values seeded, from a published scan" />
          <Stat value="0" label="numbers fabricated outside the badged demo provider" />
        </dl>
      </section>
    </div>
  )
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div>
      <dt className="text-32 text-text font-mono tabular-nums">{value}</dt>
      <dd className="text-12 text-text-muted mt-2 max-w-xs">{label}</dd>
    </div>
  )
}

/* -------------------------------------------------------------------------- */

const INVARIANTS = [
  {
    index: '01',
    title: 'Parse, then confirm — never silently interpret',
    body: 'You type a goal in English. The app parses it into an explicit objective and shows that parse back as editable chips: objective, constraints, budget, expression host, assay. Nothing runs until you confirm it. A tool that guesses what "more thermostable" means and quietly proceeds is a tool you abandon after the first surprising result.',
  },
  {
    index: '02',
    title: 'Every number is traceable',
    body: 'Any score on any screen traces in two clicks to the model, version and weights hash that produced it, the inputs it saw, the run it belonged to and the time it ran. Provenance is a first-class table, not a log file, and the database refuses to store a score without both a model version and a run.',
  },
  {
    index: '03',
    title: 'Never fabricate a scientific number',
    body: 'A model that cannot run reports why. The cell reads an em dash with the reason on hover — never an imputed value, never an estimated placeholder. The one provider allowed to invent numbers badges every one of them, watermarks exports, and refuses to generate primers.',
  },
]

function Invariants() {
  return (
    <Section label="The three invariants" title="Built for someone skeptical, busy, and correct.">
      <ul className="border-border border-t">
        {INVARIANTS.map((item) => (
          <li
            key={item.index}
            className="border-border flex flex-col gap-3 border-b py-10 md:flex-row md:gap-10"
          >
            <span className="text-24 text-accent w-12 shrink-0 font-mono tabular-nums">
              {item.index}
            </span>
            <div className="max-w-2xl">
              <h3 className="text-18 text-text font-strong">{item.title}</h3>
              <p className="text-13 text-text-muted mt-3">{item.body}</p>
            </div>
          </li>
        ))}
      </ul>
    </Section>
  )
}

/* -------------------------------------------------------------------------- */

function ValidationLoop() {
  return (
    <Section
      id="validation"
      label="The validation loop"
      title="The scorecard tells you which predictor to trust, including when the answer is none of them."
    >
      <div className="grid gap-12 lg:grid-cols-3">
        <div className="max-w-2xl space-y-5 lg:col-span-2">
          <p className="text-13 text-text-muted">
            Upload measured results from the bench. The app joins them to the variants it ranked,
            then reports how each predictor actually did — per model version, accumulating across
            every project in the lab.
          </p>
          <p className="text-13 text-text-muted">
            A rank statistic alone is not enough and the scorecard refuses to pretend otherwise. A
            predictor that reads a constant 2 kcal/mol high scores a perfect Spearman and a
            perfect precision@10 while being useless for the decision you are actually making,
            which is absolute. So the error and bias figures sit beside the rank figures, always,
            and where they cannot be computed the card says why instead of leaving a gap.
          </p>
        </div>

        <figure className="border-border bg-surface rounded-panel m-0 border p-5">
          <figcaption className="text-11 text-accent uppercase">Measured on this build</figcaption>
          <dl className="mt-4 space-y-4">
            <div>
              <dt className="text-12 text-text-muted">ESM-2 650M</dt>
              <dd className="text-32 text-text font-mono tabular-nums">ρ 0.30</dd>
            </div>
            <div>
              <dt className="text-12 text-text-muted">Synthetic control</dt>
              <dd className="text-24 text-text-muted font-mono tabular-nums">ρ −0.06</dd>
            </div>
            <div className="border-border border-t pt-4">
              <dt className="text-12 text-text-muted">MAE, mean signed error</dt>
              <dd className="text-24 text-text-muted font-mono tabular-nums">—</dd>
            </div>
          </dl>
          <p className="text-11 text-text-muted mt-4">
            Spearman ρ against 2,172 measured T50 values for <i>B. subtilis</i> lipase A (Nutschel
            et al. 2020, via ProteinGym), CPU only. No error or bias figure is reported for this
            pair: a log-likelihood ratio and a temperature in °C are not the same quantity, so the
            scorecard shows an em dash and states the reason rather than converting between them.
          </p>
        </figure>
      </div>
    </Section>
  )
}

/* -------------------------------------------------------------------------- */

const STAGES = [
  [
    'Retrieve structure',
    'From the PDB, AlphaFold DB, or a file you upload. Recorded by content hash, and labelled predicted or experimental.',
  ],
  [
    'Build MSA',
    'No alignment provider is configured in this build, so the stage records that it skipped and the reason why. The conservation column stays empty rather than being filled in with a guess — the same rule every other unavailable number follows.',
  ],
  [
    'Score with each predictor',
    'ESM-2 650M masked marginals and a ThermoMPNN ΔΔG adapter. Every substitution at every nameable position — no pre-filter, because narrowing early is a scientific choice made without asking you.',
  ],
  [
    'Aggregate',
    'Ranks are combined, never raw scores: a ΔΔG in kcal/mol and a log-likelihood ratio are not on the same scale. Disagreement between predictors is reported beside the consensus, never averaged into it.',
  ],
  [
    'Filter by constraints',
    'Catalytic residues, ligand contacts, disulfides, do-not-touch regions. Every filtered variant stays retrievable with the constraint that removed it.',
  ],
  ['Rank', 'Narrowed only by the budget you stated. An unstated budget truncates nothing.'],
]

function Pipeline() {
  return (
    <Section
      label="What a run does"
      title="Six stages, each showing its model, version, input hash and runtime — including the one that skips."
    >
      <ol className="border-border grid border-t md:grid-cols-2">
        {STAGES.map(([title, body], index) => (
          <li key={title} className="border-border border-b py-8 md:pr-10">
            <span className="text-12 text-accent font-mono tabular-nums">
              {String(index + 1).padStart(2, '0')}
            </span>
            <h3 className="text-15 text-text font-strong mt-2">{title}</h3>
            <p className="text-13 text-text-muted mt-2 max-w-md">{body}</p>
          </li>
        ))}
      </ol>
    </Section>
  )
}

/* -------------------------------------------------------------------------- */

const REFUSALS = [
  [
    'No run starts from a parse you have not confirmed',
    'Enforced in the service layer rather than the interface, because the job queue is a second caller that would otherwise route around it.',
  ],
  [
    'Primers are refused while no target carries a coding sequence',
    'A primer anneals to the construct on your bench. Back-translating the protein would produce a plausible sequence that is not your plasmid, and primers that do not anneal cost a synthesis order and a week.',
  ],
  [
    'A mutation code is never written in the wrong numbering scheme',
    'Sequence, PDB author and construct numbering are reconciled explicitly, by you, before any code is written. Where reconciliation is ambiguous the app stops and says so rather than picking.',
  ],
  [
    'An absolute error across unlike units is not computed',
    'A predicted ΔΔG in kcal/mol and a measured T50 in °C cannot be subtracted, and no conversion factor is invented to make them comparable.',
  ],
]

function Refusals() {
  return (
    <div data-theme="dark" className="bg-canvas text-text">
      <section className="mx-auto max-w-5xl px-6 py-20 md:px-10 md:py-24">
        <p className="text-11 text-accent uppercase">What it refuses to do</p>
        <h2 className="text-24 md:text-32 text-text mt-3 max-w-2xl">
          The refusals are the product. Each one states its reason and what would clear it.
        </h2>

        <ul className="border-border mt-12 grid border-t md:grid-cols-2">
          {REFUSALS.map(([title, body]) => (
            <li key={title} className="border-border border-b py-8 md:pr-10">
              <h3 className="text-15 text-text font-strong">{title}</h3>
              <p className="text-13 text-text-muted mt-2 max-w-md">{body}</p>
            </li>
          ))}
        </ul>

        <div className="mt-12 flex flex-wrap items-center gap-3">
          <Link
            href={'/projects' as Route}
            className="bg-text text-canvas rounded-control h-control text-13 inline-flex items-center gap-1.5 px-4 font-medium hover:opacity-90"
          >
            Open the workbench
            <ArrowRight aria-hidden="true" className="size-4" strokeWidth={1.5} />
          </Link>
          <a
            href={REPO}
            target="_blank"
            rel="noreferrer"
            className="border-border-strong text-text hover:bg-surface rounded-control h-control text-13 inline-flex items-center border px-4 font-medium"
          >
            Read the source
          </a>
        </div>
      </section>
    </div>
  )
}

/* -------------------------------------------------------------------------- */

function LandingFooter() {
  return (
    <div data-theme="dark" className="bg-canvas text-text">
      <footer className="border-border border-t">
        <div className="mx-auto max-w-5xl px-6 py-12 md:px-10">
          <div className="flex flex-wrap items-start justify-between gap-8">
            <div>
              <span className="inline-flex items-center gap-2">
                <CodonMark className="text-accent" />
                <span className="text-13 font-strong text-text">Codon Lab</span>
              </span>
              <p className="text-12 text-text-muted mt-3 max-w-md">
                Runs locally under Docker: Postgres, Redis, a FastAPI service, an RQ worker and
                Next.js. Nothing is deployed and no data leaves the machine.
              </p>
            </div>
            <nav aria-label="Footer" className="flex flex-col gap-2">
              <Link href={'/projects' as Route} className="text-12 text-text-muted hover:text-text">
                Projects
              </Link>
              <Link
                href={'/scorecard' as Route}
                className="text-12 text-text-muted hover:text-text"
              >
                Scorecard
              </Link>
              <a
                href={REPO}
                className="text-12 text-text-muted hover:text-text"
                target="_blank"
                rel="noreferrer"
              >
                Source
              </a>
            </nav>
          </div>
          <p className="text-11 text-text-faint mt-10">
            All nine build phases complete. The wet-lab handoff is blocked on template DNA and
            says so where it would otherwise appear.
          </p>
        </div>
      </footer>
    </div>
  )
}
