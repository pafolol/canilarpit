/**
 * The one place that talks to the backend.
 *
 * Everything is relative by default so the Vite dev proxy handles it; set
 * VITE_API_BASE_URL when the API lives on another origin in production.
 */

const BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
const V1 = `${BASE}/api/v1`;

/* ---------------------------------------------------------------- types */

export type Verdict = "yes" | "kinda" | "talk_only" | "dont";
export type EntryType = "scene" | "taste" | "role";
export type GuideType = "anime" | "lifestyle" | "general";
export type GuideStatus = "draft" | "in_review" | "published" | "archived";
export type RevisionStatus = "draft" | "in_review" | "published" | "superseded";
export type ApprovalStatus = "draft" | "approved" | "rejected" | "broken";
export type MediaKind = "stock" | "external" | "generated" | "uploaded";
export type JobStatus = "queued" | "running" | "review" | "completed" | "failed" | "cancelled";

/** seconds to exposure, "indefinite" when nothing is checkable, null on a DON'T */
export type Clock = number | "indefinite" | null;

export type CategorySummary = { id: string; slug: string; title: string };

export type Category = CategorySummary & {
  description: string;
  sort_order: number;
  published_guide_count: number;
};

export type LarpCard = {
  entry_type: EntryType;
  verdict: Verdict;
  exposure_seconds: number | null;
  unfalsifiable: boolean;
  flags: string[];
  dek: string;
};

export type GuideCard = {
  id: string;
  slug: string;
  title: string;
  summary: string;
  guide_type: GuideType;
  category: CategorySummary;
  larp: LarpCard;
  published_at: string | null;
};

export type CribSection = { heading: string; lines: string[] };

export type ImageProviderId =
  | "auto"
  | "pexels"
  | "wikimedia"
  | "tmdb"
  | "tvmaze"
  | "anilist"
  | "jikan"
  | "fanart";

/** One picture the guide asked for, and which source was told to find it. */
export type ImageQuery = {
  provider: ImageProviderId;
  query: string;
  subject: string | null;
  /** "hero", "gallery", or the id of the section the picture illustrates. */
  role: string;
  note: string | null;
};

/** The move that survives the question, and how far it actually carries. */
export type Counter = { move: string; holds: string };

export type FollowUp = {
  question: string;
  why: string;
  /** null when the entry honestly has no answer to its own question. */
  counter: Counter | null;
};

export type LarpProfile = LarpCard & {
  crib: CribSection[];
  surface: string[];
  follow_up: FollowUp;
  tells: string[];
  cost: string[];
  learn: { hours: number; book: string; make: string };
};

export type FactItem = { fact: string; citations: string[] };
export type TalkingPoint = { opener: string; follow_up: string; context: string | null };
export type VocabularyItem = { term: string; meaning: string; example: string | null };
export type QuestionAnswer = { question: string; answer: string };

export type GuideContent = {
  kind: GuideType;
  larp: LarpProfile;
  image_brief: ImageQuery[];
  overview: string;
  quick_brief: string[];
  essential_facts: FactItem[];
  talking_points: TalkingPoint[];
  vocabulary: VocabularyItem[];
  common_mistakes: string[];
  questions: QuestionAnswer[];
  extra_sections: { key: string; title: string; body: string }[];
  spoiler_warning: boolean;
  // anime
  premise?: string;
  ending_summary?: string | null;
  characters?: { name: string; role: string; fate: string | null; relationships: string[] }[];
  major_events?: { title: string; description: string; spoiler_level: string; citations: string[] }[];
  fandom_debates?: string[];
  // lifestyle
  aesthetic?: string;
  brands?: { name: string; significance: string; typical_price: string | null; citations: string[] }[];
  visual_cues?: string[];
  locations?: string[];
  media_scenarios?: {
    title: string;
    description: string;
    search_terms: string[];
    generation_prompt: string | null;
  }[];
  // general
  key_people?: string[];
  timeline?: string[];
};

export type SourceRef = {
  key: string;
  title: string;
  url: string;
  publisher: string | null;
  excerpt: string | null;
  published_at: string | null;
  verified_at: string | null;
};

export type Media = {
  id: string;
  link_id: string | null;
  kind: MediaKind;
  provider: string;
  url: string | null;
  source_page_url: string | null;
  attribution: string | null;
  license_name: string | null;
  license_url: string | null;
  alt_text: string;
  width: number | null;
  height: number | null;
  metadata: Record<string, unknown>;
  approval_status: ApprovalStatus;
  role: string | null;
  caption: string | null;
  sort_order: number | null;
};

export type GuideDetail = GuideCard & {
  revision_id: string;
  revision_number: number;
  content: GuideContent;
  aliases: string[];
  sources: SourceRef[];
  media: Media[];
  last_verified_at: string | null;
};

export type Pagination = { page: number; page_size: number; total: number; pages: number };
export type Page<T> = { items: T[]; pagination: Pagination };

export type TopicRequestResult = {
  topic: string;
  normalized_topic: string;
  request_count: number | null;
  recorded: boolean;
  matching_guide: GuideCard | null;
};

export type SiteConfig = {
  app_env: string;
  dev_auth_bypass: boolean;
  clerk_configured: boolean;
};

export type GuideDocument = {
  schema_version: 1;
  slug: string;
  title: string;
  summary: string;
  guide_type: GuideType;
  category_slug: string;
  aliases: string[];
  content: GuideContent;
  sources: SourceRef[];
  last_verified_at: string | null;
};

export type AdminRevision = {
  id: string;
  revision_number: number;
  status: RevisionStatus;
  content_hash: string;
  document: GuideDocument;
  media: Media[];
  created_at: string;
  updated_at: string;
  published_at: string | null;
};

export type AdminGuide = {
  id: string;
  slug: string;
  title: string;
  summary: string;
  guide_type: GuideType;
  status: GuideStatus;
  category: CategorySummary;
  current_revision_id: string | null;
  current_revision: AdminRevision | null;
  draft_revision: AdminRevision | null;
  published_at: string | null;
  created_at: string;
  updated_at: string;
};

export type ResearchJob = {
  id: string;
  topic: string;
  normalized_topic: string;
  guide_type: GuideType | null;
  status: JobStatus;
  instructions: string | null;
  provider_config: Record<string, unknown>;
  result: Record<string, unknown> | null;
  error_message: string | null;
  attempt_count: number;
  estimated_cost_micros: number;
  created_guide_id: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
};

export type TopicRequestRow = {
  id: string;
  topic: string;
  normalized_topic: string;
  request_count: number;
  first_requested_at: string;
  last_requested_at: string;
};

export type ImageProviderInfo = {
  id: string;
  title: string;
  subjects: string;
  configured: boolean;
  requires_key: boolean;
  editorial_only: boolean;
};

export type AiStatus = {
  text_provider: string;
  text_model: string;
  text_configured: boolean;
  image_providers: ImageProviderInfo[];
  images_configured: boolean;
  storage_configured: boolean;
};

export type ImageCandidate = {
  provider: string;
  remote_url: string;
  preview_url: string | null;
  source_page_url: string | null;
  attribution: string | null;
  license_name: string | null;
  license_url: string | null;
  alt_text: string;
  width: number | null;
  height: number | null;
  subject: string | null;
  /** Promotional art: usable with credit, but the rights are someone else's. */
  editorial_only: boolean;
};

export type ImageSearchResult = {
  query: string;
  provider: string;
  results: ImageCandidate[];
  warnings: string[];
};

/* ---------------------------------------------------------------- plumbing */

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/** Set by the auth context so admin calls carry credentials. */
let authHeaderProvider: () => Record<string, string> = () => ({});

export function setAuthHeaderProvider(provider: () => Record<string, string>) {
  authHeaderProvider = provider;
}

function readableDetail(detail: unknown, status: number): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // FastAPI validation errors: name the field so the editor can find it.
    return detail
      .map((item) => {
        const where = Array.isArray(item?.loc) ? item.loc.slice(1).join(".") : "";
        return where ? `${where}: ${item.msg}` : String(item?.msg ?? item);
      })
      .join("; ");
  }
  return `Request failed with status ${status}`;
}

async function request<T>(path: string, init: RequestInit = {}, authed = false): Promise<T> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...(init.body ? { "Content-Type": "application/json" } : {}),
    ...(authed ? authHeaderProvider() : {}),
    ...((init.headers as Record<string, string>) ?? {}),
  };

  let response: Response;
  try {
    response = await fetch(path, { ...init, headers });
  } catch {
    throw new ApiError(0, null, "The API did not respond. Is the backend running?");
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const body = text ? safeJson(text) : null;
  if (!response.ok) {
    const detail = (body as { detail?: unknown } | null)?.detail ?? body;
    throw new ApiError(response.status, detail, readableDetail(detail, response.status));
  }
  return body as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function query(params: Record<string, string | number | boolean | string[] | undefined | null>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      for (const item of value) if (item) search.append(key, item);
    } else {
      search.set(key, String(value));
    }
  }
  const rendered = search.toString();
  return rendered ? `?${rendered}` : "";
}

/* ---------------------------------------------------------------- public */

export type GuideQuery = {
  q?: string;
  category?: string;
  guide_type?: GuideType;
  entry_type?: EntryType[];
  verdict?: Verdict[];
  sort?: "relevance" | "newest" | "title";
  page?: number;
  page_size?: number;
};

export const api = {
  config: () => request<SiteConfig>(`${V1}/config`),
  categories: () => request<Category[]>(`${V1}/categories`),
  guides: (params: GuideQuery = {}) => request<Page<GuideCard>>(`${V1}/guides${query(params)}`),
  guide: (slug: string) => request<GuideDetail>(`${V1}/guides/${encodeURIComponent(slug)}`),
  related: (slug: string, limit = 6) =>
    request<GuideCard[]>(`${V1}/guides/${encodeURIComponent(slug)}/related${query({ limit })}`),
  requestTopic: (topic: string) =>
    request<TopicRequestResult>(`${V1}/topic-requests`, {
      method: "POST",
      body: JSON.stringify({ topic }),
    }),

  /* -------------------------------------------------------------- account */
  me: () => request<{ id: string; role: string; email: string | null; display_name: string | null }>(
    `${V1}/me`,
    {},
    true,
  ),

  /* -------------------------------------------------------------- admin */
  admin: {
    aiStatus: () => request<AiStatus>(`${V1}/admin/ai/status`, {}, true),
    generate: (payload: {
      topic: string;
      guide_type?: GuideType | null;
      entry_type?: EntryType | null;
      category_slug?: string | null;
      instructions?: string | null;
      attach_images?: boolean;
    }) =>
      request<ResearchJob>(
        `${V1}/admin/ai/generate`,
        { method: "POST", body: JSON.stringify(payload) },
        true,
      ),
    guides: (params: { status?: GuideStatus; page?: number; page_size?: number } = {}) =>
      request<Page<AdminGuide>>(`${V1}/admin/guides${query(params)}`, {}, true),
    guide: (id: string) => request<AdminGuide>(`${V1}/admin/guides/${id}`, {}, true),
    saveDraft: (id: string, document: GuideDocument) =>
      request<AdminGuide>(
        `${V1}/admin/guides/${id}/draft`,
        { method: "PUT", body: JSON.stringify(document) },
        true,
      ),
    validate: (id: string) =>
      request<{ valid: boolean; content_hash: string; document: GuideDocument }>(
        `${V1}/admin/guides/${id}/validate`,
        { method: "POST" },
        true,
      ),
    submitForReview: (id: string) =>
      request<AdminGuide>(`${V1}/admin/guides/${id}/submit-for-review`, { method: "POST" }, true),
    publish: (id: string, revisionId: string | null = null) =>
      request<AdminGuide>(
        `${V1}/admin/guides/${id}/publish`,
        { method: "POST", body: JSON.stringify({ revision_id: revisionId }) },
        true,
      ),
    archive: (id: string) =>
      request<void>(`${V1}/admin/guides/${id}/archive`, { method: "POST" }, true),
    topicRequests: (
      params: { include_written?: boolean; page?: number; page_size?: number } = {},
    ) => request<Page<TopicRequestRow>>(`${V1}/admin/topic-requests${query(params)}`, {}, true),
    dismissTopicRequest: (id: string) =>
      request<void>(`${V1}/admin/topic-requests/${id}`, { method: "DELETE" }, true),
    jobs: (params: { status?: JobStatus; page?: number; page_size?: number } = {}) =>
      request<Page<ResearchJob>>(`${V1}/admin/research-jobs${query(params)}`, {}, true),
    job: (id: string) => request<ResearchJob>(`${V1}/admin/research-jobs/${id}`, {}, true),
    retryJob: (id: string) =>
      request<ResearchJob>(`${V1}/admin/research-jobs/${id}/retry`, { method: "POST" }, true),
    runJob: (id: string) =>
      request<ResearchJob>(`${V1}/admin/research-jobs/${id}/run`, { method: "POST" }, true),
    cancelJob: (id: string) =>
      request<ResearchJob>(`${V1}/admin/research-jobs/${id}/cancel`, { method: "POST" }, true),
    imageProviders: () => request<ImageProviderInfo[]>(`${V1}/admin/media/providers`, {}, true),
    imageSearch: (
      q: string,
      options: {
        provider?: string;
        guide_type?: string;
        category?: string;
        limit?: number;
      } = {},
    ) =>
      request<ImageSearchResult>(
        `${V1}/admin/media/image-search${query({ q, limit: 12, ...options })}`,
        {},
        true,
      ),
    createMedia: (payload: Record<string, unknown>) =>
      request<Media>(
        `${V1}/admin/media`,
        { method: "POST", body: JSON.stringify(payload) },
        true,
      ),
    setMediaApproval: (mediaId: string, approval_status: ApprovalStatus) =>
      request<Media>(
        `${V1}/admin/media/${mediaId}/approval`,
        { method: "PATCH", body: JSON.stringify({ approval_status }) },
        true,
      ),
    linkMedia: (
      guideId: string,
      payload: { media_asset_id: string; role?: string; caption?: string | null; sort_order?: number },
    ) =>
      request<Media>(
        `${V1}/admin/guides/${guideId}/draft/media`,
        { method: "POST", body: JSON.stringify(payload) },
        true,
      ),
    unlinkMedia: (guideId: string, linkId: string) =>
      request<void>(
        `${V1}/admin/guides/${guideId}/draft/media/${linkId}`,
        { method: "DELETE" },
        true,
      ),
  },
};

/* ---------------------------------------------------------------- helpers */

export function clockOf(larp: Pick<LarpCard, "exposure_seconds" | "unfalsifiable">): Clock {
  if (larp.unfalsifiable) return "indefinite";
  return larp.exposure_seconds;
}
