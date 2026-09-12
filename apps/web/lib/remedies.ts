/**
 * What to tell someone when the API cannot be reached.
 *
 * These messages were written when this only ever ran on one developer's
 * machine, so every one of them said some version of "start the stack with
 * `docker compose up`". That is the correct advice for a developer and useless
 * — faintly alarming, even — to anyone who opens a deployed instance. They are
 * told to run a tool they do not have, for a machine that is not theirs, and
 * the reasonable conclusion is that the product is broken.
 *
 * So the remedy now depends on which kind of instance is speaking. The message
 * (*what* went wrong) never changes; only the remedy (*what would fix it*),
 * because the person who can fix it is different in each case.
 *
 * Three situations, and they are genuinely different:
 *
 *   development        A developer's local stack. `docker compose up` is right.
 *   deployed, unset    `NEXT_PUBLIC_API_URL` was never configured, so the app
 *                      is asking localhost from a server where nothing listens.
 *                      This is a deployment mistake and saying so is the only
 *                      way it gets found.
 *   deployed, set      An API address is configured and not answering. Usually
 *                      transient, and nothing the reader can do but wait.
 */

/**
 * Whether this build is a developer's local stack.
 *
 * `NODE_ENV` rather than a hostname check, because this has to give the same
 * answer in a server component and in the browser. Next inlines it at build
 * time, so both runtimes agree: `next dev` under Docker Compose is
 * development, and anything built for deployment is production.
 */
function isDevelopment(): boolean {
  return process.env.NODE_ENV !== 'production'
}

/**
 * Whether anybody told this build where the API lives.
 *
 * `baseUrl()` falls back to `http://localhost:8000` when nothing is set, which
 * is a sensible default locally and a silent misconfiguration once deployed —
 * the server then asks *itself* for port 8000 and finds nothing. Distinguishing
 * "no address configured" from "the address does not answer" is the whole
 * reason this function exists.
 */
function apiConfigured(): boolean {
  if (typeof window === 'undefined' && process.env.API_INTERNAL_URL) return true
  return Boolean(process.env.NEXT_PUBLIC_API_URL)
}

/**
 * The remedy for an API that cannot be reached at all.
 *
 * `verb` is what the reader should do after the cause is fixed — "reload" for a
 * page that was loading, "retry" for an action they took.
 */
export function unreachableRemedy(verb: 'reload' | 'retry' = 'reload'): string {
  if (isDevelopment()) {
    return `Start the stack with \`docker compose up\`, then ${verb}.`
  }
  if (!apiConfigured()) {
    return (
      'This deployment has no API address configured, so there is nothing for it '
      + 'to load from. Whoever deployed it needs to set NEXT_PUBLIC_API_URL and '
      + 'redeploy — see DEPLOYMENT.md.'
    )
  }
  return `The service may be starting up or briefly down. Wait a moment and ${verb}.`
}

/**
 * The remedy for a response whose shape does not match the contract.
 *
 * Never coerced past — a mismatched payload is how a wrong number reaches a
 * scientist — so this is always a hard failure, and the fix is always to get
 * the two halves onto the same commit.
 */
export function versionSkewRemedy(): string {
  return isDevelopment()
    ? 'The web and api versions are out of step — rebuild with `docker compose up --build`.'
    : 'The web app and the API are running different versions. Whoever deployed it '
      + 'needs to redeploy both from the same commit.'
}

/**
 * The remedy for an API that answered, but with an error.
 *
 * Distinct from `unreachableRemedy`: something *is* listening, so the reader
 * reloading is a reasonable first move rather than a way of passing the time.
 */
export function serverErrorRemedy(): string {
  return isDevelopment()
    ? 'Reload the page. If it persists, check `docker compose logs api`.'
    : 'Reload the page. If it persists, the service is having trouble and '
      + 'reloading again shortly is the only thing that will help.'
}

/**
 * The remedy for a queue with no worker consuming it.
 *
 * A run stays queued forever rather than failing, so this says what is true —
 * the work is accepted and nothing is executing it.
 */
export function noWorkerRemedy(): string {
  return isDevelopment()
    ? 'Start it with `docker compose up -d worker`.'
    : 'No worker is consuming the queue on this instance, so the run will not '
      + 'start until one is running.'
}
