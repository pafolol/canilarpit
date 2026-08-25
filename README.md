# Can I LARP It API

FastAPI and PostgreSQL backend for a catalog of pre-generated, editor-reviewed LARP guides.
Public searches never trigger AI generation. Missing topics are counted so editors can decide what
to research next.

## Stack

- Python 3.11+
- FastAPI
- PostgreSQL 15+
- SQLAlchemy 2 and Alembic
- Clerk authentication
- Optional S3-compatible storage for uploaded and generated images

Docker is not used by this project.

## Local Setup

Create and activate a virtual environment on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Create a PostgreSQL database using credentials that are valid on your machine:

```powershell
createdb -U postgres canilarpit
```

Set `DATABASE_URL` in `.env`, then migrate and seed the database:

```powershell
python -m alembic upgrade head
canilarpit seed
```

Start the API:

```powershell
uvicorn app.main:app --reload
```

Useful URLs:

- API: `http://127.0.0.1:8000`
- Swagger UI: `http://127.0.0.1:8000/docs`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`
- Liveness: `http://127.0.0.1:8000/health/live`
- Database readiness: `http://127.0.0.1:8000/health/ready`

## Clerk

Create a Clerk application and enable the desired sign-in methods. Clerk can provide Google,
GitHub, and email/password accounts at the same time. Set these values in `.env`:

```dotenv
CLERK_ISSUER=https://your-instance.clerk.accounts.dev
CLERK_JWKS_URL=https://your-instance.clerk.accounts.dev/.well-known/jwks.json
CLERK_WEBHOOK_SECRET=whsec_...
CLERK_AUDIENCE=
CLERK_AUTHORIZED_PARTIES=["http://localhost:3000","https://canilarpit.com"]
```

`CLERK_AUDIENCE` is optional when the Clerk template does not issue an audience claim.
`CLERK_AUTHORIZED_PARTIES` should contain every frontend origin allowed to present tokens.

Configure Clerk to send `user.created`, `user.updated`, and `user.deleted` events to:

```text
https://your-api.example.com/api/v1/webhooks/clerk
```

After the first account signs in and calls `GET /api/v1/me`, assign its application role:

```powershell
canilarpit set-role user_clerk_id admin
```

For local frontend development only, `DEV_AUTH_BYPASS=true` allows these headers instead of a Clerk
token:

```text
X-Dev-Clerk-User-Id: local-user
X-Dev-Email: developer@example.com
```

The bypass cannot be enabled when `APP_ENV=production`.

## Content Workflow

Validated guide files live in `content/guides/`. The included seed command publishes those files to
PostgreSQL. The CMS endpoints can create and edit database drafts, and the export endpoint produces
the same portable JSON format for Git review.

```powershell
canilarpit import-guide content/guides/naruto.json --publish
canilarpit export-guide naruto content/guides/naruto.json
```

The seed includes one anime guide and one lifestyle guide. Content is validated with category-aware
Pydantic schemas before it can be stored or published.

## Media Storage

Stock and external assets can use remote HTTPS URLs. Generated and uploaded assets can be sent to an
S3-compatible bucket using a 15-minute presigned upload URL. Configure:

```dotenv
S3_ENDPOINT_URL=https://your-account.r2.cloudflarestorage.com
S3_ACCESS_KEY_ID=...
S3_SECRET_ACCESS_KEY=...
S3_BUCKET=canilarpit-media
S3_REGION=auto
MEDIA_PUBLIC_BASE_URL=https://media.canilarpit.com
```

## Research Jobs

The API implements the research queue and lifecycle, but no paid search, LLM, stock, or image model
provider is selected yet. An external worker can atomically claim jobs using
`app.workers.research.claim_next_research_job`, perform provider calls, and save its result. Public
searches cannot enqueue jobs.

## Quality Checks

```powershell
python -m ruff check .
python -m pytest
python -m alembic upgrade head --sql
```

See [`docs/API.md`](docs/API.md) for the complete frontend contract.
