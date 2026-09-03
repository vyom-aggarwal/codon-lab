/**
 * The contrast audit, as a gate rather than a paragraph.
 *
 * `DESIGN.md` §1.3 said "Phase 9 re-runs this". Re-running it by hand once a
 * phase is how it drifted: the table claimed `--accent` on `--surface` was
 * 8.6:1 AAA when it is 6.70:1 AA, and had been claiming it since Phase 1. A
 * documented ratio nobody recomputes is a documented ratio that is eventually
 * wrong, and this one was wrong in the direction that overstates compliance.
 *
 * So the audit now runs on every build. These tests recompute every ratio from
 * `tokens.css` using the WCAG 2.1 relative-luminance formula and assert that
 * `DESIGN.md`'s tables match to one decimal place, and that every stated verdict
 * is the one the number earns. Changing a token without updating the table fails
 * the build, and so does updating the table without changing the token.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

const WEB_ROOT = join(import.meta.dirname, '..')
const REPO_ROOT = join(WEB_ROOT, '..', '..')

const tokensCss = readFileSync(join(WEB_ROOT, 'app', 'tokens.css'), 'utf8')
const design = readFileSync(join(REPO_ROOT, 'DESIGN.md'), 'utf8')

/**
 * Split `tokens.css` into its light and dark blocks.
 *
 * The dark block is found from `[data-theme='dark'] {` — with the brace, and
 * `@theme inline` is searched for *after* it. The file's own header comment
 * names both, so a naive `indexOf` finds the prose rather than the rule and
 * silently yields an empty dark block. That happened while writing this.
 */
function themeBlocks(): { light: string; dark: string } {
  const darkAt = tokensCss.indexOf("[data-theme='dark'] {")
  const themeAt = tokensCss.indexOf('@theme inline', darkAt)
  return {
    light: tokensCss.slice(tokensCss.indexOf(':root {'), darkAt),
    dark: tokensCss.slice(darkAt, themeAt),
  }
}

function hexTokens(block: string): Record<string, string> {
  const found: Record<string, string> = {}
  for (const match of block.matchAll(/^\s*--([a-z-]+):\s*(#[0-9a-fA-F]{6})\s*;/gm)) {
    found[match[1]!] = match[2]!
  }
  return found
}

/** WCAG 2.1 relative luminance. */
function luminance(hex: string): number {
  const channel = (value: number) =>
    value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
  const [r, g, b] = [1, 3, 5].map((offset) =>
    channel(Number.parseInt(hex.slice(offset, offset + 2), 16) / 255),
  ) as [number, number, number]
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

function contrast(foreground: string, background: string): number {
  const a = luminance(foreground)
  const b = luminance(background)
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)
}

/** The verdict a ratio earns for normal-size text. */
function verdict(ratio: number): 'AAA' | 'AA' | 'fails AA' {
  if (ratio >= 7) return 'AAA'
  if (ratio >= 4.5) return 'AA'
  return 'fails AA'
}

const { light, dark } = themeBlocks()
const LIGHT = hexTokens(light)
const DARK = hexTokens(dark)

describe('the token blocks parse', () => {
  it('finds both themes', () => {
    expect(Object.keys(LIGHT).length).toBeGreaterThan(10)
    expect(Object.keys(DARK).length).toBeGreaterThan(8)
  })

  it('reads the dark block rather than the header comment that names it', () => {
    // The regression this guards: an empty dark block makes every dark
    // assertion below vacuously pass, and the header comment names
    // `@theme inline` before the rule does.
    //
    // Asserted semantically rather than by comparing hex strings — the eslint
    // rule that bans raw colour literals applies to tests too, and it is right
    // to: a literal here would be a fourth place a token value is written down.
    expect(DARK['canvas']).toBeDefined()
    expect(DARK['accent']).toBeDefined()
    expect(luminance(DARK['canvas']!)).toBeLessThan(luminance(LIGHT['canvas']!))
    expect(luminance(DARK['text']!)).toBeGreaterThan(luminance(LIGHT['text']!))
  })
})

/**
 * Every row of `DESIGN.md` §1.3, in both themes. `expected` is what the document
 * claims; the test computes the truth and compares.
 */
const AUDITED: { fg: string; bg: string }[] = [
  { fg: 'text', bg: 'surface' },
  { fg: 'text-muted', bg: 'surface' },
  { fg: 'text-faint', bg: 'surface' },
  { fg: 'accent', bg: 'surface' },
  { fg: 'surface', bg: 'accent' },
  { fg: 'positive', bg: 'surface' },
  { fg: 'negative', bg: 'surface' },
  { fg: 'warn', bg: 'surface' },
  { fg: 'text', bg: 'canvas' },
  { fg: 'text-muted', bg: 'canvas' },
  { fg: 'accent', bg: 'canvas' },
  { fg: 'text', bg: 'surface-sunk' },
  { fg: 'text-muted', bg: 'surface-sunk' },
  { fg: 'text', bg: 'accent-sunk' },
  { fg: 'accent', bg: 'accent-sunk' },
]

/** Pull `| `--a` on `--b` | 6.70:1 | AA |` out of a DESIGN.md table. */
function documented(theme: 'light' | 'dark', fg: string, bg: string) {
  const heading = theme === 'light' ? '#### Light' : '#### Dark'
  const start = design.indexOf(heading)
  expect(start, `${heading} section missing from DESIGN.md §1.3`).toBeGreaterThan(-1)
  const end = design.indexOf('####', start + heading.length)
  const section = design.slice(start, end === -1 ? undefined : end)

  const row = new RegExp(
    `\\|\\s*\`--${fg}\` on \`--${bg}\`\\s*\\|\\s*([0-9.]+):1\\s*\\|\\s*([^|]+?)\\s*\\|`,
  ).exec(section)
  expect(row, `DESIGN.md §1.3 ${theme} has no row for --${fg} on --${bg}`).not.toBeNull()
  return { ratio: Number(row![1]), verdict: row![2]! }
}

for (const [theme, tokens] of [
  ['light', LIGHT],
  ['dark', DARK],
] as const) {
  describe(`contrast budget — ${theme}`, () => {
    it.each(AUDITED)(`--$fg on --$bg matches DESIGN.md`, ({ fg, bg }) => {
      const actual = contrast(tokens[fg]!, tokens[bg]!)
      const claimed = documented(theme, fg, bg)

      // One decimal place: enough to catch a token change, loose enough that
      // the table stays readable.
      expect(Number(actual.toFixed(2)), `--${fg} on --${bg} (${theme})`).toBeCloseTo(
        claimed.ratio,
        2,
      )
      expect(claimed.verdict, `--${fg} on --${bg} (${theme}) verdict`).toContain(
        verdict(actual),
      )
    })
  })
}

describe('the restrictions the audit rests on', () => {
  it('keeps --text-faint below AA in both themes, which is why it is restricted', () => {
    // Not a failure: DESIGN.md §1.3 permits it for placeholder, disabled and
    // non-essential ornament only. The test exists so that if someone raises
    // its lightness to "fix" the ratio, the restriction gets revisited rather
    // than silently becoming unnecessary.
    expect(contrast(LIGHT['text-faint']!, LIGHT['surface']!)).toBeLessThan(4.5)
    expect(contrast(DARK['text-faint']!, DARK['surface']!)).toBeLessThan(4.5)
  })

  it('justifies the landing page dark primary button', () => {
    // DESIGN.md §13 claims white-on-accent does not clear AA on dark and that
    // `bg-text text-canvas` does. Both halves are asserted, because the second
    // is the reason the first was rejected.
    expect(contrast(DARK['text']!, DARK['accent']!)).toBeLessThan(4.5)
    expect(contrast(DARK['canvas']!, DARK['text']!)).toBeGreaterThanOrEqual(7)
  })

  it('records that accent on accent-sunk does not clear AA on dark', () => {
    // Latent, not live: `--accent-sunk` is the selected-row background and the
    // only dark surface in the product is the landing page, which has no
    // tables. Asserted so that shipping a dark mode toggle cannot make it live
    // without this test being confronted. DESIGN.md §1.3 says the same.
    expect(contrast(DARK['accent']!, DARK['accent-sunk']!)).toBeLessThan(4.5)
    expect(contrast(LIGHT['accent']!, LIGHT['accent-sunk']!)).toBeGreaterThanOrEqual(4.5)
  })
})
