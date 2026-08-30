# Can I LARP It — API

FastAPI and PostgreSQL backend for the guide catalog. Public searches never trigger
generation. Missing topics are counted so editors can decide what to write next.

Every guide answers one question — *can you larp it, and for how long?* — so every
guide document carries a `content.larp` block: a verdict, an exposure clock, the crib
sheet, the follow-up that collapses it, the tells, the cost, and the honest hours it
would take to just learn the thing. See `app/schemas/content.py`.

## Stack

- Python 3.11+
- FastAPI
- PostgreSQL 15+ (with `pg_trgm`, created by the first migration)
- SQLAlchemy 2 and Alembic
- Clerk authentication
- OpenAI-compatible endpoint for guide generation (optional)
- Pexels for stock imagery (optional)
- S3-compatible storage for uploaded and generated images (optional)

Docker is not used by this project.

## Local setup

From the repository root, `npm run setup` does all of this. By hand, from `backend/`:

```powershell
python -m venv ..\.venv
..\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Create a database with credentials that work on your machine:

```powershell
createdb -U postgres canilarpit
```

Set `DATABASE_URL` in `.env`, then migrate and seed:

```powershell
python -m alembic upgrade head
canilarpit seed
```

Start the API:

```powershell
uvicorn app.main:app --reload
```

- API: `http://127.0.0.1:8000`
- Swagger UI: `/docs`
- OpenAPI JSON: `/openapi.json`
- Liveness: `/health/live` — never touches PostgreSQL
- Readiness: `/health/ready`

An unreachable database answers `503` with a message naming the fix, rather than a
`500`.

## Authentication

Clerk issues the tokens. Set:

```dotenv
CLERK_ISSUER=https://your-instance.clerk.accounts.dev
CLERK_JWKS_URL=https://your-instance.clerk.accounts.dev/.well-known/jwks.json
CLERK_WEBHOOK_SECRET=whsec_...
CLERK_AUDIENCE=
CLERK_AUTHORIZED_PARTIES=["http://localhost:5173","https://canilarpit.com"]
```

Point the `user.created`, `user.updated`, and `user.deleted` webhooks at
`/api/v1/webhooks/clerk`.

After an account signs in once and calls `GET /api/v1/me`, give it a role:

```powershell
canilarpit set-role user_clerk_id admin
```

For local frontend work, `DEV_AUTH_BYPASS=true` accepts identity headers instead of a
token, which is what the admin panel's "Local development" sign-in sends:

```text
X-Dev-Clerk-User-Id: local-admin
X-Dev-Email: developer@example.com
```

The settings validator refuses to let the bypass be enabled when `APP_ENV=production`.

`GET /api/v1/config` reports which sign-in paths are available. It returns no secrets.

## Content workflow

Reviewed guide files live in `content/guides/`. `canilarpit seed` publishes them and
creates the default categories. The CMS endpoints edit database drafts, and the export
endpoint produces the same portable JSON for Git review.

```powershell
canilarpit import-guide content/guides/naruto.json --publish
canilarpit export-guide naruto content/guides/naruto.json
```

The seed ships fifteen guides across films, drink, sport, jobs, design, and anime,
including two `DON'T` entries that exist to say the claim is not worth making.

## Guide generation

`POST /api/v1/admin/ai/generate` queues a topic and starts it immediately as a
background task. The pipeline is in `app/services/generation.py`:

1. `app/services/ai.py` asks the model for the entire guide document as one JSON object.
2. The document is validated with the CMS's own Pydantic schema. Validation errors are
   returned to the model to repair, up to `AI_MAX_REPAIR_ATTEMPTS` times.
3. Source URLs are fetched. Dead ones are dropped along with the citations that
   referenced them (`AI_VERIFY_SOURCES`).
4. Stock photographs are fetched for the image terms the guide proposed and attached to
   the draft revision, unapproved.
5. The job ends in `review` with `created_guide_id` set. Nothing is ever published
   automatically.

```dotenv
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4.1
PEXELS_API_KEY=...
```

Without `OPENAI_API_KEY` the generate endpoint answers `503` and says so; everything
else keeps working. `GET /api/v1/admin/ai/status` is what the admin panel checks before
offering the button.

Jobs can also be drained by a separate process:

```powershell
canilarpit work --limit 5
```

`app.workers.research.claim_next_research_job` claims jobs atomically with
`SKIP LOCKED` for a worker deployed elsewhere.

## Media

Stock and external assets use remote HTTPS URLs and carry their attribution and licence.
Uploaded and generated assets can go to an S3-compatible bucket through a 15-minute
presigned `PUT`:

```dotenv
S3_ENDPOINT_URL=https://your-account.r2.cloudflarestorage.com
S3_ACCESS_KEY_ID=...
S3_SECRET_ACCESS_KEY=...
S3_BUCKET=canilarpit-media
S3_REGION=auto
MEDIA_PUBLIC_BASE_URL=https://media.canilarpit.com
```

Only `approved` assets appear on a public guide page.

## Checks

```powershell
python -m ruff check .
python -m pytest
python -m alembic upgrade head --sql
```

`tests/test_api_live.py` runs the real API against PostgreSQL and skips itself when no
seeded database is reachable, so `pytest` is useful with or without one.

See [`docs/API.md`](docs/API.md) for the complete frontend contract.
