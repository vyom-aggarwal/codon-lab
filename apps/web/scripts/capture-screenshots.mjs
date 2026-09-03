/**
 * Capture the README's screenshots from the running application.
 *
 *     docker compose up -d
 *     pnpm --filter @codonlab/web screenshots
 *
 * `BRIEF.md` §9 asks for "accurate screenshots". The word doing the work is
 * accurate, and the way screenshots stop being accurate is that they are taken
 * by hand once and never again. This script takes them from the live stack, at
 * a fixed viewport, into a fixed set of paths — so regenerating them is one
 * command and a stale one is a diff rather than a discovery.
 *
 * It picks its subjects out of the database rather than hard-coding ids: a
 * screenshot script that only works on the machine it was written on is a
 * screenshot script nobody re-runs.
 *
 * What it does **not** do is dress the app up. The demo bar is left where it
 * falls, because the seeded providers are synthetic and a screenshot with the
 * bar cropped out would be exactly the fabrication the bar exists to prevent.
 */

import { mkdir } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { chromium } from '@playwright/test'

const HERE = dirname(fileURLToPath(import.meta.url))
const OUT = join(HERE, '..', '..', '..', 'docs', 'screenshots')
const WEB = process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:3000'
const API = process.env.CODONLAB_API_URL ?? 'http://localhost:8000'

/** A run that finished, and the target it belongs to. */
async function pickSubjects() {
  const projects = await fetch(`${API}/projects`).then((r) => r.json())
  for (const project of projects) {
    const detail = await fetch(`${API}/projects/${project.id}`).then((r) => r.json())
    for (const target of detail.targets ?? []) {
      const runs = await fetch(`${API}/targets/${target.id}/runs`).then((r) => r.json())
      const finished = runs.find((run) => run.status === 'succeeded')
      if (finished) return { projectId: project.id, targetId: target.id, runId: finished.id }
    }
  }
  throw new Error('no succeeded run found — run scripts/verify_gates.py first')
}

const SHOTS = [
  { name: 'landing', path: () => '/', wait: 6000, full: true },
  { name: 'projects', path: () => '/projects' },
  { name: 'run-view', path: (s) => `/runs/${s.runId}` },
  { name: 'workbench', path: (s) => `/runs/${s.runId}/workbench`, wait: 4000 },
  { name: 'scorecard', path: (s) => `/targets/${s.targetId}/scorecard`, wait: 3000 },
]

const subjects = await pickSubjects()
await mkdir(OUT, { recursive: true })

const browser = await chromium.launch()

for (const shot of SHOTS) {
  const url = `${WEB}${shot.path(subjects)}`
  // A fresh page per shot. Reusing one page hangs the *next* navigation after
  // the landing page: `page.goto` is a hard navigation, so React never unmounts
  // and Mol*'s WebGL context and spin loop are still running as the document is
  // torn down. The product path is unaffected — an in-app `Link` unmounts the
  // component and the effect cleanup disposes the plugin — but a screenshot
  // script has no reason to carry state between two unrelated screens anyway.
  const page = await browser.newPage({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
  })
  // 'load', not 'networkidle': the dev server holds an HMR websocket open, so
  // the network never goes idle and every capture times out. The explicit wait
  // below is what actually settles the page. 120s rather than the 30s default,
  // because the dev server compiles each route the first time it is requested.
  await page.goto(url, { waitUntil: 'load', timeout: 120_000 })
  // The 3D viewer and the virtualised table both settle after the network does.
  await page.waitForTimeout(shot.wait ?? 2000)
  const file = join(OUT, `${shot.name}.png`)
  await page.screenshot({ path: file, fullPage: shot.full ?? false })
  await page.close()
  console.log(`${shot.name.padEnd(12)} ${url}`)
}

await browser.close()
console.log(`\n${SHOTS.length} screenshots written to docs/screenshots/`)
