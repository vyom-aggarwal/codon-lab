# Deploying Codon Lab

Vercel hosts the web app. It cannot host the rest of the product, and this
document is mostly about why, and what to run instead.

If you only read one thing: **set `CODONLAB_AUTH=jwt` before you point a real
domain at the API.** The API refuses to start otherwise, which is deliberate —
see [Authentication](#authentication).

---

## 1. Why the deployment is split

The landing page works on Vercel today and nothing else does. That is not a
configuration mistake; it is the shape of the product.

Every application screen is `force-dynamic` and fetches from the API at request
time. The landing page is the only screen that calls nothing, which is exactly
why it is the only one that renders. Point `NEXT_PUBLIC_API_URL` at a reachable
API and the other nine start working.

The API cannot be a Vercel function, and the blocker is the **worker**. A design
run scores every single substitution in the target and takes up to
`JOB_TIMEOUT_SECONDS` — 3600 — to do it. Serverless functions are capped in the
low hundreds of seconds on every tier. A fifty-five minute job needs a process
that stays alive, and once something is running that process the API belongs
beside it.

So: **web on Vercel, everything else on a container host.**

| Piece | Where | Why |
| --- | --- | --- |
| `apps/web` | Vercel | Next.js, already building |
| `apps/api` (uvicorn) | Container host | Beside the worker |
| `apps/api` (RQ worker) | Container host | Long-running; the hard constraint |
| Postgres | Managed | |
| Redis | Managed | The job queue, not a cache |

`render.yaml` provisions the last four in one blueprint. Render is chosen
because a single file does all of it — there is no Render-specific code in the
application, and Railway, Fly and Koyeb run the same two images.

**Cost, plainly.** Render does not offer background workers on the free plan,
and a free web service sleeps after inactivity, which behind a Vercel front end
means the first request after a quiet period times out. Two Starter instances is
the realistic floor. Postgres and Key Value have usable free tiers, though the
free database expires and must be recreated.

---

## 2. Order of operations

### 2.1 Provision the backend

1. Push the repo.
2. Render → **New → Blueprint** → select it. `render.yaml` creates the API, the
   worker, Postgres and Key Value.
3. Fill in every value Render prompts for — the ones marked `sync: false`,
   which are `CORS_ORIGINS`, the two Clerk-derived JWT settings, and optionally
   `ANTHROPIC_API_KEY`. Filling them at creation is the difference between one
   deploy and three. See §4 for what each one is.

Migrations run in `preDeployCommand`, once per deploy, rather than in the start
command — otherwise every instance races every other instance to apply the same
migration the moment the service scales past one.

### 2.2 Point the web app at it

In the Vercel project, set:

```
NEXT_PUBLIC_API_URL = https://codonlab-api.onrender.com
```

**This is a build-time variable.** `NEXT_PUBLIC_*` values are inlined into the
client bundle when Next builds, so setting it after a deploy changes nothing
until you redeploy. Set it, then trigger a fresh build.

Leave `API_INTERNAL_URL` unset on Vercel. It exists so that server components
inside Docker Compose can reach the API by service name; on Vercel the server
and the browser both use the public URL, and the code already falls back
correctly.

### 2.3 Close the loop

Set `CORS_ORIGINS` on the API to the Vercel origin, comma-separated if there are
several:

```
CORS_ORIGINS = https://codon-lab.vercel.app
```

There is no wildcard, on purpose. Until this names the front end's real origin,
the browser cannot call the API at all.

---

## 2.4 Running it for free, on one box

The split above — API, worker, Postgres and Redis as four managed services — is
the shape that costs money, and the reason is the **worker**. Platform free
tiers either do not offer background workers at all (Render) or sleep them,
which kills a run mid-flight. `render.yaml` therefore asks for two paid Starter
instances.

**If the cost is the problem, stop paying per service and run the whole
`docker-compose.yml` on one machine.** That is the configuration this project
actually develops against, and as of 2026-09-15 it is verified from a cold
clone: a fresh `git clone` with no `.env`, five images built from nothing, seven
migrations against an empty database, the seed landing 2,172 measured values,
and every screen serving. `HANDOFF.md` §9.18 records exactly what was run.

```bash
git clone https://github.com/vyom-aggarwal/codon-lab.git
cd codon-lab && docker compose up -d
```

No `.env` is required — every variable in the compose file has a default.

**Where to put that box.** Two options with honestly different confidence:

- **Your own machine, exposed with a Cloudflare Tunnel.** Free, needs no new
  hosting account, and works today. It is reachable only while your machine is
  on, which makes it right for showing somebody on a call and wrong for "here
  is a link, look whenever".
- **A free-tier cloud VM.** Oracle Cloud's Always Free ARM instances are the
  usual candidate and are generously specified for this. All five images
  (`python:3.12-slim`, `node:22-slim`, `postgres:17-alpine`, `redis:7-alpine`)
  are official multi-arch builds, so ARM is fine — that was checked, not
  assumed. **What was not checked is Oracle's current terms, their ARM capacity,
  or whether the card they ask for stays uncharged.** Read their pricing page
  rather than this paragraph.

Free tiers move. Fly.io, Railway and Koyeb have all changed theirs repeatedly
and none of them is recommended here, not because they are bad but because no
claim about them could be verified at the time of writing.

**What a single box does not give you.** No managed backups, no failover, and
one machine's worth of CPU for hour-long scoring jobs. That is the correct
trade for a demo or a lab's internal instance, and the wrong one for anything
a team depends on.

---

## 3. Authentication

### 3.1 What it is, and what it is not

Identity is delegated to an OIDC provider — Clerk, Auth0, Supabase, WorkOS,
Firebase, Okta, any of them. **This service stores no credentials.** There is no
password hash, no reset token, no session table. It verifies a signed token
against the provider's published keys and nothing else.

That is a deliberate choice rather than a shortcut. This product holds
unpublished protein sequences; a lab's design set before publication is the most
sensitive thing it touches. Password storage, reset flows, email verification,
lockout and MFA are each a place to get security wrong, and they are delegated
to a service whose business is getting them right.

A `User` row is created the first time a valid token is presented, keyed on the
provider's `sub` claim. There is no registration step, because the provider has
already established who the person is.

### 3.2 The two modes

| `CODONLAB_AUTH` | Meaning |
| --- | --- |
| `disabled` | No tokens. Every request is one implicit local user. For development. |
| `jwt` | Bearer token required, verified on every request. For anything reachable. |

**The API refuses to start with `disabled` while `CORS_ORIGINS` names a
non-local origin.** That combination serves every project in the database to
anyone who finds the URL and lets them queue an hour of compute per request, and
it has no symptom until it matters. The guard hangs off `CORS_ORIGINS` because
that is the setting a deployment *must* change, so the check has something to
fire on at exactly the moment the API becomes reachable.

### 3.3 The provider is Clerk, and here is the whole of your part

Clerk is chosen and wired. The reasoning, briefly, because it was a decision
made on your behalf: it is the only option where setup is *sign up and paste two
keys*. Auth0 needs a tenant, an API, an audience and callback URLs; Supabase
Auth pulls in a whole platform; Auth.js means self-hosting sessions and building
a JWKS endpoint by hand. Clerk has first-class Next.js App Router support and
publishes a standard JWKS that the API already consumes.

Nothing about the API is Clerk-specific. It verifies any OIDC provider's tokens
against a JWKS URL, so this is a swap of environment variables if you ever want
to move.

**Your steps, in full:**

1. Create a Clerk account and an application at <https://dashboard.clerk.com>.
   The free tier covers 10,000 monthly active users.

2. From **API keys**, copy the two values into **Vercel**:

   ```
   NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY = pk_live_...
   CLERK_SECRET_KEY                  = sk_live_...
   ```

   `NEXT_PUBLIC_*` is build-time, so redeploy after setting it.

3. Set three values on the **API** service (Render), taking the domain from
   Clerk's **API keys → Show JWT public key / Frontend API URL**:

   ```
   CODONLAB_AUTH       = jwt
   CODONLAB_JWKS_URL   = https://<your-app>.clerk.accounts.dev/.well-known/jwks.json
   CODONLAB_JWT_ISSUER = https://<your-app>.clerk.accounts.dev
   ```

That is the entire integration. There is no sign-in page to build, no callback
URL to register, and no user table to manage — Clerk's hosted modal handles sign
in and sign up, and a `user` row is created here the first time someone presents
a valid token.

**On `CODONLAB_JWT_AUDIENCE`:** leave it unset with Clerk. Clerk's default
session token carries no `aud` claim, and the API only checks the audience when
one is configured, so setting it would refuse every valid token. If you later
create a Clerk **JWT template** with an audience, set this to match it — that is
worth doing if the same Clerk app ever serves a second API.

### 3.4 Configuring a different provider

```
CODONLAB_AUTH          = jwt
CODONLAB_JWKS_URL      = https://<tenant>/.well-known/jwks.json
CODONLAB_JWT_ISSUER    = https://<tenant>/
CODONLAB_JWT_AUDIENCE  = <the API identifier you configured>
```

`JWKS_URL` is required. Issuer and audience are optional but **strongly
recommended**, and each is checked only when set:

- Without `iss`, a token minted by a *different tenant of the same provider* is
  accepted here.
- Without `aud`, a token the same issuer minted for a *different application of
  yours* can be replayed against this one.

Both are correctly signed and unexpired, so the signature check does not catch
either.

The web app must then send `Authorization: Bearer <token>` on API calls. That
wiring is **not built** — see §6.

### 3.5 Existing projects will disappear, and that is correct

Migration `0006_ownership` adds a nullable `owner_id` to `project` and does not
backfill it. Every project created before authentication existed has no owner,
and nothing in the database records who made them, because there was nobody to
record.

Under `CODONLAB_AUTH=jwt` an unowned project belongs to nobody and is shown to
nobody. **Deploying against a database that already has projects will show an
empty project list.** Assigning them to whoever signs in first would be
inventing a claim about authorship, which is the same class of thing as
inventing a scientific number — it would render identically to a true one.

If you want the seeded demo data owned by a real account, sign in once so your
`user` row exists, then:

```sql
UPDATE project SET owner_id = (SELECT id FROM "user" WHERE subject = '<your sub>')
WHERE owner_id IS NULL;
```

That is a deliberate act with a person's name on it, which is the point.

---

## 4. Environment variables

### API and worker

| Name | Required | Notes |
| --- | --- | --- |
| `DATABASE_URL` | yes | Any Postgres URL. `postgres://` and `postgresql://` are rewritten to the psycopg 3 driver automatically — see below. |
| `REDIS_URL` | yes | The job queue. |
| `CORS_ORIGINS` | yes | The Vercel origin. No wildcard. |
| `CODONLAB_AUTH` | yes in production | `jwt` or `disabled`. |
| `CODONLAB_JWKS_URL` | with `jwt` | Provider's JWKS endpoint. |
| `CODONLAB_JWT_ISSUER` | recommended | Checked only when set. |
| `CODONLAB_JWT_AUDIENCE` | recommended | Checked only when set. |
| `CODONLAB_MAX_RUNS_IN_FLIGHT` | no | Default 3. See §5. |
| `CODONLAB_PROVIDERS` | no | Default `mock`. See §6. |
| `CODONLAB_SEED_DEMO_DATA` | no | Default on. Set `false` for a real lab's instance. |
| `ANTHROPIC_API_KEY` | no | Goal parsing only. Blank uses the deterministic parser. |
| `CODONLAB_PARSER_MODEL` | no | Which Claude model parses a goal. Ignored without a key. |

**On `DATABASE_URL`:** every managed Postgres hands out a URL that SQLAlchemy
reads as psycopg **2**, which this project does not install. Render, Heroku and
Fly issue `postgres://`; Neon and Supabase issue `postgresql://`. Both are
rewritten to `postgresql+psycopg://` at startup, so the generated connection
string can be pasted in unedited — including when it is rotated. A URL that
already names a driver is left alone.

### Web (Vercel)

| Name | Required | Notes |
| --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | yes | **Build-time.** Redeploy after changing. |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | for sign-in | **Build-time.** Absent means no sign-in and no token — the local mode. |
| `CLERK_SECRET_KEY` | for sign-in | Server-side only. |
| `API_INTERNAL_URL` | no | Leave unset on Vercel. |

Leaving both Clerk keys unset is a supported state, not a broken one: the app
renders exactly as it did before authentication existed. That is what local
development and the whole gate suite run against, so the path stays real.

---

## 5. Rate limiting

`POST /goals/{id}/runs` buys up to an hour of a shared worker. The limit is a
**ceiling on runs in flight** — pending or running — per user, defaulting to 3.

It is not a rate per time window, because that would measure the wrong thing.
The scarce resource is the worker, and what consumes it is unfinished runs. Ten
enqueues in a second are harmless if nine are cache hits on an identical content
address, which this product treats as the same run. One an hour is a permanent
backlog if each takes fifty-five minutes. Finishing or cancelling a run frees
capacity immediately.

Raise `CODONLAB_MAX_RUNS_IN_FLIGHT` if you deploy more than one worker; that is
the number it should track.

---

## 6. What is still missing

Deploying this today gives you a working, authenticated, rate-limited instance
that **fabricates every number**. Read this section before showing it to anyone.

1. **`CODONLAB_PROVIDERS=mock` fabricates every score.** The product is honest
   about it — a persistent amber bar on every screen, a badge on every number,
   watermarked exports, a refusal to generate primers — but it is a demo, not a
   tool. Real predictors need the `[models]` extra (torch plus the ESM-2 650M
   checkpoint, several gigabytes) and a much larger instance. `HANDOFF.md` open
   thread 11 records that the containerised real-provider path has **never been
   verified**.

2. **A 550-residue target cannot be run at all.** `JOB_TIMEOUT_SECONDS` is 3600
   and the seeded luciferase needs about 142 minutes. The fix is resumable
   scoring, designed and unbuilt — `HANDOFF.md` §9.3 carries the exact shape.

3. **No primers, no PDF export.** Blocked on the data model having no template
   DNA. `HANDOFF.md` §9.2.

4. **Projects cannot be shared.** Ownership is per user. A lab that wants a
   shared project needs an organisation model — invitations, roles, a sharing
   UI. The schema is shaped so that slots in above `Project.owner_id` without a
   rewrite, but none of it is built.

---

## 7. Verifying a deployment

```bash
curl https://<api>/health                 # 200
curl https://<api>/meta                   # providers, demo flag
curl -i https://<api>/projects            # 401 when CODONLAB_AUTH=jwt
```

A `401` from `/projects` with no token is the check that authentication is
actually on. A `200` means it is not, and you should stop and fix that before
anything else.

Locally, `python scripts/verify_gates.py` runs the whole suite against a live
stack, including the ownership behaviour checks.
