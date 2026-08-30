import { useCallback, useEffect, useId, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  api,
  ApiError,
  clockOf,
  type Category,
  type Clock,
  type CribSection,
  type EntryType,
  type GuideCard,
  type Verdict,
} from "./api";
import {
  TYPES,
  TYPE_GLYPH,
  VERDICTS,
  VERDICT_LABEL,
  VERDICT_LEVEL,
  VERDICT_TONE,
} from "./data";

const prefersReducedMotion = () =>
  typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

const mmss = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

/** Static, spoken-once label. The running digits stay aria-hidden. */
export function clockLabel(clock: Clock): string {
  if (clock === null) return "No clock. This one does not run.";
  if (clock === "indefinite") return "Indefinite. Nothing here is checkable.";
  const m = Math.round(clock / 60);
  return `About ${m} ${m === 1 ? "minute" : "minutes"} to exposure.`;
}

/* ----------------------------------------------------------------
   VerdictBadge — word + glyph + colour. The word is never dropped.
   The glyph is a fill gauge: full, half, low, stopped.
   ---------------------------------------------------------------- */

function VerdictMark({ verdict }: { verdict: Verdict }) {
  const id = useId();
  if (verdict === "dont") {
    return (
      <svg className="verdict__mark" viewBox="0 0 12 12" aria-hidden="true">
        <circle cx="6" cy="6" r="5" fill="none" stroke="currentColor" strokeWidth="2" />
        <line x1="2.5" y1="9.5" x2="9.5" y2="2.5" stroke="currentColor" strokeWidth="2" />
      </svg>
    );
  }
  const level = VERDICT_LEVEL[verdict];
  return (
    <svg className="verdict__mark" viewBox="0 0 12 12" aria-hidden="true">
      <clipPath id={id}>
        <circle cx="6" cy="6" r="5" />
      </clipPath>
      <circle cx="6" cy="6" r="5" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <rect
        x="0"
        y={12 - 12 * level}
        width="12"
        height={12 * level}
        fill="currentColor"
        clipPath={`url(#${id})`}
      />
    </svg>
  );
}

export function VerdictBadge({ verdict, size = "s" }: { verdict: Verdict; size?: "s" | "m" | "l" }) {
  return (
    <span className={`verdict verdict--${size} verdict--${VERDICT_TONE[verdict]}`}>
      <VerdictMark verdict={verdict} />
      {VERDICT_LABEL[verdict]}
    </span>
  );
}

/* ----------------------------------------------------------------
   ExposureClock — the one moving thing on an entry page.
   Counts down while you read. At zero it flips to EXPOSED and stays.
   ---------------------------------------------------------------- */

export function ExposureClock({
  seconds,
  running = false,
  size = "s",
  className = "",
}: {
  seconds: Clock;
  running?: boolean;
  size?: "s" | "l";
  className?: string;
}) {
  const start = typeof seconds === "number" ? seconds : 0;
  const [left, setLeft] = useState(start);

  useEffect(() => {
    setLeft(start);
    if (!running || typeof seconds !== "number" || prefersReducedMotion()) return;
    const id = setInterval(() => {
      // Pausing while the tab is hidden costs one line and keeps the value honest.
      if (document.hidden) return;
      setLeft((s) => (s <= 0 ? 0 : s - 1));
    }, 1000);
    return () => clearInterval(id);
  }, [seconds, running, start]);

  const cls = (m: string) => `clock ${size === "l" ? "clock--l " : ""}${m} ${className}`.trim();

  if (seconds === null) return <span className={cls("clock--none")} aria-hidden="true">—</span>;
  if (seconds === "indefinite") return <span className={cls("clock--inf")} aria-hidden="true">∞</span>;

  const exposed = running && left <= 0 && !prefersReducedMotion();
  return (
    <span className={cls(exposed ? "clock--exposed" : "")} aria-hidden="true">
      {exposed ? "EXPOSED" : mmss(running ? left : start)}
    </span>
  );
}

/* ---------------------------------------------------------------- */

export function TypeGlyph({ type, label = false }: { type: EntryType; label?: boolean }) {
  return (
    <span className="card__type">
      <span className="glyph" aria-hidden="true">{TYPE_GLYPH[type]}</span>
      {label ? <span className="u-label">{type}</span> : <span className="u-sr">{type}</span>}
    </span>
  );
}

export function FlagChips({ flags, stack = false }: { flags: string[]; stack?: boolean }) {
  if (!flags.length) return null;
  return (
    <ul className={`flags${stack ? " flags--stack" : ""}`}>
      {flags.slice(0, 3).map((f) => (
        <li key={f} className="flag">{f}</li>
      ))}
    </ul>
  );
}

export function EntryCard({ entry }: { entry: GuideCard }) {
  return (
    <Link className="card" to={`/entry/${entry.slug}`}>
      <div className="card__top">
        <TypeGlyph type={entry.larp.entry_type} label />
        <ExposureClock seconds={clockOf(entry.larp)} className="card__clock" />
      </div>
      <div className="card__body">
        <h3 className="card__name">{entry.title}</h3>
        <VerdictBadge verdict={entry.larp.verdict} />
        <p className="card__dek">{entry.larp.dek}</p>
        <div className="card__flags">
          <FlagChips flags={entry.larp.flags} />
        </div>
      </div>
    </Link>
  );
}

/* ----------------------------------------------------------------
   TickerRow — 60s cycle, right to left, pauses on hover and focus.
   The track is duplicated so -50% lands on a seam.
   ---------------------------------------------------------------- */

export function TickerRow({ entries }: { entries: GuideCard[] }) {
  if (!entries.length) return null;
  const run = entries.map((e) => (
    <Link className="ticker__item" key={e.slug} to={`/entry/${e.slug}`}>
      <span className="glyph" aria-hidden="true">{TYPE_GLYPH[e.larp.entry_type]}</span>
      {e.title.toUpperCase()}
      <ExposureClock seconds={clockOf(e.larp)} />
      <span className="ticker__sep" aria-hidden="true">·</span>
    </Link>
  ));
  return (
    <div className="ticker">
      <div className="ticker__track">
        <div style={{ display: "flex" }}>{run}</div>
        <div style={{ display: "flex" }} className="ticker__dupe" aria-hidden="true">
          {run}
        </div>
      </div>
    </div>
  );
}

/* ----------------------------------------------------------------
   SearchField — the front door. One box, one question.
   Typing updates ?q= after a beat and offers the closest entries;
   Enter goes straight to the one at the top of that list.
   ---------------------------------------------------------------- */

/** Bold the part of a title the person actually typed. */
function Marked({ text, term }: { text: string; term: string }) {
  const at = term ? text.toLowerCase().indexOf(term.toLowerCase()) : -1;
  if (at < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, at)}
      <b>{text.slice(at, at + term.length)}</b>
      {text.slice(at + term.length)}
    </>
  );
}

export function SearchField({
  value,
  onChange,
  busy,
  count,
}: {
  value: string;
  onChange: (next: string) => void;
  busy: boolean;
  count: number | null;
}) {
  const [draft, setDraft] = useState(value);
  const [hits, setHits] = useState<GuideCard[]>([]);
  const [open, setOpen] = useState(false);
  const [cursor, setCursor] = useState(0);
  const dirty = useRef(false);
  const navigate = useNavigate();

  useEffect(() => {
    if (!dirty.current) setDraft(value);
  }, [value]);

  useEffect(() => {
    if (draft === value) return;
    const id = setTimeout(() => {
      dirty.current = false;
      onChange(draft);
    }, 250);
    return () => clearTimeout(id);
  }, [draft, value, onChange]);

  // Suggestions run faster than the grid does, and are dropped if they land late.
  useEffect(() => {
    const term = draft.trim();
    if (term.length < 2) {
      setHits([]);
      return;
    }
    let cancelled = false;
    const id = setTimeout(() => {
      api
        .guides({ q: term, sort: "relevance", page_size: 6 })
        .then((page) => {
          if (cancelled) return;
          setHits(page.items);
          setCursor(0);
        })
        .catch(() => !cancelled && setHits([]));
    }, 120);
    return () => {
      cancelled = true;
      clearTimeout(id);
    };
  }, [draft]);

  const list = open ? hits : [];
  const go = (entry: GuideCard) => {
    setOpen(false);
    dirty.current = false;
    navigate(`/entry/${entry.slug}`);
  };

  return (
    <form
      className="search"
      role="search"
      onSubmit={(event) => {
        event.preventDefault();
        // Enter takes the top suggestion. With nothing to take, it commits the filter.
        const target = list[cursor] ?? list[0];
        if (target) {
          go(target);
          return;
        }
        dirty.current = false;
        setOpen(false);
        onChange(draft);
      }}
    >
      <div className="search__field">
        <label className="u-sr" htmlFor="search-q">Search entries</label>
        <input
          id="search-q"
          className="search__input"
          type="search"
          value={draft}
          placeholder="Type a thing you might claim to know"
          autoComplete="off"
          role="combobox"
          aria-expanded={list.length > 0}
          aria-controls="search-sug"
          aria-autocomplete="list"
          aria-activedescendant={list.length ? `sug-${cursor}` : undefined}
          onChange={(event) => {
            dirty.current = true;
            setOpen(true);
            setDraft(event.target.value);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 120)}
          onKeyDown={(event) => {
            if (!list.length) return;
            if (event.key === "Enter") {
              // Explicit rather than relying on the form's implicit submission.
              event.preventDefault();
              go(list[cursor] ?? list[0]);
            } else if (event.key === "ArrowDown") {
              event.preventDefault();
              setCursor((n) => (n + 1) % list.length);
            } else if (event.key === "ArrowUp") {
              event.preventDefault();
              setCursor((n) => (n - 1 + list.length) % list.length);
            } else if (event.key === "Escape") {
              setOpen(false);
            }
          }}
        />
        {list.length > 0 && (
          <ul className="sug" id="search-sug" role="listbox" aria-label="Closest entries">
            {list.map((entry, i) => (
              <li
                key={entry.slug}
                id={`sug-${i}`}
                role="option"
                aria-selected={i === cursor}
                className="sug__item"
                onMouseEnter={() => setCursor(i)}
                onMouseDown={(event) => {
                  event.preventDefault();
                  go(entry);
                }}
              >
                <span className="sug__name">
                  <Marked text={entry.title} term={draft.trim()} />
                </span>
                <span className="sug__meta">
                  <span className="sug__cat">{entry.category.title}</span>
                  <VerdictBadge verdict={entry.larp.verdict} />
                </span>
              </li>
            ))}
            <li className="sug__hint" aria-hidden="true">
              Enter opens the top one
            </li>
          </ul>
        )}
      </div>
      <button className="search__btn" type="submit">Search</button>
      <span className="search__status" aria-live="polite">
        {busy ? "searching" : count === null ? "" : `${count} found`}
      </span>
    </form>
  );
}

/* ----------------------------------------------------------------
   FilterBar — additive within a group, intersecting across groups.
   Every change is a history entry, so Back steps through them.
   ---------------------------------------------------------------- */

const readList = (v: string | null) => (v ? v.split(",").filter(Boolean) : []);

export function useFilters() {
  const [params, setParams] = useSearchParams();
  const verdicts = readList(params.get("verdict")) as Verdict[];
  const types = readList(params.get("type")) as EntryType[];
  const category = params.get("category") ?? "";
  const q = params.get("q") ?? "";

  const write = (next: {
    verdicts?: Verdict[];
    types?: EntryType[];
    category?: string;
    q?: string;
  }) => {
    const p = new URLSearchParams();
    const v = next.verdicts ?? verdicts;
    const t = next.types ?? types;
    const c = next.category ?? category;
    const term = next.q ?? q;
    if (term) p.set("q", term);
    if (v.length) p.set("verdict", v.join(","));
    if (t.length) p.set("type", t.join(","));
    if (c) p.set("category", c);
    setParams(p);
  };

  const toggle = <T extends string>(list: T[], value: T) =>
    list.includes(value) ? list.filter((x) => x !== value) : [...list, value];

  const setQuery = useCallback(
    (term: string) => {
      const p = new URLSearchParams(params);
      if (term) p.set("q", term);
      else p.delete("q");
      setParams(p, { replace: true });
    },
    [params, setParams],
  );

  return {
    q,
    verdicts,
    types,
    category,
    active: verdicts.length + types.length + (category ? 1 : 0) + (q ? 1 : 0),
    setQuery,
    toggleVerdict: (v: Verdict) => write({ verdicts: toggle(verdicts, v) }),
    toggleType: (t: EntryType) => write({ types: toggle(types, t) }),
    setCategory: (c: string) => write({ category: c }),
    clear: () => setParams(new URLSearchParams()),
  };
}

export function FilterBar({
  f,
  count,
  categories,
  lockCategory,
}: {
  f: ReturnType<typeof useFilters>;
  count: number;
  categories: Category[];
  lockCategory?: string;
}) {
  return (
    <div className="filters">
      <div className="filters__in u-shell">
        <div className="filters__group">
          {VERDICTS.map((v) => (
            <button
              key={v}
              className="chip"
              aria-pressed={f.verdicts.includes(v)}
              onClick={() => f.toggleVerdict(v)}
            >
              {VERDICT_LABEL[v]}
            </button>
          ))}
        </div>
        <div className="filters__group">
          {TYPES.map((t) => (
            <button key={t} className="chip" aria-pressed={f.types.includes(t)} onClick={() => f.toggleType(t)}>
              <span className="glyph" aria-hidden="true">{TYPE_GLYPH[t]}</span>
              {t}
            </button>
          ))}
        </div>
        <div className="filters__group filters__spacer">
          {lockCategory ? (
            <span className="u-label">{lockCategory}</span>
          ) : (
            <>
              <label className="u-sr" htmlFor="cat">Category</label>
              <select
                id="cat"
                className="filters__select"
                value={f.category}
                onChange={(e) => f.setCategory(e.target.value)}
              >
                <option value="">All categories</option>
                {categories.map((c) => (
                  <option key={c.slug} value={c.slug}>
                    {c.title} ({c.published_guide_count})
                  </option>
                ))}
              </select>
            </>
          )}
          <span className="filters__count" aria-live="polite">{count} shown</span>
          {f.active > 0 && !lockCategory && (
            <button className="chip chip--clear" onClick={f.clear}>Clear</button>
          )}
        </div>
      </div>
    </div>
  );
}

/* ----------------------------------------------------------------
   CribBlock — copy swaps its own label. No toast.
   ---------------------------------------------------------------- */

const asPlainText = (sections: CribSection[], title: string) =>
  [
    title.toUpperCase(),
    ...sections.map(
      (s) => `\n${s.heading.toUpperCase()}\n${s.lines.map((l) => `- ${l}`).join("\n")}`,
    ),
  ].join("\n");

export function CribBlock({ sections, title, id }: { sections: CribSection[]; title: string; id?: string }) {
  const body = useRef<HTMLDivElement>(null);
  const [label, setLabel] = useState<"copy" | "copied" | "select and copy">("copy");

  useEffect(() => {
    if (label === "copy") return;
    const t = setTimeout(() => setLabel("copy"), 2000);
    return () => clearTimeout(t);
  }, [label]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(asPlainText(sections, `${title} — the crib sheet`));
      setLabel("copied");
    } catch {
      if (body.current) getSelection()?.selectAllChildren(body.current);
      setLabel("select and copy");
    }
  };

  return (
    <section className="crib" id={id} aria-labelledby={`${id}-h`}>
      <div className="crib__top">
        <h2 className="crib__title" id={`${id}-h`}>The crib sheet</h2>
        <button className="crib__copy" onClick={copy} aria-live="polite">{label}</button>
      </div>
      <div className="crib__body" ref={body}>
        {sections.map((s) => (
          <div className="crib__sec" key={s.heading}>
            <h3 className="u-label crib__h">{s.heading}</h3>
            {s.lines.map((l) => (
              <p className="crib__line" key={l}>
                <span className="crib__bullet" aria-hidden="true">—</span>
                <span>{l}</span>
              </p>
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}

export function TellsList({ tells }: { tells: string[] }) {
  return (
    <ul className="tells">
      {tells.map((t) => (
        <li key={t}>{t}</li>
      ))}
    </ul>
  );
}

/* ----------------------------------------------------------------
   SubmitBox / NewsletterBox — one input, one button.
   ---------------------------------------------------------------- */

type BoxState = { kind: "idle" | "sending" | "ok" | "fail"; message?: string };

function Box({
  title,
  sub,
  placeholder,
  cta,
  done,
  type = "text",
  initialValue = "",
  submit,
}: {
  title: string;
  sub: string;
  placeholder: string;
  cta: string;
  done: string | ((value: string) => string);
  type?: string;
  initialValue?: string;
  submit: (value: string) => Promise<string | void>;
}) {
  const [value, setValue] = useState(initialValue);
  const [state, setState] = useState<BoxState>({ kind: "idle" });
  const [outcome, setOutcome] = useState("");

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!value.trim()) {
      setState({ kind: "fail", message: "The field is empty. Type a name first." });
      return;
    }
    setState({ kind: "sending" });
    try {
      const message = await submit(value.trim());
      setOutcome(typeof message === "string" ? message : "");
      setState({ kind: "ok" });
    } catch (error) {
      // Field keeps its value. The message names what failed and what to do.
      const detail =
        error instanceof ApiError && error.status === 429
          ? "Too many requests from this address. Wait a minute and try again."
          : "The request did not reach us. Check your connection and press submit again.";
      setState({ kind: "fail", message: detail });
    }
  };

  return (
    <form className="box" onSubmit={onSubmit} noValidate>
      <div className="box__head">
        <h2 className="box__title">{title}</h2>
        <p className="box__sub">{sub}</p>
      </div>
      {state.kind === "ok" ? (
        <p className="box__msg">{outcome || (typeof done === "string" ? done : done(value))}</p>
      ) : (
        <>
          <label className="u-sr" htmlFor={`box-${title}`}>{title}</label>
          <input
            id={`box-${title}`}
            type={type}
            value={value}
            placeholder={placeholder}
            onChange={(e) => setValue(e.target.value)}
            autoComplete={type === "email" ? "email" : "off"}
          />
          <button className="box__btn" type="submit" disabled={state.kind === "sending"}>
            {state.kind === "sending" ? "sending" : cta}
          </button>
          {state.kind === "fail" && (
            <p className="box__msg box__msg--fail" role="alert">{state.message}</p>
          )}
        </>
      )}
    </form>
  );
}

/**
 * Records demand for a topic nobody has written yet. Search never calls this on
 * its own: the reader has to ask for it, once, on purpose.
 */
export function SubmitBox({ topic = "" }: { topic?: string }) {
  return (
    <Box
      title="Not listed yet"
      sub="One scene, taste, or role per submission."
      placeholder="e.g. orienteering, Bauhaus, sommelier"
      cta="Request it"
      initialValue={topic}
      done="Queued. A human reads it before it ships."
      submit={async (value) => {
        const result = await api.requestTopic(value);
        if (result.matching_guide) {
          return `Already written: ${result.matching_guide.title}. Search for it above.`;
        }
        const n = result.request_count ?? 1;
        return n > 1
          ? `Recorded. ${n} people have asked for this one.`
          : "Recorded. You are the first to ask for this one.";
      }}
    />
  );
}

export function NewsletterBox() {
  // No subscription endpoint exists yet, so this resolves locally and says so.
  return (
    <Box
      title="One entry a week"
      sub="No archive, no digest, no second email."
      placeholder="you@example.com"
      type="email"
      cta="Subscribe"
      done="Noted locally. The mailing list is not wired up yet."
      submit={() => new Promise<void>((r) => setTimeout(r, 350))}
    />
  );
}

/* ---------------------------------------------------------------- */

export function Loading({ what = "entries" }: { what?: string }) {
  return <p className="state state--loading">Loading {what}…</p>;
}

export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  const message =
    error instanceof ApiError
      ? error.message
      : "Something went wrong and the page could not load.";
  return (
    <div className="state state--error" role="alert">
      <p>{message}</p>
      {retry && (
        <button className="chip" onClick={retry}>
          Try again
        </button>
      )}
    </div>
  );
}
