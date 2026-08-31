import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ApiError,
  api,
  type AdminGuide,
  type Category,
  type EntryType,
  type GuideDocument,
  type GuideType,
  type ImageQuery,
  type ResearchJob,
  type Verdict,
} from "../api";
import { ErrorState, Loading } from "../components";
import { isAdmin, useAuth } from "../auth";
import { VERDICT_LABEL } from "../data";
import MediaPanel from "./MediaPanel";
import {
  CribEditor,
  CsvField,
  PhraseEditor,
  ListField,
  NumberField,
  SelectField,
  TextArea,
  TextField,
} from "./fields";

const VERDICT_OPTIONS: { value: Verdict; label: string }[] = (
  ["yes", "kinda", "talk_only", "dont"] as Verdict[]
).map((value) => ({ value, label: VERDICT_LABEL[value] }));

const ENTRY_OPTIONS: { value: EntryType; label: string }[] = [
  { value: "scene", label: "Scene" },
  { value: "taste", label: "Taste" },
  { value: "role", label: "Role" },
];

const GUIDE_TYPE_OPTIONS: { value: GuideType; label: string }[] = [
  { value: "anime", label: "Anime" },
  { value: "screen", label: "Screen" },
  { value: "lifestyle", label: "Lifestyle" },
  { value: "person", label: "Person" },
  { value: "craft", label: "Craft" },
  { value: "profession", label: "Profession" },
  { value: "general", label: "General" },
];

type Notice = { kind: "ok" | "fail"; text: string } | null;

const RUNNING = new Set(["queued", "running"]);

export default function GuideEditor() {
  const { id = "" } = useParams();
  const { account } = useAuth();
  const [guide, setGuide] = useState<AdminGuide | null>(null);
  const [document, setDocument] = useState<GuideDocument | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [raw, setRaw] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice>(null);
  const [busy, setBusy] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [rewrite, setRewrite] = useState<ResearchJob | null>(null);
  const [replaceImages, setReplaceImages] = useState(false);

  const load = useCallback(() => {
    setBusy(true);
    return api.admin
      .guide(id)
      .then((row) => {
        setGuide(row);
        const source = row.draft_revision?.document ?? row.current_revision?.document ?? null;
        setDocument(source ? structuredClone(source) : null);
        setError(null);
      })
      .catch(setError)
      .finally(() => setBusy(false));
  }, [id]);

  useEffect(() => {
    void load();
    api.categories().then(setCategories).catch(() => setCategories([]));
  }, [load]);

  // The rewrite runs in the API process, so the only way to see it land is to ask.
  useEffect(() => {
    if (!rewrite || !RUNNING.has(rewrite.status)) return;
    const timer = setInterval(() => {
      api.admin
        .job(rewrite.id)
        .then((next) => {
          setRewrite(next);
          if (!RUNNING.has(next.status)) {
            void load();
            setNotice(
              next.status === "failed"
                ? { kind: "fail", text: next.error_message ?? "The rewrite failed." }
                : { kind: "ok", text: "Rewritten. Read the draft before publishing it." },
            );
          }
        })
        .catch(() => undefined);
    }, 2500);
    return () => clearInterval(timer);
  }, [rewrite, load]);

  const media = guide?.draft_revision?.media ?? guide?.current_revision?.media ?? [];

  // The document's own brief drives the image panel; fall back to whatever
  // visual direction an older document carries.
  const brief = useMemo<ImageQuery[]>(() => {
    if (!document) return [];
    const content = document.content;
    if (content.image_brief?.length) return content.image_brief;
    const inferred = [
      ...(content.media_scenarios ?? []).flatMap((scenario) =>
        scenario.search_terms.map((term) => ({ term, subject: scenario.title })),
      ),
      ...(content.visual_cues ?? []).map((term) => ({ term, subject: null })),
      { term: document.title, subject: document.title },
    ];
    const seen = new Set<string>();
    return inferred
      .filter(({ term }) => term.trim() && !seen.has(term.toLowerCase()) && seen.add(term.toLowerCase()))
      .slice(0, 6)
      .map(({ term, subject }) => ({
        provider: "auto" as const,
        query: term,
        subject,
        role: "gallery" as const,
        note: null,
      }));
  }, [document]);

  if (busy && !guide) return <Loading what="the guide" />;
  if (error) return <ErrorState error={error} retry={load} />;
  if (!guide) return <p className="panel__empty">Guide not found.</p>;

  const patchLarp = (patch: Partial<GuideDocument["content"]["larp"]>) => {
    setDocument((current) =>
      current
        ? { ...current, content: { ...current.content, larp: { ...current.content.larp, ...patch } } }
        : current,
    );
  };

  const patchContent = (patch: Partial<GuideDocument["content"]>) => {
    setDocument((current) =>
      current ? { ...current, content: { ...current.content, ...patch } } : current,
    );
  };

  const run = async (action: () => Promise<unknown>, okText: string) => {
    setSaving(true);
    setNotice(null);
    try {
      await action();
      await load();
      setNotice({ kind: "ok", text: okText });
    } catch (cause) {
      setNotice({
        kind: "fail",
        text: cause instanceof ApiError ? cause.message : "That did not work.",
      });
    } finally {
      setSaving(false);
    }
  };

  const currentDocument = (): GuideDocument | null => {
    if (raw === null) return document;
    try {
      return JSON.parse(raw) as GuideDocument;
    } catch (cause) {
      setNotice({ kind: "fail", text: `The raw JSON does not parse: ${String(cause)}` });
      return null;
    }
  };

  const save = () => {
    const payload = currentDocument();
    if (!payload) return;
    void run(() => api.admin.saveDraft(guide.id, payload), "Draft saved.");
  };

  const larp = document?.content.larp;
  const stop = larp?.verdict === "dont";
  const rewriting = Boolean(rewrite && RUNNING.has(rewrite.status));

  return (
    <div className="editor">
      <header className="editor__head">
        <div>
          <h1 className="admin__h1">{guide.title}</h1>
          <p className="editor__meta">
            <span className={`pill pill--${guide.status}`}>{guide.status.replace("_", " ")}</span>
            <span className="editor__slug">{guide.slug}</span>
            {guide.status === "published" ? (
              <Link className="editor__view" to={`/entry/${guide.slug}`}>
                view public page
              </Link>
            ) : null}
          </p>
        </div>
        <div className="editor__actions">
          <button className="btn" disabled={saving || !document} onClick={save}>
            {saving ? "working…" : "Save draft"}
          </button>
          <button
            className="chip"
            disabled={saving}
            onClick={() =>
              void run(async () => {
                const result = await api.admin.validate(guide.id);
                setNotice({ kind: "ok", text: `Valid. Hash ${result.content_hash.slice(0, 12)}…` });
              }, "Draft validates.")
            }
          >
            Validate
          </button>
          <button
            className="chip"
            disabled={saving || !guide.draft_revision}
            onClick={() => void run(() => api.admin.submitForReview(guide.id), "Sent for review.")}
          >
            Submit for review
          </button>
          <button
            className="chip chip--go"
            disabled={saving || !isAdmin(account) || !guide.draft_revision}
            title={isAdmin(account) ? undefined : "Publishing needs the admin role"}
            onClick={() => void run(() => api.admin.publish(guide.id), "Published.")}
          >
            Publish
          </button>
          <button
            className="chip"
            disabled={saving || !isAdmin(account)}
            onClick={() => void run(() => api.admin.archive(guide.id), "Archived.")}
          >
            Archive
          </button>
          <button
            className="chip chip--ai"
            disabled={saving || rewriting}
            title="Write this guide again from its title. The published version stays up."
            onClick={() => {
              const warning = guide.draft_revision
                ? `Rewrite "${guide.title}"? This replaces the current draft.`
                : `Rewrite "${guide.title}"? It lands as a new draft.`;
              if (!confirm(warning)) return;
              setNotice(null);
              api.admin
                .regenerate(guide.id, { replace_images: replaceImages })
                .then(setRewrite)
                .catch((cause) =>
                  setNotice({
                    kind: "fail",
                    text: cause instanceof ApiError ? cause.message : "Could not start it.",
                  }),
                );
            }}
          >
            {rewriting ? "rewriting…" : "Regenerate"}
          </button>
          <label className="editor__toggle">
            <input
              type="checkbox"
              checked={replaceImages}
              onChange={(event) => setReplaceImages(event.target.checked)}
            />
            <span>new images too</span>
          </label>
        </div>
      </header>

      {rewriting && (
        <p className="admin__ok" role="status">
          Rewriting “{guide.title}” from its title. This takes about a minute; the
          published version stays up until you publish the new draft.
        </p>
      )}

      {notice && (
        <p className={notice.kind === "ok" ? "admin__ok" : "admin__error"} role="status">
          {notice.text}
        </p>
      )}

      {!document ? (
        <p className="panel__empty">This guide has no revision to edit.</p>
      ) : raw !== null ? (
        <section className="panel">
          <div className="panel__head">
            <h2 className="panel__h">Raw document</h2>
            <button className="chip" onClick={() => setRaw(null)}>
              Back to the form
            </button>
          </div>
          <textarea
            className="af__input af__input--code"
            rows={32}
            value={raw}
            onChange={(event) => setRaw(event.target.value)}
          />
        </section>
      ) : (
        <div className="admin__cols">
          <MediaPanel
            guideId={guide.id}
            media={media}
            brief={brief}
            guideType={document.guide_type}
            categorySlug={document.category_slug}
            onChanged={() => void load()}
          />

          <section className="panel">
            <div className="panel__head">
              <h2 className="panel__h">The verdict</h2>
              <button className="chip" onClick={() => setRaw(JSON.stringify(document, null, 2))}>
                Edit raw JSON
              </button>
            </div>

            <TextField
              label="Title"
              value={document.title}
              onChange={(title) => setDocument({ ...document, title })}
            />
            <TextField label="Slug" value={document.slug} onChange={() => undefined} disabled
              hint="A slug is permanent once the guide exists." />
            <TextArea
              label="Summary"
              value={document.summary}
              rows={3}
              onChange={(summary) => setDocument({ ...document, summary })}
              hint="Used in search results and meta descriptions."
            />
            <SelectField
              label="Category"
              value={document.category_slug}
              options={categories.map((c) => ({ value: c.slug, label: c.title }))}
              onChange={(category_slug) => setDocument({ ...document, category_slug })}
            />
            <SelectField
              label="Guide type"
              value={document.guide_type}
              options={GUIDE_TYPE_OPTIONS}
              onChange={() => undefined}
              hint="Changing the template means rewriting the content block; use raw JSON."
            />
            <CsvField
              label="Aliases"
              values={document.aliases}
              onChange={(aliases) => setDocument({ ...document, aliases })}
              hint="Other names people search for, comma separated."
            />

            {larp && (
              <>
                <SelectField
                  label="Verdict"
                  value={larp.verdict}
                  options={VERDICT_OPTIONS}
                  onChange={(verdict) =>
                    patchLarp(
                      verdict === "dont"
                        ? { verdict, exposure_seconds: null, unfalsifiable: false }
                        : { verdict },
                    )
                  }
                />
                <SelectField
                  label="Entry type"
                  value={larp.entry_type}
                  options={ENTRY_OPTIONS}
                  onChange={(entry_type) => patchLarp({ entry_type })}
                />
                <label className="af af--check">
                  <input
                    type="checkbox"
                    checked={larp.unfalsifiable}
                    disabled={stop}
                    onChange={(event) =>
                      patchLarp({
                        unfalsifiable: event.target.checked,
                        exposure_seconds: event.target.checked ? null : larp.exposure_seconds,
                      })
                    }
                  />
                  <span>Unfalsifiable — nothing here is checkable, so no clock runs</span>
                </label>
                <NumberField
                  label="Exposure seconds"
                  value={larp.exposure_seconds}
                  min={30}
                  disabled={larp.unfalsifiable || stop}
                  onChange={(exposure_seconds) => patchLarp({ exposure_seconds })}
                  hint="How long before a knowledgeable person catches on. 360 is six minutes."
                />
                <CsvField
                  label="Flags"
                  values={larp.flags}
                  onChange={(flags) => patchLarp({ flags })}
                  hint="Up to three short uppercase warnings, comma separated."
                />
                <TextArea
                  label="Dek"
                  value={larp.dek}
                  rows={2}
                  onChange={(dek) => patchLarp({ dek })}
                  hint="One sentence under the title."
                />
              </>
            )}
          </section>

          <section className="panel">
            <div className="panel__head">
              <h2 className="panel__h">The entry</h2>
            </div>
            {larp && (
              <>
                <CribEditor sections={larp.crib} onChange={(crib) => patchLarp({ crib })} />
                <PhraseEditor
                  phrases={larp.phrases}
                  disabled={stop}
                  onChange={(phrases) => patchLarp({ phrases })}
                />
                <ListField
                  label="The surface layer"
                  values={larp.surface}
                  onChange={(surface) => patchLarp({ surface })}
                  hint="What passes on first contact. One paragraph per box."
                />
                <TextArea
                  label="The follow-up that kills you"
                  value={larp.follow_up.question}
                  rows={2}
                  onChange={(question) =>
                    patchLarp({ follow_up: { ...larp.follow_up, question } })
                  }
                  hint="The question itself, in quotes."
                />
                <TextArea
                  label="Why it works"
                  value={larp.follow_up.why}
                  rows={5}
                  onChange={(why) => patchLarp({ follow_up: { ...larp.follow_up, why } })}
                  hint="Blank lines separate paragraphs."
                />
                <label className="af af--check">
                  <input
                    type="checkbox"
                    checked={larp.follow_up.counter !== null}
                    disabled={stop}
                    onChange={(event) =>
                      patchLarp({
                        follow_up: {
                          ...larp.follow_up,
                          counter: event.target.checked
                            ? { move: "", holds: "" }
                            : null,
                        },
                      })
                    }
                  />
                  <span>
                    This one has a counter
                    {stop ? " — a DON'T entry never does" : ""}
                  </span>
                </label>
                {larp.follow_up.counter && (
                  <>
                    <TextArea
                      label="The counter"
                      value={larp.follow_up.counter.move}
                      rows={4}
                      onChange={(move) =>
                        patchLarp({
                          follow_up: {
                            ...larp.follow_up,
                            counter: { ...larp.follow_up.counter!, move },
                          },
                        })
                      }
                      hint="The words the reader says when the question lands, not the strategy."
                    />
                    <TextArea
                      label="How far it holds"
                      value={larp.follow_up.counter.holds}
                      rows={3}
                      onChange={(holds) =>
                        patchLarp({
                          follow_up: {
                            ...larp.follow_up,
                            counter: { ...larp.follow_up.counter!, holds },
                          },
                        })
                      }
                      hint="And the situation it does not survive. An oversold counter is worse than none."
                    />
                  </>
                )}
                <ListField
                  label="Tells"
                  values={larp.tells}
                  rows={1}
                  onChange={(tells) => patchLarp({ tells })}
                  hint="Each one contrasts the larper with the real thing."
                />
                <ListField
                  label="Cost of getting caught"
                  values={larp.cost}
                  onChange={(cost) => patchLarp({ cost })}
                />
                <NumberField
                  label="Hours to just learn it"
                  value={larp.learn.hours}
                  min={0}
                  onChange={(hours) =>
                    patchLarp({ learn: { ...larp.learn, hours: hours ?? 0 } })
                  }
                />
                <TextField
                  label="The one book"
                  value={larp.learn.book}
                  onChange={(book) => patchLarp({ learn: { ...larp.learn, book } })}
                />
                <TextField
                  label="The one thing to make"
                  value={larp.learn.make}
                  onChange={(make) => patchLarp({ learn: { ...larp.learn, make } })}
                />
              </>
            )}

            <ListField
              label="Quick brief"
              values={document.content.quick_brief}
              rows={1}
              onChange={(quick_brief) => patchContent({ quick_brief })}
              hint="The minimum not to embarrass yourself."
            />
            <TextArea
              label="Overview"
              value={document.content.overview}
              rows={8}
              onChange={(overview) => patchContent({ overview })}
              hint="Blank lines separate paragraphs."
            />
            <ListField
              label="Common mistakes"
              values={document.content.common_mistakes}
              rows={1}
              onChange={(common_mistakes) => patchContent({ common_mistakes })}
            />
          </section>

        </div>
      )}
    </div>
  );
}
