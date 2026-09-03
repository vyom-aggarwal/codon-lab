import { clerkMiddleware } from '@clerk/nextjs/server'
import { NextResponse } from 'next/server'

/**
 * Runs Clerk's middleware only when Clerk is configured.
 *
 * `clerkMiddleware()` throws at request time without a publishable key, so
 * calling it unconditionally would break every local run, every gate check and
 * both Playwright flows on a machine that has no identity provider — which is
 * every machine today. The unconfigured path is a supported mode (see
 * `lib/auth.ts`), so the middleware has to have one too.
 *
 * Note what this deliberately does *not* do: it does not protect routes. Clerk
 * decides who the caller is; the **API** decides what they may see, and it does
 * that against the database rather than against a URL pattern. Middleware that
 * also guarded routes would be a second, weaker copy of the same rule, free to
 * disagree with the real one — which is the same reasoning that keeps the run
 * confirmation gate in the service layer rather than in a route.
 */
const configured = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY)

export default configured ? clerkMiddleware() : () => NextResponse.next()

export const config = {
  matcher: [
    // Everything except Next internals and static files, plus the API routes.
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest|pdb)).*)',
    '/(api|trpc)(.*)',
  ],
}
