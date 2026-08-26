import '@testing-library/jest-dom/vitest'

import { vi } from 'vitest'

/**
 * jsdom has no Next App Router, so any client component calling `useRouter`
 * throws "invariant expected app router to be mounted" the moment it mounts.
 * The workbench mounts one — the design-set dialog in its footer — so this stub
 * is what lets the workbench render at all under test.
 *
 * It is deliberately a **stub, not a fake**: the methods record nothing and no
 * test asserts on them. Navigation is not a claim any of these tests make, and a
 * mock that could be asserted against would invite a test that passes because
 * `push` was called rather than because the interface did the right thing.
 */
vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: () => {},
    replace: () => {},
    refresh: () => {},
    back: () => {},
    forward: () => {},
    prefetch: () => {},
  }),
  usePathname: () => '/',
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
  redirect: () => {
    throw new Error('redirect() is not available under test')
  },
  notFound: () => {
    throw new Error('notFound() is not available under test')
  },
}))
