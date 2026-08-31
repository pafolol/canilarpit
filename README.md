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
└── scripts/     Setup, dev, migrate, seed, check
```

The two halves used to be separate branches. They are one repo now: `backend/` owns the
data and the contract, `frontend/` reads it through `frontend/src/api.ts`, and nothing
in the interface holds its own copy of the content.

## Quick start

```powershell
npm run setup
```

That creates `.venv`, installs both halves, and writes `backend/.env` and
`frontend/.env` from their examples. Then point `DATABASE_URL` at a database you have
created, and:

```powershell
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

`DEV_AUTH_BYPASS=true` is set in `backend/.env`, so the admin panel offers a "Local
development" sign-in that sends an identity header instead of a Clerk token. The API
refuses that bypass outright when `APP_ENV=production`.

The first sign-in creates a `member`. Promote it once:

```powershell
.venv\Scripts\python.exe -m app.cli set-role local-admin admin
```

(run from `backend/`, or use `canilarpit set-role local-admin admin` with the venv
active). Reload `/admin` and the catalog appears.

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

```powershell
.venv\Scripts\canilarpit.exe backfill-images          # published guides missing images
.venv\Scripts\canilarpit.exe backfill-images --replace # rebuild all of them
```

The guide editor has a **Regenerate** button that rewrites an existing guide from its
own title. The slug is pinned, so a rewrite always lands on the same guide as a draft;
the published version stays up until you publish the new one. Tick *new images too* to
refetch the pictures as well.

Generation runs inside the API process as a background task. For a separate worker:

```powershell
canilarpit work --limit 5
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

## Checks

```powershell
npm run check
```

Runs `ruff`, `pytest`, `oxlint`, and the production build. The tests in
`backend/tests/test_api_live.py` exercise the real API against PostgreSQL and skip
themselves when no seeded database is reachable, so the suite is useful either way.

## What is where

| Concern | File |
|---|---|
| The verdict layer, and the six content templates | `backend/app/schemas/content.py` |
| Search, filters, topic demand | `backend/app/api/routes/public.py` |
| Editorial CMS and lifecycle | `backend/app/api/routes/admin.py` |
| Guide generation | `backend/app/services/ai.py`, `services/generation.py` |
| Image providers | `backend/app/services/images.py` |
| Frontend API client and types | `frontend/src/api.ts` |
| Admin panel | `frontend/src/admin/` |
| Seed content | `backend/content/guides/*.json` |

The complete HTTP contract is in [`backend/docs/API.md`](backend/docs/API.md).
