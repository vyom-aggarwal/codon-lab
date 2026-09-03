import { expect, test } from '@playwright/test'

/**
 * Smoke flow 1 of 2: **no run starts from an unconfirmed parse.**
 *
 * This is `BRIEF.md` §2.1, the product's first invariant, and §9's Phase 3 exit
 * gate. It is enforced in `services/goals.require_confirmed` — in the service
 * layer, because the job queue is a second caller that would otherwise route
 * around a check placed in a route.
 *
 * It is already asserted over HTTP in `scripts/verify_gates.py`. What that
 * cannot see is the **interface**: whether the button a user actually reaches
 * for is disabled before confirmation, whether the reason is on screen, and
 * whether confirming enables it. A product whose API refuses correctly while
 * its UI invites the click is still a product that wastes the user's time and
 * teaches them the affordances lie.
 *
 * Chosen as one of the two flows because breaking it silently is the single
 * most expensive UI regression available: the run would start, the numbers
 * would look normal, and the objective they answer would be one nobody agreed
 * to.
 */

/** Everything this flow needs, created through the API so the UI is the thing under test. */
async function seedTarget(request: import('@playwright/test').APIRequestContext) {
  const stamp = Date.now()
  const project = await request.post('http://localhost:8000/projects', {
    data: { name: `E2E confirmation ${stamp}`, organism: 'Bacillus subtilis' },
  })
  expect(project.ok(), 'project create').toBeTruthy()
  const projectId = (await project.json()).id

  const target = await request.post(`http://localhost:8000/projects/${projectId}/targets`, {
    data: { source: 'uniprot', accession: 'P37957' },
  })
  expect(target.ok(), 'target create').toBeTruthy()
  const body = await target.json()

  // Confirm a canonical numbering scheme: until one exists the target is not
  // designable and the goal screen would refuse for a different reason than the
  // one this flow is about.
  const sequenceScheme = body.numbering_schemes.find(
    (scheme: { kind: string }) => scheme.kind === 'sequence',
  )
  const confirmed = await request.post(
    `http://localhost:8000/targets/${body.id}/numbering/confirm`,
    { data: { scheme_id: sequenceScheme.id } },
  )
  expect(confirmed.ok(), 'numbering confirm').toBeTruthy()

  return body.id as string
}

test('a design run cannot be started until the parse is confirmed', async ({ page, request }) => {
  const targetId = await seedTarget(request)
  await page.goto(`/targets/${targetId}/goal`)

  // --- before any parse -------------------------------------------------
  const goalBox = page.getByLabel('Engineering goal')
  await expect(goalBox).toBeVisible()

  await goalBox.fill(
    'make this enzyme survive 65 C without killing activity, one 96-well plate in E. coli, measured by DSF',
  )
  await page.getByRole('button', { name: 'Parse goal' }).click()

  // --- parsed, not confirmed -------------------------------------------
  const confirm = page.getByRole('button', { name: 'Confirm objective' })
  await expect(confirm).toBeVisible({ timeout: 30_000 })

  const startRun = page.getByRole('button', { name: 'Start design run' })
  await expect(startRun, 'the run button must be disabled before confirmation').toBeDisabled()

  // The refusal is on screen, not only in the disabled attribute. A control
  // that is dead with no stated reason is indistinguishable from a bug.
  await expect(page.getByText('No run can start from an unconfirmed objective.')).toBeVisible()

  // The parse is shown back before it is agreed to — §2.1's "shows that parse
  // back as editable chips". The chips render read-only until "Edit chips" is
  // pressed, so this asserts what the user is actually looking at when they
  // decide whether to confirm.
  await expect(page.getByRole('heading', { name: 'Parsed objective' })).toBeVisible()
  await expect(page.getByText('Not confirmed')).toBeVisible()
  await expect(page.getByText('Objective', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Edit chips' })).toBeVisible()

  // --- confirming enables it -------------------------------------------
  await confirm.click()
  await expect(page.getByRole('button', { name: 'Confirmed' })).toBeVisible({ timeout: 30_000 })
  await expect(startRun, 'confirming must enable the run').toBeEnabled()
  await expect(
    page.getByText('Scores every single substitution, then ranks what the constraints allow.'),
  ).toBeVisible()
})

test('the API refuses a run from an unconfirmed goal even if the UI is bypassed', async ({
  request,
}) => {
  // The button being disabled is a courtesy. The guarantee is in the service
  // layer, and this asserts it from outside the browser entirely — because a
  // future screen, or the queue, could call the same endpoint.
  const targetId = await seedTarget(request)

  const goal = await request.post(`http://localhost:8000/targets/${targetId}/goals`, {
    data: { text: 'make this enzyme survive 65 C, one plate in E. coli, measured by DSF' },
  })
  expect(goal.ok()).toBeTruthy()
  const goalId = (await goal.json()).id

  const started = await request.post(`http://localhost:8000/goals/${goalId}/runs`, { data: {} })
  // 400, not 409 — the status verify_gates.py has asserted since Phase 3.
  // Matching the established contract rather than guessing at a nicer code.
  expect(started.status(), 'starting from an unconfirmed goal must be refused').toBe(400)

  const detail = (await started.json()).detail
  expect(JSON.stringify(detail).toLowerCase()).toContain('confirm')
})
