import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  ApiError,
  api,
  type AiStatus,
  type Category,
  type EntryType,
  type GuideType,
  type ResearchJob,
} from "../api";
import { SelectField, TextArea, TextField } from "./fields";

const GUIDE_TYPES: { value: GuideType | ""; label: string }[] = [
  { value: "", label: "Let the model choose" },
  { value: "anime", label: "Anime — plot, characters, endings, fandom" },
  { value: "screen", label: "Screen — films and series, and how they end" },
  { value: "lifestyle", label: "Lifestyle — brands, objects, places, a look" },
  { value: "craft", label: "Craft — a skill somebody can hand you the kit for" },
  { value: "profession", label: "Profession — a job title, and where it becomes fraud" },
  { value: "general", label: "General — everything with no better home" },
];

const ENTRY_TYPES: { value: EntryType | ""; label: string }[] = [
  { value: "", label: "Let the model choose" },
  { value: "scene", label: "Scene — a room you claim to belong in" },
  { value: "taste", label: "Taste — a thing you claim to like" },
  { value: "role", label: "Role — a thing you claim to be" },
];

const TERMINAL = new Set(["review", "completed", "failed", "cancelled"]);

export default function Generate() {
  const [params] = useSearchParams();
  const navigate = useNavigate();

  const [topic, setTopic] = useState(params.get("topic") ?? "");
  const [guideType, setGuideType] = useState<GuideType | "">("");
  const [entryType, setEntryType] = useState<EntryType | "">("");
  const [categorySlug, setCategorySlug] = useState("");
  const [instructions, setInstructions] = useState("");
  const [attachImages, setAttachImages] = useState(true);

  const [categories, setCategories] = useState<Category[]>([]);
  const [aiStatus, setAiStatus] = useState<AiStatus | null>(null);
  const [job, setJob] = useState<ResearchJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api.categories().then(setCategories).catch(() => setCategories([]));
    api.admin.aiStatus().then(setAiStatus).catch(() => setAiStatus(null));
  }, []);

  // The job runs in the API process, so the only way to see it finish is to ask.
  useEffect(() => {
    if (!job || TERMINAL.has(job.status)) return;
    const id = setInterval(() => {
      api.admin
        .job(job.id)
        .then(setJob)
        .catch(() => undefined);
    }, 2500);
    return () => clearInterval(id);
  }, [job]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const created = await api.admin.generate({
        topic: topic.trim(),
        guide_type: guideType || null,
        entry_type: entryType || null,
        category_slug: categorySlug || null,
        instructions: instructions.trim() || null,
        attach_images: attachImages,
      });
      setJob(created);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "The request failed.");
    } finally {
      setSubmitting(false);
    }
  };

  const warnings = (job?.result?.warnings as string[] | undefined) ?? [];

  return (
    <div className="admin__cols">
      <section className="panel">
        <div className="panel__head">
          <h2 className="panel__h">Generate a guide</h2>
          <p className="panel__sub">
            One topic in, one draft out. Nothing is published until you publish it.
          </p>
        </div>

        {aiStatus && !aiStatus.text_configured && (
          <p className="admin__error" role="alert">
            No model key is configured. Set <code>OPENAI_API_KEY</code> in{" "}
            <code>backend/.env</code> and restart the API.
          </p>
        )}

        <form className="admin__form" onSubmit={submit}>
          <TextField
            label="Topic"
            value={topic}
            onChange={setTopic}
            placeholder="e.g. Attack on Titan, orienteering, sommelier"
            hint="What someone would type into the search box."
          />
          <SelectField
            label="Guide type"
            value={guideType}
            options={GUIDE_TYPES}
            onChange={setGuideType}
          />
          <SelectField
            label="Entry type"
            value={entryType}
            options={ENTRY_TYPES}
            onChange={setEntryType}
          />
          <SelectField
            label="Category"
            value={categorySlug}
            options={[
              { value: "", label: "Let the model choose" },
              ...categories.map((c) => ({ value: c.slug, label: c.title })),
            ]}
            onChange={setCategorySlug}
          />
          <TextArea
            label="Instructions"
            value={instructions}
            onChange={setInstructions}
            rows={4}
            hint="Optional. Anything here overrides the house defaults."
          />
          <label className="af af--check">
            <input
              type="checkbox"
              checked={attachImages}
              onChange={(event) => setAttachImages(event.target.checked)}
              disabled={aiStatus ? !aiStatus.images_configured : false}
            />
            <span>
              Find and attach images. The model picks a source per picture.
            </span>
          </label>

          {aiStatus && (
            <ul className="providerList">
              {aiStatus.image_providers.map((item) => (
                <li key={item.id} className={item.configured ? "" : "is-off"}>
                  <span className="providerList__name">{item.title}</span>
                  <span className="providerList__what">{item.subjects}</span>
                  {!item.configured && <span className="providerList__off">needs a key</span>}
                </li>
              ))}
            </ul>
          )}

          <button
            className="btn"
            type="submit"
            disabled={submitting || !topic.trim() || aiStatus?.text_configured === false}
          >
            {submitting ? "queueing…" : "Generate draft"}
          </button>
        </form>

        {error && (
          <p className="admin__error" role="alert">
            {error}
          </p>
        )}
      </section>

      <section className="panel">
        <div className="panel__head">
          <h2 className="panel__h">Run</h2>
          {aiStatus ? (
            <p className="panel__sub">
              {aiStatus.text_provider} · {aiStatus.text_model}
            </p>
          ) : null}
        </div>

        {!job ? (
          <p className="panel__empty">
            Nothing running. A generation takes about a minute: the model writes the
            document, the API validates it, dead links are dropped, and photographs are
            attached to the draft.
          </p>
        ) : (
          <div className="run">
            <p className="run__row">
              <span className={`pill pill--${job.status}`}>{job.status}</span>
              <span className="run__topic">{job.topic}</span>
            </p>
            {job.status === "queued" || job.status === "running" ? (
              <p className="run__wait">Working. This page checks every few seconds.</p>
            ) : null}
            {job.error_message ? (
              <pre className="run__error">{job.error_message}</pre>
            ) : null}
            {warnings.length > 0 && (
              <ul className="run__warnings">
                {warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            )}
            {job.estimated_cost_micros > 0 && (
              <p className="run__cost">
                Estimated cost ${(job.estimated_cost_micros / 1_000_000).toFixed(4)}
              </p>
            )}
            {job.created_guide_id && (
              <button
                className="btn"
                onClick={() => navigate(`/admin/guides/${job.created_guide_id}`)}
              >
                Open the draft
              </button>
            )}
            {job.status === "failed" && (
              <button
                className="chip"
                onClick={() => {
                  api.admin
                    .retryJob(job.id)
                    .then((retried) => api.admin.runJob(retried.id))
                    .then(setJob)
                    .catch((cause) =>
                      setError(cause instanceof ApiError ? cause.message : "Retry failed."),
                    );
                }}
              >
                Retry
              </button>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
