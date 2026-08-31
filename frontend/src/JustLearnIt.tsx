import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type LearnPage } from "./api";
import { ErrorState, Loading, TypeGlyph, VerdictBadge } from "./components";
import { useDocumentTitle } from "./useDocumentTitle";

const HOURS = new Intl.NumberFormat("en-GB");

/** Hours, in the unit a person can feel. A week is 40 of them. */
function weight(hours: number): string {
  if (hours < 40) return `${hours}h`;
  const weeks = Math.round(hours / 40);
  if (weeks < 52) return `${weeks} ${weeks === 1 ? "week" : "weeks"} full time`;
  const years = (hours / 2000).toFixed(1).replace(/\.0$/, "");
  return `${years} ${years === "1" ? "year" : "years"} full time`;
}

/**
 * The other answer to every entry on the site.
 *
 * Sorted by hours ascending, so it opens on the things that are cheaper to
 * learn than to fake. The verdict badge on each row is the whole joke: eight
 * hours against a YES is a shrug, and eight hundred against a DON'T is the only
 * route there has ever been.
 */
export default function JustLearnIt() {
  const [page, setPage] = useState<LearnPage | null>(null);
  const [sort, setSort] = useState<"hours" | "title">("hours");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(true);
  const [reloads, setReloads] = useState(0);

  useDocumentTitle(
    "Just learn it",
    "Every entry on the site, priced in hours: the one book, the one thing to make.",
  );

  useEffect(() => {
    let cancelled = false;
    setBusy(true);
    api
      .learn(sort)
      .then((result) => {
        if (cancelled) return;
        setPage(result);
        setError(null);
      })
      .catch((cause) => !cancelled && setError(cause))
      .finally(() => !cancelled && setBusy(false));
    return () => {
      cancelled = true;
    };
  }, [sort, reloads]);

  const items = page?.items ?? [];

  return (
    <div className="u-shell">
      <header className="hero">
        <p className="hero__lede">
          <span className="hero__n">{HOURS.format(page?.total_hours ?? 0)}</span> hours of actual
          study, across {items.length} {items.length === 1 ? "entry" : "entries"}. Or:
        </p>
        <h1 className="hero__q">Just learn it.</h1>
      </header>

      <p className="learnpage__note">
        Every entry carries the honest alternative to larping it: how long it takes, the one
        book, and the one thing to make. The verdict beside each is the part worth reading
        twice.
      </p>

      <div className="learnpage__sortbar">
        <button
          className="chip"
          aria-pressed={sort === "hours"}
          onClick={() => setSort("hours")}
        >
          cheapest first
        </button>
        <button
          className="chip"
          aria-pressed={sort === "title"}
          onClick={() => setSort("title")}
        >
          A–Z
        </button>
      </div>

      {error ? (
        <ErrorState error={error} retry={() => setReloads((n) => n + 1)} />
      ) : busy && !page ? (
        <Loading what="the hours" />
      ) : items.length === 0 ? (
        <p className="state">No entry has named its hours yet.</p>
      ) : (
        <ol className="learnlist">
          {items.map((row) => (
            <li className="learnrow" key={row.slug}>
              <div className="learnrow__hours">
                <span className="learnrow__n">{HOURS.format(row.hours)}</span>
                <span className="u-label">hours</span>
                <span className="learnrow__weight">{weight(row.hours)}</span>
              </div>
              <div className="learnrow__body">
                <div className="learnrow__top">
                  <TypeGlyph type={row.entry_type} />
                  <Link className="learnrow__name" to={`/entry/${row.slug}`}>
                    {row.title}
                  </Link>
                  <VerdictBadge verdict={row.verdict} />
                  <Link className="learnrow__cat" to={`/category/${row.category.slug}`}>
                    {row.category.title}
                  </Link>
                </div>
                <dl className="learnrow__pair">
                  <dt className="u-label">The one book</dt>
                  <dd>{row.book}</dd>
                  <dt className="u-label">The one thing to make</dt>
                  <dd>{row.make}</dd>
                </dl>
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
