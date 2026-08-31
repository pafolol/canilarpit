import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ApiError,
  api,
  type Category,
  type EntryType,
  type GuideType,
} from "./api";

const GUIDE_TYPES: { value: GuideType | ""; label: string }[] = [
  { value: "", label: "Not sure" },
  { value: "screen", label: "A film or series" },
  { value: "anime", label: "Anime or manga" },
  { value: "person", label: "A person and their work" },
  { value: "craft", label: "A skill you practise" },
  { value: "profession", label: "A job" },
  { value: "lifestyle", label: "A scene, with a look" },
  { value: "general", label: "Something else" },
];

const ENTRY_TYPES: { value: EntryType | ""; label: string }[] = [
  { value: "", label: "Not sure" },
  { value: "scene", label: "A scene you claim to belong to" },
  { value: "taste", label: "A thing you claim to like" },
  { value: "role", label: "A thing you claim to be" },
];

const NEW_CATEGORY = "__new__";

/**
 * What a reader gets when the catalogue has nothing.
 *
 * It asks for enough to write from rather than just a name, because a topic on
 * its own tells an editor nothing about whether it is worth an evening. The
 * hidden `website` field and the form token are the parts nobody should notice.
 */
export default function SubmissionForm({ topic = "" }: { topic?: string }) {
  const navigate = useNavigate();
  const [token, setToken] = useState<string | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);

  const [subject, setSubject] = useState(topic);
  const [notes, setNotes] = useState("");
  const [guideType, setGuideType] = useState<GuideType | "">("");
  const [entryType, setEntryType] = useState<EntryType | "">("");
  const [category, setCategory] = useState("");
  const [newCategory, setNewCategory] = useState("");
  const [credit, setCredit] = useState("");
  const [website, setWebsite] = useState("");

  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.submissionForm().then((form) => setToken(form.token)).catch(() => setToken(null));
    api.categories().then(setCategories).catch(() => setCategories([]));
  }, []);

  // Follow the search box until the reader edits the field themselves.
  const [edited, setEdited] = useState(false);
  useEffect(() => {
    if (!edited) setSubject(topic);
  }, [topic, edited]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!token) {
      setError("The form did not load. Refresh the page and try again.");
      return;
    }
    setSending(true);
    setError(null);
    try {
      const receipt = await api.submit({
        topic: subject.trim(),
        notes: notes.trim(),
        guide_type: guideType || null,
        entry_type: entryType || null,
        category_slug: category && category !== NEW_CATEGORY ? category : null,
        suggested_category: category === NEW_CATEGORY ? newCategory.trim() || null : null,
        credit_name: credit.trim() || null,
        token,
        website: website || null,
      });
      navigate("/thanks", {
        state: {
          message: receipt.message,
          guideSlug: receipt.matching_guide?.slug,
          guideTitle: receipt.matching_guide?.title,
        },
      });
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : "That did not send. Try again in a moment.",
      );
      // A refused token is spent; get another so a retry can succeed.
      api.submissionForm().then((form) => setToken(form.token)).catch(() => undefined);
    } finally {
      setSending(false);
    }
  };

  return (
    <form className="submit" onSubmit={submit} noValidate>
      <div className="submit__head">
        <h2 className="submit__title">Write it with us</h2>
        <p className="submit__sub">
          Tell us what you know and an editor takes it from there. What you write is a
          lead, not the guide: it gets checked before anything is published. Somebody
          reads every submission within 48 hours.
        </p>
      </div>

      <label className="af">
        <span className="af__label">What is it</span>
        <input
          className="af__input"
          value={subject}
          placeholder="e.g. orienteering, Werner Herzog, sommelier"
          onChange={(event) => {
            setEdited(true);
            setSubject(event.target.value);
          }}
        />
      </label>

      <label className="af">
        <span className="af__label">What would somebody need to know</span>
        <textarea
          className="af__input af__input--area"
          rows={6}
          value={notes}
          placeholder="The names people drop, the question that catches someone out, what gives a beginner away. A few sentences is plenty."
          onChange={(event) => setNotes(event.target.value)}
        />
        <span className="af__hint">
          {notes.trim().length < 80
            ? `${80 - notes.trim().length} more characters needed`
            : "That is enough to work with."}
        </span>
      </label>

      <div className="submit__row">
        <label className="af">
          <span className="af__label">What kind of thing</span>
          <select
            className="af__input"
            value={guideType}
            onChange={(event) => setGuideType(event.target.value as GuideType | "")}
          >
            {GUIDE_TYPES.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </label>

        <label className="af">
          <span className="af__label">How people claim it</span>
          <select
            className="af__input"
            value={entryType}
            onChange={(event) => setEntryType(event.target.value as EntryType | "")}
          >
            {ENTRY_TYPES.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </label>
      </div>

      <div className="submit__row">
        <label className="af">
          <span className="af__label">Category</span>
          <select
            className="af__input"
            value={category}
            onChange={(event) => setCategory(event.target.value)}
          >
            <option value="">Let an editor decide</option>
            {categories.map((item) => (
              <option key={item.slug} value={item.slug}>{item.title}</option>
            ))}
            <option value={NEW_CATEGORY}>Suggest a new one…</option>
          </select>
        </label>

        {category === NEW_CATEGORY ? (
          <label className="af">
            <span className="af__label">Your category</span>
            <input
              className="af__input"
              value={newCategory}
              placeholder="e.g. architecture, poker, birding"
              onChange={(event) => setNewCategory(event.target.value)}
            />
            <span className="af__hint">An editor decides whether to add it.</span>
          </label>
        ) : (
          <label className="af">
            <span className="af__label">Credit, if you want it</span>
            <input
              className="af__input"
              value={credit}
              placeholder="A name or a handle"
              onChange={(event) => setCredit(event.target.value)}
            />
            <span className="af__hint">Printed on the entry as suggested by. Optional.</span>
          </label>
        )}
      </div>

      {category === NEW_CATEGORY ? (
        <label className="af">
          <span className="af__label">Credit, if you want it</span>
          <input
            className="af__input"
            value={credit}
            placeholder="A name or a handle"
            onChange={(event) => setCredit(event.target.value)}
          />
        </label>
      ) : null}

      {/* Hidden by the stylesheet. Anything typed here did not come from a person. */}
      <div className="submit__trap" aria-hidden="true">
        <label>
          Leave this empty
          <input
            tabIndex={-1}
            autoComplete="off"
            value={website}
            onChange={(event) => setWebsite(event.target.value)}
          />
        </label>
      </div>

      <button className="btn" type="submit" disabled={sending || !token}>
        {sending ? "sending…" : "Send it in"}
      </button>

      {error ? (
        <p className="admin__error" role="alert">
          {error}
        </p>
      ) : null}
    </form>
  );
}
