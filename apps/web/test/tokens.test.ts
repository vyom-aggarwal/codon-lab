/**
 * The Phase 1 exit gate, enforced mechanically.
 *
 * "DESIGN.md tokens are the only source of colour and type in the codebase" is a
 * claim that decays the moment someone is in a hurry. These tests make it fail the
 * build instead of failing quietly.
 */

import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

import { describe, expect, it } from 'vitest'

const WEB_ROOT = join(import.meta.dirname, '..')
const REPO_ROOT = join(WEB_ROOT, '..', '..')

/** The one file allowed to contain literal colour values — it *is* the token table. */
const TOKEN_FILE = join(WEB_ROOT, 'app', 'tokens.css')

function walk(dir: string, extensions: string[]): string[] {
  const found: string[] = []
  for (const entry of readdirSync(dir)) {
    if (entry === 'node_modules' || entry === '.next') continue
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) {
      found.push(...walk(full, extensions))
    } else if (extensions.some((ext) => entry.endsWith(ext))) {
      found.push(full)
    }
  }
  return found
}

function sourceFiles(): string[] {
  return [
    ...walk(join(WEB_ROOT, 'app'), ['.ts', '.tsx', '.css']),
    ...walk(join(WEB_ROOT, 'components'), ['.ts', '.tsx']),
    ...walk(join(WEB_ROOT, 'lib'), ['.ts', '.tsx']),
  ].filter((file) => file !== TOKEN_FILE)
}

function report(file: string, line: string): string {
  return `${relative(REPO_ROOT, file)}: ${line.trim()}`
}

describe('colour is only ever a token', () => {
  it('has no hex colour literals outside tokens.css', () => {
    const violations: string[] = []
    for (const file of sourceFiles()) {
      readFileSync(file, 'utf8')
        .split('\n')
        .forEach((line) => {
          if (/#[0-9a-fA-F]{3,8}\b/.test(line)) violations.push(report(file, line))
        })
    }
    expect(violations).toEqual([])
  })

  it('has no rgb() or hsl() literals outside tokens.css', () => {
    const violations: string[] = []
    for (const file of sourceFiles()) {
      readFileSync(file, 'utf8')
        .split('\n')
        .forEach((line) => {
          if (/\b(rgba?|hsla?)\(/.test(line)) violations.push(report(file, line))
        })
    }
    expect(violations).toEqual([])
  })
})

describe('type and spacing come off the scale', () => {
  it('uses no arbitrary values containing raw lengths or colours', () => {
    // `animate-[layer-in_var(--duration-fast)]` is fine — it composes tokens.
    // `text-[13px]` is not — it is a token that never made it into DESIGN.md.
    const arbitrary = /\b[a-z-]+-\[([^\]]+)\]/g
    // The unit ends in a negative lookahead rather than `\b`. `\b` is a word
    // boundary and `_` is a word character, so `grid-cols-[4rem_1fr]` slipped
    // past this check for as long as it existed — Tailwind uses `_` as its
    // space separator, and that underscore suppressed the boundary. Found while
    // adding the landing page, which is where a multi-value arbitrary track
    // template first appeared in this codebase.
    const rawLiteral = /#[0-9a-fA-F]{3,8}|\d+(\.\d+)?(px|rem|em|vh|vw)(?![a-z])/

    const violations: string[] = []
    for (const file of sourceFiles()) {
      for (const line of readFileSync(file, 'utf8').split('\n')) {
        for (const match of line.matchAll(arbitrary)) {
          const inner = match[1] ?? ''
          if (rawLiteral.test(inner)) violations.push(report(file, match[0]))
        }
      }
    }
    expect(violations).toEqual([])
  })

  it('uses no Tailwind stock type sizes', () => {
    // These were deleted from the theme, so they would silently render as nothing.
    const stock = /\btext-(xs|sm|base|lg|xl|2xl|3xl|4xl|5xl|6xl|7xl|8xl|9xl)\b/
    const violations: string[] = []
    for (const file of sourceFiles()) {
      readFileSync(file, 'utf8')
        .split('\n')
        .forEach((line) => {
          if (stock.test(line)) violations.push(report(file, line))
        })
    }
    expect(violations).toEqual([])
  })

  it('uses no Tailwind stock radii', () => {
    const stock = /\brounded-(sm|md|lg|xl|2xl|3xl)\b/
    const violations: string[] = []
    for (const file of sourceFiles()) {
      readFileSync(file, 'utf8')
        .split('\n')
        .forEach((line) => {
          if (stock.test(line)) violations.push(report(file, line))
        })
    }
    expect(violations).toEqual([])
  })
})

describe('banned devices stay banned', () => {
  it('uses rounded-full only for status dots', () => {
    const offenders = sourceFiles().filter(
      (file) => /\brounded-full\b/.test(readFileSync(file, 'utf8')) && !file.endsWith('badge.tsx'),
    )
    expect(offenders.map((file) => relative(REPO_ROOT, file))).toEqual([])
  })

  it('uses no backdrop-blur', () => {
    const offenders = sourceFiles().filter((file) =>
      /\bbackdrop-blur\b/.test(readFileSync(file, 'utf8')),
    )
    expect(offenders.map((file) => relative(REPO_ROOT, file))).toEqual([])
  })

  it('uses no gradients outside data visualisation', () => {
    const offenders = sourceFiles().filter((file) =>
      /\bbg-gradient-|linear-gradient\(/.test(readFileSync(file, 'utf8')),
    )
    expect(offenders.map((file) => relative(REPO_ROOT, file))).toEqual([])
  })

  it('declares only the two permitted shadows', () => {
    const shadows = new Set<string>()
    for (const file of sourceFiles()) {
      for (const match of readFileSync(file, 'utf8').matchAll(/\bshadow-([a-z]+)\b/g)) {
        if (match[1]) shadows.add(match[1])
      }
    }
    expect([...shadows].sort()).toEqual(['dialog', 'popover'])
  })

  it('contains no emoji', () => {
    const emoji = /\p{Extended_Pictographic}/u
    const violations: string[] = []
    for (const file of sourceFiles()) {
      readFileSync(file, 'utf8')
        .split('\n')
        .forEach((line) => {
          if (emoji.test(line)) violations.push(report(file, line))
        })
    }
    expect(violations).toEqual([])
  })
})

describe('tokens.css matches DESIGN.md', () => {
  const design = readFileSync(join(REPO_ROOT, 'DESIGN.md'), 'utf8')
  const tokens = readFileSync(TOKEN_FILE, 'utf8')

  // Every token the specification names, from §4 of the brief.
  const REQUIRED = [
    'canvas',
    'surface',
    'surface-sunk',
    'border',
    'border-strong',
    'text',
    'text-muted',
    'text-faint',
    'accent',
    'accent-sunk',
    'positive',
    'negative',
    'warn',
  ]

  it.each(REQUIRED)('defines --%s in tokens.css', (name) => {
    expect(tokens).toMatch(new RegExp(`^\\s*--${name}:`, 'm'))
  })

  it.each(REQUIRED)('documents --%s in DESIGN.md', (name) => {
    expect(design).toMatch(new RegExp(`^\\s*--${name}:`, 'm'))
  })

  it('agrees with DESIGN.md on every light-mode colour value', () => {
    // Guards against the two files drifting apart, which is the failure mode the
    // "update the file in the same commit" rule exists to prevent.
    const lightBlock = tokens.slice(0, tokens.indexOf("[data-theme='dark']"))
    for (const name of REQUIRED) {
      const inTokens = new RegExp(`^\\s*--${name}:\\s*([^;]+);`, 'm').exec(lightBlock)?.[1]
      const inDesign = new RegExp(`^\\s*--${name}:\\s*([^;]+);`, 'm').exec(design)?.[1]
      expect(inTokens?.trim(), `--${name}`).toBe(inDesign?.trim())
    }
  })

  it('defines exactly the six application sizes plus the three display sizes', () => {
    const sizes = [...tokens.matchAll(/^\s*--text-(\d+):/gm)].map((match) => match[1])
    expect(sizes).toEqual(['11', '12', '13', '15', '18', '24', '32', '44', '56'])
  })

  it('keeps the display sizes off every application screen', () => {
    // 32 and 44 exist for the landing page, which is not part of the app and
    // which the brief's in-app scale was not written for (DESIGN.md §1.5).
    // Widening the scale is only safe if the widening is contained, so the
    // containment is a test rather than a convention.
    const display = /text-(32|44|56)/
    const landing = join('components', 'landing')
    const offenders = sourceFiles().filter(
      (file) => display.test(readFileSync(file, 'utf8')) && !file.includes(landing),
    )
    expect(offenders.map((file) => relative(REPO_ROOT, file))).toEqual([])
  })

  it('defines no font weight at or above 700', () => {
    const weights = [...tokens.matchAll(/--font-weight-[a-z]+:\s*(\d+)/g)].map((match) =>
      Number(match[1]),
    )
    expect(weights.length).toBeGreaterThan(0)
    expect(Math.max(...weights)).toBeLessThan(700)
  })
})
