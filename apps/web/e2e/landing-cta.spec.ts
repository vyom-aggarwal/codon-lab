import { expect, test } from '@playwright/test'

/**
 * Smoke flow 3 of 3: **the landing page's call to action actually works, and
 * the 3D viewer does not eat the main thread.**
 *
 * This exists because it did not. The hero's Mol* viewer ran a perpetual
 * `trackball.animate` spin, which redraws the scene every frame; the scene cost
 * ~65 ms a frame even at 358x358. That starved the Next router badly enough
 * that clicking "Open the workbench" did nothing at all — no error, no console
 * message, the URL simply never changed — and assigning `window.location` could
 * not complete either. The page looked perfect and was unusable.
 *
 * Nothing in the suite could see it. `verify_gates.py` reads served HTML, which
 * was correct. The jsdom tests have no WebGL and no frame budget. The other two
 * flows never open `/`. A defect that only exists once a GPU has been running
 * for a few seconds needs a real browser and a wait, which is what this is.
 *
 * The guard is deliberately behavioural rather than a check that the spin is
 * off: any future change that makes a frame expensive again — a heavier
 * representation, occlusion back on, an animation — fails here, which is the
 * property worth keeping.
 */

/** Long enough for the structure to download, build and start rendering. */
const VIEWER_SETTLES = 10_000

test('the landing page call to action still navigates once the viewer is running', async ({
  page,
}) => {
  await page.goto('/', { waitUntil: 'domcontentloaded' })

  // Wait for the viewer to be live. Clicking before Mol* boots passed even when
  // the bug was present, so the wait is the test.
  await expect(page.locator('canvas')).toBeVisible({ timeout: VIEWER_SETTLES })
  await page.waitForTimeout(VIEWER_SETTLES)

  // The model is actually on screen — otherwise this passes by rendering
  // nothing, which is the cheap way to make the assertion below true.
  const canvas = await page.locator('canvas').first().evaluate((el) => ({
    width: (el as HTMLCanvasElement).width,
    height: (el as HTMLCanvasElement).height,
  }))
  expect(canvas.width, 'the viewer must have a real drawing buffer').toBeGreaterThan(64)
  expect(canvas.height).toBeGreaterThan(64)

  await page.getByRole('link', { name: 'Open the workbench' }).first().click()
  await expect(page).toHaveURL(/\/projects$/, { timeout: 15_000 })
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
})

test('a frame stays cheap enough for the page to stay responsive', async ({ page }) => {
  // The direct measurement of the cause, kept separate so a failure says which
  // of the two things broke.
  //
  // The threshold is measured, not chosen. `requestAnimationFrame` is capped at
  // the display's refresh, so a *healthy* idle page cannot read below ~16.7 ms
  // however fast the machine is — five runs here gave 15.4, 16.0, 16.4, 16.5,
  // 16.6, which is vsync and nothing else. The spin restored as a mutation read
  // 42.5 ms, i.e. two frames in three were being missed.
  //
  // 25 ms sits between those: it means "dropping roughly a third of frames",
  // which is a statement about the page rather than about this machine. A
  // faster GPU cannot slip under it, and a slower one still reads vsync while
  // the page is idle.
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  await expect(page.locator('canvas')).toBeVisible({ timeout: VIEWER_SETTLES })
  await page.waitForTimeout(VIEWER_SETTLES)

  const perFrame = await page.evaluate(
    () =>
      new Promise<number>((resolve) => {
        const started = performance.now()
        let frames = 0
        const tick = () => {
          frames += 1
          if (frames >= 10) resolve((performance.now() - started) / frames)
          else requestAnimationFrame(tick)
        }
        requestAnimationFrame(tick)
      }),
  )

  expect(perFrame, `a frame cost ${perFrame.toFixed(1)}ms`).toBeLessThan(25)
})
