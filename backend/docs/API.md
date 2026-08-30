# Frontend API Contract

## Conventions

The development base URL is `http://127.0.0.1:8000`. Versioned endpoints begin with `/api/v1`.
Request and response bodies use JSON. Dates use ISO 8601 UTC strings and IDs use UUID strings.

Authenticated requests send the Clerk session token as:

```http
Authorization: Bearer <clerk-session-jwt>
```

Access levels used below:

| Access | Meaning |
|---|---|
| Public | No account required; a valid token may still be sent where noted |
| Member | Any active Clerk-backed account |
| Editor | Account with application role `editor` or `admin` |
| Admin | Account with application role `admin` |
| Clerk | Signed Clerk webhook request, not called by the frontend |

Successful `DELETE` endpoints usually return `204 No Content`. Common failures are:

| Status | Meaning |
|---|---|
| `400` | Malformed webhook or signature |
| `401` | Missing, expired, or invalid Clerk token |
| `403` | Account is inactive or lacks the required role |
| `404` | Resource does not exist or is not publicly available |
| `409` | Valid request conflicts with the resource's current lifecycle state |
| `429` | Anonymous topic-request rate limit exceeded |
| `422` | Request body, query parameter, citation, or guide schema is invalid |
| `503` | Database, Clerk configuration, model provider, stock provider, or object storage is unavailable |

FastAPI validation errors use `{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}`.
Application errors use `{"detail": "Readable explanation"}`.

## Shared Responses

Paginated responses contain `items` and:

```json
{
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 42,
    "pages": 3
  }
}
```

`pages` is `0` when there are no results. Valid page sizes are `1` through `100`.

A guide card is represented as:

```json
{
  "id": "5b8a38bf-671b-4ed2-8f58-fde3d032280b",
  "slug": "naruto",
  "title": "Naruto",
  "summary": "A spoiler-heavy briefing...",
  "guide_type": "anime",
  "category": {
    "id": "7de4fdee-f5bc-4ba2-97fc-4e3b333f9ca3",
    "slug": "anime",
    "title": "Anime"
  },
  "larp": {
    "entry_type": "taste",
    "verdict": "kinda",
    "exposure_seconds": 420,
    "unfalsifiable": false,
    "flags": ["LONG CANON", "SPOILER HEAVY"],
    "dek": "The plot is public and the summaries are excellent."
  },
  "published_at": "2026-08-23T12:00:00Z"
}
```

`larp` is denormalized from the published revision so a card never has to open the
document. Its three clock states are mutually exclusive:

| State | Shape | Meaning |
|---|---|---|
| Countdown | `exposure_seconds` >= 30, `unfalsifiable` false | Seconds of conversation before exposure |
| Indefinite | `exposure_seconds` null, `unfalsifiable` true | Nothing about the claim is checkable |
| Stopped | `exposure_seconds` null, `unfalsifiable` false | Only on `verdict: "dont"`; no clock runs |

Guide types are `anime`, `lifestyle`, and `general`. Entry types are `scene`, `taste`,
and `role`.

Verdicts are `yes`, `kinda`, `talk_only`, and `dont`. Three of the four are a yes:
`talk_only` means the conversation holds and the doing does not, which is a finding
rather than a refusal. `dont` is reserved for claims that endanger or defraud someone,
and those entries carry no crib sheet by design. Media kinds are
`stock`, `external`, `generated`, and `uploaded`. Approval states are `draft`,
`approved`, `rejected`, and `broken`.

## Health

### `GET /health/live`

Access: Public.

Confirms that the Python process is running. It does not access PostgreSQL and is suitable for a
process liveness check.

Success `200`:

```json
{"status": "ok"}
```

### `GET /health/ready`

Access: Public.

Executes `SELECT 1` against PostgreSQL. Use it for deployment readiness, not continuous frontend
polling.

Success `200`: `{"status": "ready"}`.

Failure `503`: PostgreSQL cannot be reached.

## Public Catalog

### `GET /api/v1/config`

Access: Public.

Reports which sign-in paths the deployment offers so the admin panel can render the
right form. It returns no secrets.

Success `200`:

```json
{"app_env": "development", "dev_auth_bypass": true, "clerk_configured": false}
```

### `GET /api/v1/categories`

Access: Public.

Returns active categories in display order. Each category includes `published_guide_count`, allowing
the frontend to hide empty categories or display counts without an additional query.

Success `200`:

```json
[
  {
    "id": "7de4fdee-f5bc-4ba2-97fc-4e3b333f9ca3",
    "slug": "anime",
    "title": "Anime",
    "description": "Plot, character, ending, and fandom guides.",
    "sort_order": 10,
    "published_guide_count": 1
  }
]
```

### `GET /api/v1/guides`

Access: Public.

Returns published guide cards. Drafts, review revisions, and archived guides cannot appear here.

Query parameters:

| Parameter | Type | Behavior |
|---|---|---|
| `q` | string, optional | Searches titles, summaries, fuzzy title matches, and aliases |
| `category` | slug, optional | Filters by category slug such as `anime` |
| `guide_type` | enum, optional | Filters by `anime`, `lifestyle`, or `general` |
| `entry_type` | enum, repeatable | Filters by `scene`, `taste`, or `role` |
| `verdict` | enum, repeatable | Filters by `yes`, `kinda`, `not_really`, or `dont` |
| `sort` | enum | `relevance`, `newest`, or `title`; defaults to `relevance` |
| `page` | integer | One-based page; defaults to `1` |
| `page_size` | integer | Defaults to `20`, maximum `100` |

`entry_type` and `verdict` accept repeated values. Values inside one parameter widen the
result; the two parameters intersect. `?verdict=dont&entry_type=role` returns roles you
should not claim.

When `q` is absent, `relevance` behaves like newest-first. Search is read-only and does not create a
guide, topic request, or account history entry.

Success `200`: paginated guide cards.

Frontend behavior: if `items` is empty, explicitly call `POST /api/v1/topic-requests` only after the
user chooses to request that topic. Do not call the topic request endpoint on every keystroke.

### `GET /api/v1/guides/{slug}`

Access: Public.

Returns the current published revision of one guide. The route uses a stable slug such as `naruto`.

Important response fields:

| Field | Purpose |
|---|---|
| `id` | Stable guide UUID used by save and history endpoints |
| `revision_id` | Exact published content revision |
| `revision_number` | Increasing human-readable revision number |
| `larp` | The verdict layer, identical in shape to the card's |
| `content` | Category-specific content object rendered by `content.kind` |
| `aliases` | Alternative names for display or SEO |
| `sources` | Citations referenced by content fact items |
| `media` | Approved images only, already ordered by `sort_order` |
| `last_verified_at` | When factual content was last reviewed |

Anime content includes `premise`, `ending_summary`, `characters`, `major_events`, and
`fandom_debates`. Lifestyle content includes `aesthetic`, `brands`, `visual_cues`, `locations`, and
`media_scenarios`. All content types also include `larp`, `overview`, `quick_brief`,
`essential_facts`, `talking_points`, `vocabulary`, `common_mistakes`, and `questions`.

`content.larp` is the full profile. Beyond the card fields it carries `crib` (sections of
`heading` and `lines`), `surface`, `follow_up`, `tells`, `cost`, and
`learn` (`hours`, `book`, `make`). A `dont` entry still carries every field; the frontend
drops its crib sheet and opens on `cost` instead.

Media contains `url`, `alt_text`, attribution and license fields, placement `role`, `caption`, and
`sort_order`. The frontend should show attribution when supplied and should mark generated media
using `kind === "generated"`.

Failure `404`: no published guide has this slug.

### `GET /api/v1/guides/{slug}/related`

Access: Public.

Returns published guide cards in the same category, newest first. The current guide is excluded.

Query parameter `limit` defaults to `6` and accepts `1` through `20`.

Success `200`: an array of guide cards, which may be empty.

Failure `404`: the source guide is not published or does not exist.

### `POST /api/v1/topic-requests`

Access: Public.

Records demand for a topic that is not in the catalog. Repeated normalized topics increment the same
counter. Punctuation, capitalization, and repeated spaces do not create separate topics.
The endpoint is limited to 10 requests per minute per client IP. It intentionally stores no client
IP or account association.

Request:

```json
{"topic": "Attack on Titan"}
```

If no exact title, slug, or alias exists, success `200` returns:

```json
{
  "topic": "Attack on Titan",
  "normalized_topic": "attack on titan",
  "request_count": 7,
  "recorded": true,
  "matching_guide": null
}
```

If a guide already exists, `recorded` is `false`, `request_count` is `null`, and `matching_guide`
contains the guide card. The frontend should navigate to that guide instead of showing a requested
confirmation.

## Account

### `GET /api/v1/me`

Access: Member.

Returns the application user corresponding to the Clerk token. On the first authenticated call, the
backend creates a local `member` record if the Clerk webhook has not already done so.

Success `200` includes `id`, `clerk_user_id`, `email`, `display_name`, `avatar_url`, `role`, and
`created_at`.

### `GET /api/v1/me/history`

Access: Member.

Returns published guides the user explicitly recorded as viewed, ordered by most recent view.

Query parameters: `page` and `page_size`.

Each item contains a guide card, `first_viewed_at`, `last_viewed_at`, and `view_count`.

### `PUT /api/v1/me/history/{guide_id}`

Access: Member.

Records one guide view. The operation is an upsert: the first call creates the history row and later
calls increment `view_count` and refresh `last_viewed_at`.

Request body: none.

Success `200`: the updated history item.

Frontend behavior: call this after a published guide page has successfully loaded, not before. It is
safe to retry, but each successful retry counts as another view.

Failure `404`: the UUID is missing, draft-only, or archived.

### `DELETE /api/v1/me/history/{guide_id}`

Access: Member.

Removes one guide from the user's history. The operation is idempotent and returns `204` even when no
history row existed.

### `DELETE /api/v1/me/history`

Access: Member.

Clears all guide-view history for the current user. Returns `204`.

### `GET /api/v1/me/saved`

Access: Member.

Returns saved published guides, ordered by when they were saved. Query parameters are `page` and
`page_size`. Each item contains `guide` and `saved_at`.

### `PUT /api/v1/me/saved/{guide_id}`

Access: Member.

Saves a published guide. This endpoint is idempotent: saving an already saved guide returns the
existing record without changing its original `saved_at` value.

Request body: none. Success `200`: `{"guide": <guide card>, "saved_at": "..."}`.

Failure `404`: the guide is not currently published.

### `DELETE /api/v1/me/saved/{guide_id}`

Access: Member.

Removes a saved guide. The operation is idempotent and returns `204`.

### `GET /api/v1/me/search-history`

Access: Member.

Returns explicitly recorded searches newest first. Query parameters are `page` and `page_size`.

Each item includes `id`, the original `query`, optional `matched_guide_id`, and `created_at`.

### `POST /api/v1/me/search-history`

Access: Member.

Records a search in the user's private account history. Public `GET /guides` does not do this
automatically.

Request:

```json
{
  "query": "Naruto Shippuden",
  "matched_guide_id": "5b8a38bf-671b-4ed2-8f58-fde3d032280b"
}
```

`matched_guide_id` may be omitted when there was no selected result. When supplied, it must identify
a published guide. Success `201`: the created search-history row.

### `DELETE /api/v1/me/search-history`

Access: Member.

Clears all search history for the current user and returns `204`.

## Editorial Guides

### `GET /api/v1/admin/guides`

Access: Editor.

Returns all guide states for the CMS, ordered by latest update. Query parameters are `status`, `page`,
and `page_size`. Valid statuses are `draft`, `in_review`, `published`, and `archived`.

Each guide contains `current_revision` and `draft_revision`. Either can be `null`. A revision includes
the complete validated `document`, its `content_hash`, lifecycle status, timestamps, and all linked
media including unapproved media. This is intentionally richer than the public response.

### `POST /api/v1/admin/guides`

Access: Editor.

Creates a new guide identity and revision 1 in `draft` state. The request body is a complete
`GuideDocument`, described in the Guide Document section below. Slugs are unique.

Success `201`: the complete admin guide response.

Failure `409`: another guide already has the slug. Failure `422`: category or document is invalid.

### `POST /api/v1/admin/guides/import`

Access: Editor.

Imports the same complete JSON document used by version-controlled files. If the slug is new, a guide
is created. If it exists, its editable draft is replaced or a new draft revision is created.

Query parameter `publish` defaults to `false`. `publish=true` also publishes the imported revision
and therefore requires the caller to have the `admin` role. Editors can import a draft but cannot use
this convenience route to bypass administrative publication review.

Success `200`: the complete admin guide response.

### `GET /api/v1/admin/guides/{guide_id}`

Access: Editor.

Returns one CMS guide by UUID, including its current published revision, editable draft revision, and
revision media.

Failure `404`: guide UUID does not exist.

### `PUT /api/v1/admin/guides/{guide_id}/draft`

Access: Editor.

Replaces the complete editable draft document. This is full-document saving rather than JSON Patch.
If the guide has only a published revision, the endpoint creates the next draft revision and copies
its media placements. If a draft already exists, that draft is updated in place.

The document slug must equal the guide's existing slug. Published metadata does not change until the
draft is published.

Success `200`: updated admin guide. Failure `422`: validation, citation, category, or slug error.

### `POST /api/v1/admin/guides/{guide_id}/validate`

Access: Editor.

Re-runs Pydantic validation for the current draft and returns the deterministic SHA-256
`content_hash` and normalized document. Request body: none.

Success `200`: `{"valid": true, "content_hash": "...", "document": {...}}`.

Failure `409`: there is no editable draft.

### `POST /api/v1/admin/guides/{guide_id}/submit-for-review`

Access: Editor.

Moves the latest draft revision to `in_review`. Published content remains public while a replacement
revision is reviewed. Request body: none.

Success `200`: updated admin guide. Failure `409`: no draft exists.

### `POST /api/v1/admin/guides/{guide_id}/publish`

Access: Admin.

Publishes a draft or review revision. The previous published revision becomes `superseded`, the guide
metadata and aliases are replaced from the document, and public routes immediately use the selected
revision.

Request:

```json
{"revision_id": "ca4e28ca-f540-4140-8bf8-97e905a1f9be"}
```

`revision_id` may be `null`; the backend then chooses the newest draft or review revision.

Success `200`: updated admin guide. Failure `404`: revision is absent. Failure `409`: revision is
already published, superseded, or otherwise not publishable.

### `POST /api/v1/admin/guides/{guide_id}/archive`

Access: Admin.

Archives a guide and removes it from every public catalog endpoint. Content and account references
remain in PostgreSQL. Request body: none. Success `204`.

### `GET /api/v1/admin/guides/{guide_id}/export`

Access: Editor.

Returns a portable `GuideDocument` suitable for saving to `content/guides/{slug}.json` and reviewing
in Git.

Optional query parameter `revision_id` selects an exact revision. Without it, the latest revision is
exported, which may be an unpublished draft.

## Guide Document

Every create, import, draft-save, and export operation uses this top-level shape:

```json
{
  "schema_version": 1,
  "slug": "naruto",
  "title": "Naruto",
  "summary": "At least ten characters",
  "guide_type": "anime",
  "category_slug": "anime",
  "aliases": ["Naruto Shippuden"],
  "content": {
    "kind": "anime",
    "larp": {
      "entry_type": "taste",
      "verdict": "kinda",
      "exposure_seconds": 420,
      "unfalsifiable": false,
      "flags": ["LONG CANON"],
      "dek": "One sentence under the title.",
      "crib": [{"heading": "References", "lines": ["One line worth saying."]}],
      "surface": ["What passes on first contact."],
      "follow_up": ["\"Which episode did you stop on?\"", "Why that question works."],
      "tells": ["You summarise arcs. Viewers quote lines."],
      "cost": ["What happens when you are caught."],
      "learn": {"hours": 90, "book": "One book", "make": "One thing to do"}
    }
  },
  "sources": [
    {
      "key": "official-source",
      "title": "Source title",
      "url": "https://example.com/source",
      "publisher": "Publisher",
      "excerpt": null,
      "published_at": null,
      "verified_at": "2026-08-23T00:00:00Z"
    }
  ],
  "last_verified_at": "2026-08-23T00:00:00Z"
}
```

Citation strings in facts, anime events, and lifestyle brands must match a source `key`. Duplicate
aliases and sources are rejected or normalized. `content.kind` must equal `guide_type`.

`content.image_brief` is a list of up to ten `{provider, query, subject, role, note}`
objects naming what to illustrate the guide with and where to find it. `provider` is
`auto` or one of the ids from `GET /admin/media/providers`.

`role` places the picture: `hero` is the top of the page, `gallery` is the strip at the
end, and `crib`, `surface`, `follow-up`, `tells`, `brief`, `words`, `asked`, `cost` and
`learn` put it under that section. Images without a section are spread evenly through
the article, so a reader meets a picture beside the point it belongs to. It may be empty, in which case the backend infers a brief from the title and
any visual cues.

`content.larp` is required. Its clock rules are enforced at validation time: a `dont`
verdict must have `exposure_seconds: null`, `unfalsifiable: true` forbids a clock, and
any other verdict requires `exposure_seconds` of at least 30. A `422` naming
`content.<kind>.larp.exposure_seconds` means one of those three was broken.

Use the generated OpenAPI schema for every nested content field. The two files in `content/guides/`
are complete working examples for anime and lifestyle documents.

## Editorial Media

### `GET /api/v1/admin/media`

Access: Editor.

Returns recently created media assets. Optional `status` filters by approval state. `limit` defaults
to `50` and accepts up to `200`.

This endpoint returns assets independently from guide placement. `link_id`, `role`, and `caption` are
therefore `null` here.

### `POST /api/v1/admin/media`

Access: Editor.

Creates media metadata after selecting a stock/external image or uploading/generated an object.

Example stock asset:

```json
{
  "kind": "stock",
  "provider": "pexels",
  "remote_url": "https://images.example.com/watch.jpg",
  "storage_key": null,
  "source_page_url": "https://www.pexels.com/photo/example",
  "attribution": "Photo by Example Creator",
  "license_name": "Pexels License",
  "license_url": "https://www.pexels.com/license/",
  "alt_text": "Mechanical wristwatch in natural window light",
  "width": 1600,
  "height": 1067,
  "metadata": {},
  "approval_status": "draft"
}
```

`stock` and `external` require `remote_url`. `generated` and `uploaded` require `storage_key` or a
remote URL. Generated-image prompt, model, and seed should be kept in `metadata`.

Success `201`: media response.

### `PATCH /api/v1/admin/media/{media_id}/approval`

Access: Editor.

Changes whether an asset is usable publicly.

Request: `{"approval_status": "approved"}`.

Only approved assets appear in `GET /guides/{slug}`. Rejecting or marking a currently linked image as
broken hides it without deleting its editorial placement.

### `POST /api/v1/admin/media/uploads/presign`

Access: Editor.

Creates a 15-minute S3-compatible `PUT` URL. Object storage must be configured.

Request:

```json
{
  "filename": "watch.webp",
  "content_type": "image/webp",
  "kind": "uploaded"
}
```

Success `200` includes `upload_url`, `storage_key`, optional `public_url`, and
`required_headers`. The frontend must upload the raw file directly to `upload_url` using `PUT` and
the exact required headers. After upload succeeds, call `POST /admin/media` with the returned
`storage_key`.

Failure `503`: storage credentials or bucket are not configured.

### `POST /api/v1/admin/guides/{guide_id}/draft/media`

Access: Editor.

Places an existing media asset in the guide's draft revision. If the guide only has a published
revision, a new draft is created and existing media placements are copied first.

Request:

```json
{
  "media_asset_id": "0a9a66b7-2c22-49d9-93ba-caf6617e956b",
  "role": "hero",
  "caption": "Travel-watch visual reference",
  "sort_order": 0
}
```

The combination of draft revision, asset, and role is idempotent. Repeating it updates caption and
order. Success `200` includes a non-null `link_id`, which is required to remove that placement.

### `DELETE /api/v1/admin/guides/{guide_id}/draft/media/{link_id}`

Access: Editor.

Removes one placement from the editable draft without deleting the reusable media asset. Returns
`204`.

Failure `409`: no editable draft. Failure `404`: link is not part of that draft.

## Topic Demand

### `GET /api/v1/admin/topic-requests`

Access: Editor.

Returns missing topics ordered by highest `request_count`, then most recent request. Query parameters
are `page` and `page_size`. This is the editorial backlog and does not automatically enqueue paid
research.

Each item contains `topic`, `normalized_topic`, `request_count`, `first_requested_at`, and
`last_requested_at`.

## Guide Generation

### `GET /api/v1/admin/ai/status`

Access: Editor.

Reports whether generation and stock imagery are configured, so the panel can disable
what will not work.

Success `200`:

```json
{
  "text_provider": "openai",
  "text_model": "gpt-4.1",
  "text_configured": true,
  "images_configured": true,
  "image_providers": [
    {
      "id": "tvmaze",
      "title": "TVmaze",
      "subjects": "Television series, their characters and their episodes",
      "configured": true,
      "requires_key": false,
      "editorial_only": true
    }
  ],
  "storage_configured": false
}
```

`images_configured` is true whenever at least one provider can be reached. Four of the
seven need no key, so it is normally true even on a fresh install.

### `POST /api/v1/admin/ai/generate`

Access: Editor.

Queues one topic and starts the run immediately as a background task inside the API
process.

Request:

```json
{
  "topic": "Attack on Titan",
  "guide_type": "anime",
  "entry_type": "taste",
  "category_slug": "anime",
  "instructions": "Include the ending and the major deaths.",
  "attach_images": true
}
```

`attach_images` runs the generated document's own `image_brief` through the provider
registry and places what it finds on the draft, unapproved.

Every field except `topic` is optional; a null `guide_type`, `entry_type`, or
`category_slug` lets the model choose.

Success `202`: the research job. Poll `GET /admin/research-jobs/{id}` until `status`
leaves `queued` and `running`. A finished run has `status: "review"`,
`created_guide_id` set, and a `result` object containing `revision_id`, `attempts`,
token counts, `attached_media`, and any `warnings` (dropped dead sources, or stock
imagery that could not be fetched).

The generated revision is a **draft**. Publishing it is a separate, admin-only call.

Failure `503`: `OPENAI_API_KEY` is not configured. Failure `422`: `category_slug` does
not exist.

### `POST /api/v1/admin/research-jobs/{job_id}/run`

Access: Editor.

Runs an already-queued job now rather than waiting for an external worker.

Success `202`: the job. Failure `409`: the job is not `queued`.

### `GET /api/v1/admin/media/providers`

Access: Editor.

Lists the image sources this deployment can reach and what each is good for. The
`subjects` string is the same text the model is given when it writes an image brief.

Success `200`: an array of `{id, title, subjects, configured, requires_key,
editorial_only}`.

Providers are `pexels`, `wikimedia`, `tmdb`, `tvmaze`, `anilist`, `jikan` and `fanart`.
`wikimedia`, `tvmaze`, `anilist` and `jikan` need no key.

### `GET /api/v1/admin/media/image-search`

Access: Editor.

Searches one image provider.

| Parameter | Type | Behavior |
|---|---|---|
| `q` | string, 2-200 | The search term |
| `provider` | enum | A provider id, or `auto` to choose by category |
| `guide_type` | string, optional | Informs `auto` |
| `category` | string, optional | Informs `auto` |
| `limit` | integer | 1 to 40, default 12 |

Success `200`:

```json
{
  "query": "Breaking Bad",
  "provider": "tvmaze",
  "results": [
    {
      "provider": "tvmaze",
      "remote_url": "https://static.tvmaze.com/uploads/images/original_untouched/0/2404.jpg",
      "preview_url": "https://static.tvmaze.com/uploads/images/medium_portrait/0/2404.jpg",
      "source_page_url": "https://www.tvmaze.com/characters/1/breaking-bad-walter-white",
      "attribution": "Walter White, Breaking Bad, via TVmaze",
      "license_name": "Editorial use; rights held by the copyright owner",
      "license_url": "https://www.tvmaze.com/api",
      "alt_text": "Walter White in Breaking Bad",
      "width": null,
      "height": null,
      "subject": "Walter White",
      "editorial_only": true
    }
  ],
  "warnings": ["Pexels is not configured (PEXELS_API_KEY)"]
}
```

`editorial_only` marks promotional material: usable with credit, rights held by the
copyright owner. The admin panel labels these and the public page prints the licence.

Fallback is constrained by family. `pexels` and `wikimedia` substitute for each other;
`tmdb`, `tvmaze` and `fanart` substitute for each other; `anilist` and `jikan`
substitute for each other. A film database never falls back to a photo library, because
the result would be a picture of the wrong thing. `warnings` explains every provider
that was tried and skipped.

Failure `422`: unknown provider. Failure `503`: nothing in the family could answer, with
the reasons in `detail`.

The frontend posts a chosen result to `POST /admin/media` and then places it with
`POST /admin/guides/{guide_id}/draft/media`.

## Research Jobs

Research job states are `queued`, `running`, `review`, `completed`, `failed`, and `cancelled`.
`POST /admin/ai/generate` is the normal way to create one; the routes below manage jobs
created by hand or driven by an external worker.

### `GET /api/v1/admin/research-jobs`

Access: Editor.

Returns jobs newest first. Optional `status` filters by lifecycle state. `page` and `page_size`
control pagination.

### `POST /api/v1/admin/research-jobs`

Access: Editor.

Explicitly queues research. This route is never called by public search.

Request:

```json
{
  "topic": "Attack on Titan",
  "guide_type": "anime",
  "instructions": "Include the ending and major character deaths.",
  "provider_config": {}
}
```

Success `202`: queued job. `provider_config` must not contain API secrets because it is returned to
editors and stored as ordinary JSON.

### `GET /api/v1/admin/research-jobs/{job_id}`

Access: Editor.

Returns one job including provider configuration, result, error, attempt count, estimated cost in
millionths of a US dollar, `created_guide_id`, and timestamps.

Failure `404`: job does not exist.

### `POST /api/v1/admin/research-jobs/{job_id}/retry`

Access: Editor.

Moves a `failed` or `cancelled` job back to `queued`, clears its error and execution timestamps, and
preserves its prior result and attempt count for auditing. Request body: none.

Failure `409`: job is not failed or cancelled.

### `POST /api/v1/admin/research-jobs/{job_id}/start`

Access: Editor.

Moves a queued job to `running`, increments `attempt_count`, and sets `started_at`. This can be used by
a manually operated research integration; a database worker may instead claim jobs atomically.

Failure `409`: job is not queued.

### `POST /api/v1/admin/research-jobs/{job_id}/cancel`

Access: Editor.

Cancels a queued or running job and sets `finished_at`. Request body: none.

Failure `409`: job has already reached review, completed, failed, or cancelled state.

### `POST /api/v1/admin/research-jobs/{job_id}/complete`

Access: Editor.

Records output from a worker or manual research process.

Request:

```json
{
  "status": "review",
  "result": {"draft_document": {}},
  "error_message": null,
  "estimated_cost_micros": 25000
}
```

Allowed target statuses are `review`, `completed`, and `failed`. A failed result requires
`error_message`. The endpoint stores arbitrary result JSON but does not automatically publish or
convert it into a guide; an editor must review it and use the guide create/import endpoint.

## Clerk Webhook

### `POST /api/v1/webhooks/clerk`

Access: Clerk-signed webhook only.

Synchronizes user creation, profile updates, and soft deletion. The backend verifies Svix headers
using `CLERK_WEBHOOK_SECRET` and records event IDs so retries are idempotent.

Success `200` returns `{"processed": true}` for a new event and `{"processed": false}` for a
previously processed retry.

The frontend must never call this endpoint directly.

## Recommended Frontend Flows

Public search flow: call `GET /guides?q=...`, render guide cards, and offer a request button only when
empty. The button calls `POST /topic-requests` once.

Guide page flow: call `GET /guides/{slug}`. If signed in, call `PUT /me/history/{guide.id}` after the
guide response succeeds. Save and unsave with `PUT` and `DELETE /me/saved/{guide.id}`.

CMS flow: create or load a guide, save the entire document with `PUT /draft`, manage media assets and
placements separately, validate, submit for review, and let an admin publish the exact revision.

Generation flow: `POST /admin/ai/generate`, poll the job, open `created_guide_id` in the
editor, review and correct the draft, approve the images you want, then publish.

Authentication flow: use Clerk frontend components and SDKs. Obtain a session token with Clerk's
token method and attach it as a Bearer token to member/editor/admin requests. Do not send passwords to
FastAPI.
