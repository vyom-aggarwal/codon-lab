import { expect, test, type Page } from '@playwright/test'

/**
 * Smoke flow 2 of 2: **any score traces to a model version in two clicks**,
 * counted with trusted events.
 *
 * `BRIEF.md` §2.2 and §9's Phase 5 exit gate. There is already a jsdom version
 * of this (`test/two-clicks.test.tsx`) and it does real work — it counts clicks
 * rather than asserting the drawer exists, which is the correction `HANDOFF.md`
 * §7 records the owner making. But every click it counts is synthetic, and
 * jsdom has no layout: an element covered by another, sized to zero, or placed
 * off-screen is still "clickable" there.
 *
 * This counts `event.isTrusted` clicks in a browser that lays the page out and
 * refuses to click what a user could not reach. That is the only difference,
 * and it is the whole reason this flow is one of the two.
 */

/** Count only clicks the browser itself generated. */
async function countTrustedClicks(page: Page) {
  await page.evaluate(() => {
    ;(window as unknown as { __clicks: number }).__clicks = 0
    document.addEventListener(
      'click',
      (event) => {
        if (event.isTrusted) (window as unknown as { __clicks: number }).__clicks += 1
      },
      true,
    )
  })
  return () => page.evaluate(() => (window as unknown as { __clicks: number }).__clicks)
}

/** A finished run over a real target, created through the API. */
async function seedRun(request: import('@playwright/test').APIRequestContext) {
  const stamp = Date.now()
  const project = await request.post('http://localhost:8000/projects', {
    data: { name: `E2E two clicks ${stamp}`, organism: 'Bacillus subtilis' },
  })
  const projectId = (await project.json()).id

  const target = await request.post(`http://localhost:8000/projects/${projectId}/targets`, {
    data: { source: 'uniprot', accession: 'P37957' },
  })
  const targetBody = await target.json()
  const scheme = targetBody.numbering_schemes.find(
    (s: { kind: string }) => s.kind === 'sequence',
  )
  await request.post(`http://localhost:8000/targets/${targetBody.id}/numbering/confirm`, {
    data: { scheme_id: scheme.id },
  })

  const goal = await request.post(`http://localhost:8000/targets/${targetBody.id}/goals`, {
    data: {
      text: 'make this enzyme survive 65 C without killing activity, one 96-well plate in E. coli, measured by DSF',
    },
  })
  const goalId = (await goal.json()).id
  await request.post(`http://localhost:8000/goals/${goalId}/confirm`, { data: {} })

  const started = await request.post(`http://localhost:8000/goals/${goalId}/runs`, { data: {} })
  expect(started.ok(), 'run start').toBeTruthy()
  const runId = (await started.json()).id

  // The worker executes this in another container. Poll the API rather than the
  // page, so a slow run is a slow test and not a flaky assertion.
  const deadline = Date.now() + 100_000
  for (;;) {
    const status = await request.get(`http://localhost:8000/runs/${runId}`)
    const body = await status.json()
    if (body.is_terminal) {
      expect(body.status, `run finished as ${body.status}: ${body.error ?? ''}`).toBe('succeeded')
      return runId as string
    }
    if (Date.now() > deadline) throw new Error('the run did not finish in time')
    await new Promise((resolve) => setTimeout(resolve, 1500))
  }
}

test('a score reaches its model version and weights hash in exactly two clicks', async ({
  page,
  request,
}) => {
  const runId = await seedRun(request)
  await page.goto(`/runs/${runId}/workbench`)

  const firstRow = page.locator('tr[data-code]').first()
  await expect(firstRow).toBeVisible({ timeout: 30_000 })

  const clicks = await countTrustedClicks(page)

  // Zero clicks: nothing about a model version is on screen.
  await expect(page.getByRole('heading', { name: 'Provenance' })).toHaveCount(0)
  expect(await clicks()).toBe(0)

  // Click one: the row. Opens the inspector, which shows the score — but the
  // weights hash is still not reachable.
  await firstRow.click()
  expect(await clicks()).toBe(1)
  const trace = page.getByRole('button', { name: 'Trace' }).first()
  await expect(trace).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Provenance' })).toHaveCount(0)

  // Click two: Trace. Everything a PI needs is now on screen.
  await trace.click()
  expect(await clicks(), 'the trace must cost exactly two clicks').toBe(2)

  await expect(page.getByRole('heading', { name: 'Provenance' })).toBeVisible()

  // The *weights* hash specifically. The drawer carries three hashes — weights,
  // the stage's input hash and the run's — so matching "any sha256" would pass
  // even if the one thing §2.2 names had gone missing.
  // The `dd` that is the weights row's own sibling. Matching an ancestor div
  // and taking its first `dd` returned the model *id* instead, which would have
  // passed a weaker pattern — the locator has to be as specific as the claim.
  const weights = page
    .locator('dt', { hasText: /^weights$/ })
    .locator('xpath=following-sibling::dd[1]')
  await expect(weights).toHaveText(/^sha256:[0-9a-f]{64}$/)

  // And the model version and id, which are the rest of the §2.2 claim.
  await expect(page.locator('dt', { hasText: /^version$/ })).toBeVisible()
  await expect(page.locator('dt', { hasText: /^id$/ })).toBeVisible()
})

test('every score offers its own trace, not just the first', async ({ page, request }) => {
  // The word doing the work in the gate is "any". HANDOFF.md §8 records a
  // mutation that pointed every Trace control at the *first* score and passed
  // six tests. With one predictor configured there is one score per row, so
  // what is checked here is that each row reaches its own — a trace opened from
  // row two must name row two's variant.
  const runId = await seedRun(request)
  await page.goto(`/runs/${runId}/workbench`)

  const rows = page.locator('tr[data-code]')
  await expect(rows.first()).toBeVisible({ timeout: 30_000 })

  const secondRow = rows.nth(1)
  const secondCode = await secondRow.getAttribute('data-code')
  expect(secondCode, 'the second row must have a mutation code').toBeTruthy()

  await secondRow.click()
  await page.getByRole('button', { name: 'Trace' }).first().click()

  await expect(page.getByRole('heading', { name: 'Provenance' })).toBeVisible()
  // The drawer is about the variant that was clicked, not a different one.
  await expect(page.getByText(secondCode!, { exact: false }).first()).toBeVisible()
})
