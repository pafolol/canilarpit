/**
 * Cross-links between guides.
 *
 * A guide's prose names other subjects all the time — an anime guide lists
 * three other shows, a taste guide names a scene. Where one of those already
 * has a page, the mention becomes a link, and hovering it shows what the
 * verdict over there is without making you leave.
 *
 * The catalogue is small enough to hold in memory, so this costs one request
 * per session and no request at all per hover.
 */

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api, type GuideCard } from "./api";
import { ReadCount, TypeGlyph, VerdictBadge } from "./components";

/* ---------------------------------------------------------------- index */

let pending: Promise<GuideCard[]> | null = null;

/** Every published guide, title-first, fetched once and shared. */
function catalogue(): Promise<GuideCard[]> {
  pending ??= api
    .guides({ page_size: 100, sort: "title" })
    .then((page) => page.items)
    .catch(() => []);
  return pending;
}

export function useCatalogue(): GuideCard[] {
  const [rows, setRows] = useState<GuideCard[]>([]);
  useEffect(() => {
    let live = true;
    catalogue().then((items) => live && setRows(items));
    return () => {
      live = false;
    };
  }, []);
  return rows;
}

const escape = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/**
 * One regex for the whole catalogue. Longest titles first, so "Prestige TV"
 * wins over a guide that happens to be called "TV".
 */
function buildMatcher(rows: GuideCard[], exclude: string) {
  const usable = rows.filter((row) => row.slug !== exclude && row.title.trim().length >= 3);
  if (usable.length === 0) return null;
  const bySlug = new Map(usable.map((row) => [row.title.toLowerCase(), row]));
  const pattern = usable
    .map((row) => row.title)
    .sort((a, b) => b.length - a.length)
    .map(escape)
    .join("|");
  return { re: new RegExp(`\\b(${pattern})\\b`, "gi"), bySlug };
}

/* ---------------------------------------------------------------- linking */

/**
 * Renders one string, turning any guide title it mentions into a link.
 * A guide is linked once per passage — three links to the same page in one
 * paragraph reads as a mistake rather than a cross-reference.
 */
export function Linked({ text, exclude }: { text: string; exclude?: string }) {
  const rows = useCatalogue();
  const matcher = useMemo(() => buildMatcher(rows, exclude ?? ""), [rows, exclude]);

  const parts = useMemo(() => {
    if (!matcher) return null;
    const out: ReactNode[] = [];
    const seen = new Set<string>();
    let cursor = 0;
    for (const hit of text.matchAll(matcher.re)) {
      const guide = matcher.bySlug.get(hit[0].toLowerCase());
      if (!guide || seen.has(guide.slug) || hit.index === undefined) continue;
      seen.add(guide.slug);
      out.push(text.slice(cursor, hit.index));
      out.push(<GuidePeek key={`${guide.slug}-${hit.index}`} guide={guide} label={hit[0]} />);
      cursor = hit.index + hit[0].length;
    }
    if (out.length === 0) return null;
    out.push(text.slice(cursor));
    return out;
  }, [matcher, text]);

  return <>{parts ?? text}</>;
}

/** Convenience for the common case: a list of paragraphs. */
export function LinkedParagraphs({ items, exclude }: { items: string[]; exclude?: string }) {
  return (
    <>
      {items.map((line) => (
        <p key={line}>
          <Linked text={line} exclude={exclude} />
        </p>
      ))}
    </>
  );
}

/* ---------------------------------------------------------------- preview */

const OPEN_AFTER = 120;
const CLOSE_AFTER = 180;

function GuidePeek({ guide, label }: { guide: GuideCard; label: string }) {
  const [open, setOpen] = useState(false);
  const [above, setAbove] = useState(false);
  const wrap = useRef<HTMLSpanElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => () => clearTimeout(timer.current), []);

  const show = () => {
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      const box = wrap.current?.getBoundingClientRect();
      // Flip above when there is not room below for the card.
      if (box) setAbove(window.innerHeight - box.bottom < 240);
      setOpen(true);
    }, OPEN_AFTER);
  };

  const hide = () => {
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setOpen(false), CLOSE_AFTER);
  };

  return (
    <span className="xwrap" ref={wrap} onMouseEnter={show} onMouseLeave={hide}>
      <Link className="xlink" to={`/entry/${guide.slug}`} onFocus={show} onBlur={hide}>
        {label}
      </Link>
      {/* Visual only: the link text and its destination already carry the meaning. */}
      <span
        className={`xcard${open ? " xcard--in" : ""}${above ? " xcard--up" : ""}`}
        aria-hidden="true"
      >
        <span className="xcard__top">
          <TypeGlyph type={guide.larp.entry_type} label />
          <ReadCount count={guide.view_count} compact />
        </span>
        <span className="xcard__name">{guide.title}</span>
        <VerdictBadge verdict={guide.larp.verdict} />
        <span className="xcard__dek">{guide.larp.dek || guide.summary}</span>
        <span className="xcard__go">Open entry →</span>
      </span>
    </span>
  );
}
