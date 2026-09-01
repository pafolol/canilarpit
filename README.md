# Can I LARP It

One question per entry: **can you larp it, and for how long before someone catches you?**

To LARP something is to present yourself as knowing or being something you do not — a
film you never watched, a scene you do not belong to, a job you do not do. This site is
the briefing you read beforehand: the crib sheet, the lines to actually say, the follow-up question that collapses
it **and what to say when it lands**, the tells, the cost of being caught, and the
honest hours it would take to just learn the thing instead.

Every larpable entry answers its own killer question. The counter gives the reader the
words, not a strategy, and states where it stops working — an oversold counter gets
somebody caught worse than none. The one entry with no counter says so.

Three of the four verdicts are a yes. **YES** holds indefinitely, **KINDA** holds at the
bar and fails at the table, and **TALK ONLY** means the conversation holds but the doing
does not — you can discuss the instrument, you cannot play it. **DON'T** is reserved for
claims that endanger or defraud someone, and those entries exist to say so. Filing
something under DON'T for being merely difficult would make the site useless.

Readers type a word. If a guide exists they read it. If it does not, they ask for it,
and that demand shows up in the editors' backlog.

## The repository

```
canilarpit/
├── backend/     FastAPI + PostgreSQL: catalog, editorial CMS, guide generation
├── frontend/    React + Vite: the public reading interface and the admin panel
└── scripts/     The same tasks in PowerShell, for Windows
```

The two halves used to be separate branches. They are one repo now: `backend/` owns the
data and the contract, `frontend/` reads it through `frontend/src/api.ts`, and nothing
in the interface holds its own copy of the content.

## Quick start

macOS, with [Homebrew](https://brew.sh). Node and Python 3.11+ come from `brew install
node python`. The database is its own step:

```bash
brew install postgresql@17
brew services start postgresql@17
```

The formula is versioned, so its client tools stay off the PATH, and the cluster it
creates has no `postgres` role — which is the one the stock `DATABASE_URL` asks for.
Both are a one-time fix:

```bash
export PATH="/opt/homebrew/opt/postgresql@17/bin:$PATH"
psql -d postgres -c "CREATE ROLE postgres LOGIN SUPERUSER PASSWORD 'postgres'"
createdb -O postgres canilarpit
```

Then:

```bash
npm run setup
```

That creates `.venv`, installs both halves, and writes `backend/.env` and
`frontend/.env` from their examples. The stock `DATABASE_URL` already names the database
you just created, so nothing needs editing:

```bash
npm run db:migrate
npm run db:seed
npm run dev
```

- Reading interface: <http://localhost:5173>
- Admin panel: <http://localhost:5173/admin>
- API: <http://127.0.0.1:8000>, Swagger at `/docs`

The dev server proxies `/api` and `/health` to the API, so the frontend calls relative
paths and never needs CORS in development.

### Making yourself an editor

Sign-in is email and password, kept here. There is no third-party identity
provider and no registration endpoint: **accounts are made by an administrator**,
because an admin panel that lets a stranger create an account is an admin panel
with a stranger in it.

The first one comes from the command line, which is the only place that has the
machine before anybody has an account:

```bash
.venv/bin/python -m app.cli create-user you@example.com --role admin
```

(from the repo root, or `canilarpit create-user ...` with the venv active.)

It asks for the password twice and never echoes it. After that, an administrator
adds editors from the panel's **Editors** tab. `canilarpit users` lists accounts
and says which of them can actually sign in.

Passwords are hashed with Argon2id, salted per row, and are not readable by
anybody — an administrator can set a new one for somebody locked out, and that
ends every session that account had. Changing your *own* password asks for the
current one, which is what stops a borrowed unlocked laptop becoming permanent.

`DEV_AUTH_BYPASS=true` additionally offers a one-click local sign-in that sends
an identity header instead of a password. The API refuses it twice over: the
settings validator will not build a production configuration with it on, and the
request path ignores the header regardless of what the settings say.

## Generating a guide

The admin panel's **Generate** tab takes a topic and produces a complete draft:

1. The model writes the whole guide document in one JSON object.
2. The API validates it with the same Pydantic schema the CMS uses. Validation errors
   are handed back to the model to repair, up to `AI_MAX_REPAIR_ATTEMPTS` times.
3. Every source URL is fetched. Dead links are dropped, along with the citations that
   pointed at them, so a published guide never carries a broken reference.
4. Images are fetched. The guide's own `image_brief` names a source per picture, and
   the model chooses it: a character goes to an anime or television database, a loaf of
   bread goes to a photo library. See **Images** below.
5. The result is a **draft**. Nothing is published until an admin publishes it.

Set `OPENAI_API_KEY` in `backend/.env` to switch it on; `OPENAI_BASE_URL` and
`OPENAI_MODEL` point it at any OpenAI-compatible endpoint. Without it everything else
still works — the panel says which feature is unavailable and why.

## Images

Pexels has never heard of Walter White. So the backend keeps a registry of image
providers and the model picks one per picture:

| Provider | Key | Good for | Rights |
|---|---|---|---|
| Pexels | yes | Objects, food, drink, places, sport, interiors | Free licence |
| Wikimedia Commons | no | Real people, buildings, marques, artefacts | CC, varies by file |
| TVmaze | no | Series, their characters and episodes | Editorial only |
| AniList | no | Anime and manga, and their characters | Editorial only |
| MyAnimeList (Jikan) | no | Anime and characters, as a second opinion | Editorial only |
| fanart.tv | yes | Transparent logos, banners and clear art | Editorial only |

Four of the six need no key at all, so guides get illustrated out of the box.

TMDB is deliberately absent: it charges for commercial use. Film imagery comes from
Commons — directors, premieres, locations — rather than posters, which belong to
somebody anyway. fanart.tv resolves its ids through TVmaze for television and
Wikidata for film, so it needs no second key.

Two rules keep the results honest:

- **Providers substitute only within their family.** Generic photo libraries can cover
  for each other; a film database cannot degrade to a stock library. Asking a screen database
  for *Jeanne Dielman* and settling for whatever Commons has under that name gets you
  an unrelated 1929 portrait, so an unavailable specialist returns nothing instead.
- **Free-text results are filtered for relevance.** Commons will answer "techno club
  dancefloor" with a photograph of a Bukharan folk dance, because both mention dancing.
  Matches below half the query's significant words are dropped, and the rest are ranked.

Everything from TVmaze, AniList, Jikan and fanart.tv is copyrighted promotional
material: fine editorially with credit, but the rights belong to whoever owns the film
or show. Those assets are stored with `editorial_only` set, the admin panel labels them
"rights reserved", and the public page prints the credit and licence under every image.

To illustrate guides that have none:

```bash
.venv/bin/canilarpit backfill-images          # published guides missing images
.venv/bin/canilarpit backfill-images --replace # rebuild all of them
```

The guide editor has a **Regenerate** button that rewrites an existing guide from its
own title. The slug is pinned, so a rewrite always lands on the same guide as a draft;
the published version stays up until you publish the new one. Tick *new images too* to
refetch the pictures as well.

Generation runs inside the API process as a background task. For a separate worker:

```bash
.venv/bin/canilarpit work --limit 5
```

## Reader submissions

When a search finds nothing, the reader gets the one-line request button first, because
most people only want to say "write this one". Beside it is an offer: **Submit it
yourself**, which opens `/submit` with the topic filled in.

That page asks for what the thing is, what somebody would need to know, which category it
belongs in or one they would like added, and a name to be credited under. An editor
reviews it, a model screens and drafts it, and a human publishes it. The credit appears
on the entry as "Suggested by".

It is the only unauthenticated endpoint that stores prose, so it has five independent
obstacles in front of it, and none of them shares a weakness with the others:

1. **A signed form token**, bound to the client and the moment it was issued.
2. **A minimum delay** between opening the form and sending it. People read; scripts do not.
3. **A honeypot field** the layout hides, so anything in it did not come from a person.
4. **Limits.** Requests are flood-limited per client fingerprint rather than per address,
   because behind a proxy everybody shares one address. The real bound is a database
   quota on how many submissions one client can have waiting.
5. **Content heuristics**: length, word variety, and how much of it is links.

No raw address is stored anywhere. A submission carries an HMAC of address, user agent
and language under `SUBMISSION_SECRET` — enough to count against and to block, useless
for identifying anybody. Rotating the secret clears every stored hash, which is how you
reset a block list. Set it before deploying: the app refuses to start in production
without one.

**Reviewing costs money, so only an editor can trigger it.** Nothing an anonymous
request does reaches a model.

## Sharing, and who is reading

`npm run build` puts the app in `frontend/dist`, and from then on the API serves it. That is
what makes a shared link work: Slack, Discord, WhatsApp and search crawlers read the HTML the
server returns and never run JavaScript, so `/entry/{slug}` gets the guide's own title,
description and hero image injected into the head before the page leaves. Set `SITE_BASE_URL`
to the origin readers actually use — those tags and `/sitemap.xml` are absolute URLs.

With no build on disk nothing is mounted and `npm run dev` is untouched: Vite serves the
frontend on 5173 and proxies the API.

Three counters, all anonymous and all keyed on the same HMAC the submission form uses, so no
raw address is stored anywhere:

- **Views.** One per client per entry per half hour. Without the window the number would be a
  refresh count, and the site does not print numbers it does not mean.
- **Presence.** One row per client, swept every heartbeat. Always the real number, including
  when it is 1.
- **Hours.** Denormalized onto each guide row when a revision is published, so
  `/just-learn-it` sorts in SQL rather than by opening every revision.

An entry also prints. `@media print` drops the chrome, the rail, the images and the clock, and
leaves the crib sheet, the lines to say and the tells, in ink on white — the laminated pocket
card the design has always claimed to be.

## The admin surface

The catalog is public and everything that writes to it is not. What a request is
allowed to do is read out of the database at the moment it asks — never from the
cookie, never from a cache. An editor demoted a second ago is demoted on their
next call.

**The session is a row, not a signature.** The cookie carries an opaque random
string that decodes into nothing, and the database stores only its SHA-256, so a
copy of the table is not a set of working sessions. That is the whole reason for
the design: a signed token is valid until it expires and there is nowhere to go
to say otherwise, whereas a row can be marked revoked and refused on the very
next request. Signing out actually signs out, and so does *sign out everywhere*.

The cookie is `HttpOnly`, so no script can read it and an XSS cannot steal it.
Beside it rides a deliberately readable CSRF cookie the panel echoes back as a
header on every write: another origin can make a browser send our cookies, but
it cannot read them, so it cannot produce the matching header, and both have to
agree.

**Signing in assumes somebody is attacking it.** Two throttles — one on the
caller, one on the account, because moving address beats the first and nothing
beats the second. A wrong address and a wrong password give the same message
and, because a missing account still pays for a full Argon2 verification, about
the same amount of time. Both throttles run before the account is looked up, so
being rate-limited does not confirm an address either.

**Deny is the default.** Editor-or-better and a request ceiling sit on the whole
`/admin` prefix rather than route by route, so an endpoint added next month is
authenticated the day it is written. Individual routes opt into being *more*
restricted — publishing, archiving, accepting a submission and everything under
Editors are admin-only — never less.

**On the way out.** Every response carries `nosniff`, `DENY`, a referrer policy,
an empty permissions policy, and in production HSTS. Admin JSON leaves with
`no-store`, so an unpublished draft cannot come to rest in a proxy. The content
policy is `script-src 'self'` on every page, panel included, because sign-in is
a form this application serves and nothing is loaded from anywhere else.

**In production the app refuses to start** without a `SUBMISSION_SECRET`, an
https `SITE_BASE_URL`, and `FRONTEND_ORIGINS` that are https and contain no `*`
— a wildcard origin with credentials is how an admin session reaches everybody.
Swagger, ReDoc and `/openapi.json` are not served at all: authentication does
not stop anybody reading a route-by-route map of the admin surface.

`TRUSTED_HOSTS` is the one control left off by default. An incomplete list
answers 400 to every request including health checks, so it is installed only
once a deployment has said which hosts it answers to.

## Publishing to a deployed site

The local database is the authoring copy. `scripts/upload.py` replays it into a
deployed API through the same admin endpoints the panel uses, so the server
needs no database access of its own:

```bash
npm run db:upload -- --dry-run
npm run db:upload -- --email you@example.com
```

It defaults to <https://api.mcocvault.com/larp>; `--api-url` points it somewhere
else. Each guide goes up as a document, gets its images placed on the draft, and
is published only if it is published here — so a half-illustrated entry never
appears. Guides the target already serves are compared by content hash and
skipped, which makes a re-run cost nothing and a second run after a failure
finish the job.

The script signs in once with an editor account and holds the session for the
whole run, so a long upload does not race a credential's expiry. Put the password
in `CANILARPIT_PASSWORD` or let it prompt. A large catalog can reach the admin
request ceiling; the script waits out a 429 and carries on rather than stopping
half way. Importing needs the editor role and publishing needs admin; with an
editor token everything arrives as a draft.

Readers, view counts, presence, submissions and topic requests are deliberately
left behind. They belong to the deployment they happened on, and the counter on
the live site counts real people.

## Checks

```bash
npm run check
```

Runs `ruff`, `pytest`, `oxlint`, and the production build. The tests in
`backend/tests/test_api_live.py` exercise the real API against PostgreSQL and skip
themselves when no seeded database is reachable, so the suite is useful either way.

Two of them want more than a database. `test_the_seeded_guides_are_illustrated` expects
`backfill-images` to have run, and `test_regenerating_an_unknown_guide_is_a_404` expects
generation to be configured — the endpoint answers 503 before it looks the guide up, so
any non-empty `OPENAI_API_KEY` satisfies it.

## What is where

| Concern | File |
|---|---|
| The verdict layer, and the six content templates | `backend/app/schemas/content.py` |
| Search, filters, topic demand, counting | `backend/app/api/routes/public.py` |
| Serving the built app, sharing tags, sitemap | `backend/app/api/routes/site.py` |
| Editorial CMS and lifecycle | `backend/app/api/routes/admin.py` |
| Who is asking, verified per request | `backend/app/core/security.py` |
| Signing in, sessions, password change | `backend/app/api/routes/auth.py` |
| Password hashing | `backend/app/services/passwords.py` |
| Sessions and the cookie pair | `backend/app/services/sessions.py` |
| Response headers and the per-surface CSP | `backend/app/core/headers.py` |
| Throttles on the authenticated surface | `backend/app/core/auth_guard.py` |
| Admin sign-in in the panel | `frontend/src/auth.tsx` |
| Account management | `frontend/src/admin/Editors.tsx` |
| Guide generation | `backend/app/services/ai.py`, `services/generation.py` |
| Image providers | `backend/app/services/images.py` |
| Frontend API client and types | `frontend/src/api.ts` |
| Admin panel | `frontend/src/admin/` |
| Seed content | `backend/content/guides/*.json` |
| Pushing the catalog to a deployment | `scripts/upload.py` |
| Print stylesheet, the pocket crib card | `frontend/src/styles.css` |

The complete HTTP contract is in [`backend/docs/API.md`](backend/docs/API.md).
