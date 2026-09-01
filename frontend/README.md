# canilarpit — frontend

Can you larp it, and for how long?

```bash
npm run dev
```

Vite + React + React Router. Every entry comes from the API; nothing here holds its own
copy of the content.

## Layout

| File | What it holds |
|---|---|
| `src/api.ts` | The only module that talks to the backend: types, client, error shapes |
| `src/data.ts` | Display vocabulary — verdict labels, type glyphs, gauge levels — and site copy |
| `src/components.tsx` | The shared interface: verdict badge, exposure clock, search, filters, cards |
| `src/Home.tsx` | Search, filters, and the grid |
| `src/Entry.tsx` | One guide: crib sheet, follow-up, tells, cost, and the clock that runs while you read |
| `src/auth.tsx` | Admin credentials — the session cookie from password sign-in, or the local dev identity headers |
| `src/admin/` | The editor panel: catalog, generation, guide editor, images |

Routes: `/` (home), `/entry/{slug}`, `/category/{slug}`, `/submit`, `/thanks`, `/faq`,
`/privacy`, `/just-learn-it`, `/admin/*`. Anything else is a real 404.

## Talking to the API

The dev server proxies `/api` and `/health` to `VITE_API_PROXY`
(`http://127.0.0.1:8000` by default), so the client only ever uses relative paths and
development needs no CORS. In production, set `VITE_API_BASE_URL` when the API is on a
different origin.

```bash
cp .env.example .env
```

## The admin panel

`/admin` needs an account with the `editor` or `admin` role.

Sign-in is email and password. Accounts are made by an administrator — from the
panel's **Editors** tab, or with `canilarpit create-user you@example.com --role admin`
on the backend. There is no registration screen to add one from here.

While the API runs with `DEV_AUTH_BYPASS=true`, the sign-in screen additionally offers
a "Local development" option that sends identity headers instead of a password. The
first sign-in creates a `member`; promote it once from the backend with
`canilarpit set-role <email> admin`.
