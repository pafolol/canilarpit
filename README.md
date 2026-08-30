# Can I LARP It

One question per entry: **can you larp it, and for how long before someone catches you?**

To LARP something is to present yourself as knowing or being something you do not — a
film you never watched, a scene you do not belong to, a job you do not do. This site is
the briefing you read beforehand: the crib sheet, the follow-up question that collapses
it, the tells, the cost of being caught, and the honest hours it would take to just
learn the thing instead.

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
| TMDB | yes | Films, television, actors | Editorial only |
| TVmaze | no | Series, their characters and episodes | Editorial only |
| AniList | no | Anime and manga, and their characters | Editorial only |
| MyAnimeList (Jikan) | no | Anime and characters, as a second opinion | Editorial only |
| fanart.tv | yes | Transparent logos and clear art | Editorial only |

Four of the seven need no key at all, so guides get illustrated out of the box.

Two rules keep the results honest:

- **Providers substitute only within their family.** Generic photo libraries can cover
  for each other; a film database cannot degrade to a stock library. Asking TMDB for
  *Jeanne Dielman* and settling for whatever Commons has under that name gets you an
  unrelated 1929 portrait, so an unavailable specialist returns nothing instead.
- **Free-text results are filtered for relevance.** Commons will answer "techno club
  dancefloor" with a photograph of a Bukharan folk dance, because both mention dancing.
  Matches below half the query's significant words are dropped, and the rest are ranked.

Everything from TMDB, TVmaze, AniList, Jikan and fanart.tv is copyrighted promotional
material: fine editorially with credit, but the rights belong to whoever owns the film
or show. Those assets are stored with `editorial_only` set, the admin panel labels them
"rights reserved", and the public page prints the credit and licence under every image.

To illustrate guides that have none:

```powershell
.venv\Scripts\canilarpit.exe backfill-images          # published guides missing images
.venv\Scripts\canilarpit.exe backfill-images --replace # rebuild all of them
```

Generation runs inside the API process as a background task. For a separate worker:

```powershell
canilarpit work --limit 5
```

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
| The verdict layer (verdict, clock, tells, crib) | `backend/app/schemas/content.py` |
| Search, filters, topic demand | `backend/app/api/routes/public.py` |
| Editorial CMS and lifecycle | `backend/app/api/routes/admin.py` |
| Guide generation | `backend/app/services/ai.py`, `services/generation.py` |
| Image providers | `backend/app/services/images.py` |
| Frontend API client and types | `frontend/src/api.ts` |
| Admin panel | `frontend/src/admin/` |
| Seed content | `backend/content/guides/*.json` |

The complete HTTP contract is in [`backend/docs/API.md`](backend/docs/API.md).
