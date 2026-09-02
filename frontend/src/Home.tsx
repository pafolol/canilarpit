import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AdSlot } from "./ads";
import {
  api,
  type Category,
  type EntryType,
  type GuideCard,
  type LearnPage,
  type Page,
  type Verdict,
} from "./api";
import {
  EntryCard,
  ErrorState,
  FilterBar,
  NewsletterBox,
  SearchField,
  Skeleton,
  SubmitBox,
  TickerRow,
  useFilters,
  VerdictBadge,
} from "./components";
import { useDocumentTitle } from "./useDocumentTitle";

const PAGE_SIZE = 48;

export default function Home({ category }: { category?: string }) {
  const f = useFilters();
  const activeCategory = category ?? f.category;

  const [categories, setCategories] = useState<Category[]>([]);
  const [newest, setNewest] = useState<GuideCard[]>([]);
  const [popular, setPopular] = useState<GuideCard[]>([]);
  const [learn, setLearn] = useState<LearnPage | null>(null);
  const [result, setResult] = useState<Page<GuideCard> | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [reloads, setReloads] = useState(0);

  // A category page names itself; the front page keeps the bare mark.
  const categoryTitle = categories.find((item) => item.slug === category)?.title;
  useDocumentTitle(
    category ? (categoryTitle ?? category) : "canilarpit",
    category
      ? `Everything written under ${categoryTitle ?? category}, and how long each one holds.`
      : "Can you larp it, and for how long? One reference card per scene, taste and role.",
  );

  useEffect(() => {
    api.categories().then(setCategories).catch(() => setCategories([]));
    api
      .guides({ sort: "newest", page_size: 20 })
      .then((page) => setNewest(page.items))
      .catch(() => setNewest([]));
    api
      .guides({ sort: "popular", page_size: 8 })
      // Nothing anybody has opened yet is not a ranking, it is a list. It stays
      // hidden until there is something to rank.
      .then((page) => setPopular(page.items.filter((item) => item.view_count > 0)))
      .catch(() => setPopular([]));
    api
      .learn()
      .then(setLearn)
      .catch(() => setLearn(null));
  }, []);

  const typeKey = f.types.join(",");
  const verdictKey = f.verdicts.join(",");

  useEffect(() => {
    let cancelled = false;
    setBusy(true);
    api
      .guides({
        q: f.q || undefined,
        category: activeCategory || undefined,
        entry_type: typeKey ? (typeKey.split(",") as EntryType[]) : [],
        verdict: verdictKey ? (verdictKey.split(",") as Verdict[]) : [],
        // Most larped first. A search still sorts by relevance: what somebody
        // typed beats what everybody else read.
        sort: f.q ? "relevance" : "popular",
        page_size: PAGE_SIZE,
      })
      .then((page) => {
        if (cancelled) return;
        setResult(page);
        setError(null);
      })
      .catch((cause) => {
        if (!cancelled) setError(cause);
      })
      .finally(() => {
        if (!cancelled) setBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [f.q, activeCategory, typeKey, verdictKey, reloads]);

  const items = result?.items ?? [];
  const total = result?.pagination.total ?? 0;

  return (
    <>
      <div className="u-shell">
        <header className="hero">
          <p className="hero__lede">
            <span className="hero__n">{total}</span> {total === 1 ? "entry" : "entries"}
            {activeCategory ? ` in ${activeCategory}` : ""}. One question each:
          </p>
          <h1 className="hero__q">Can you larp it, and for how long?</h1>
        </header>

        <SearchField
          value={f.q}
          onChange={f.setQuery}
          busy={busy}
          count={result ? total : null}
        />
      </div>

      <TickerRow entries={newest} />

      <FilterBar f={f} count={items.length} categories={categories} lockCategory={category} />

      <div className="u-shell">
        {error ? (
          <ErrorState error={error} retry={() => setReloads((n) => n + 1)} />
        ) : busy && !result ? (
          <Skeleton variant="cards" count={8} />
        ) : items.length === 0 ? (
          <div className="empty">
            {f.q ? (
              <>
                <p>
                  Nothing written for <span className="u-data">{f.q}</span> yet.
                </p>
                <SubmitBox topic={f.q} />
                <p className="empty__offer">
                  Know this one?{" "}
                  <Link to={`/submit?topic=${encodeURIComponent(f.q)}`}>
                    Submit it yourself
                  </Link>{" "}
                  and we will write it up.
                </p>
              </>
            ) : (
              <>
                <p>No entries match. Loosen a filter.</p>
                <button onClick={f.clear}>Clear all filters</button>
              </>
            )}
          </div>
        ) : (
          <div className="grid">
            {items.map((entry) => (
              <EntryCard key={entry.slug} entry={entry} />
            ))}
          </div>
        )}

        <AdSlot />

        {popular.length > 0 && (
          <section className="band ranked" aria-labelledby="ranked-h">
            <h2 className="band__h" id="ranked-h">Most larped</h2>
            <p className="band__sub">What people actually opened. One read per person per entry.</p>
            <ol className="ranked__list">
              {popular.map((entry, index) => (
                <li className="ranked__row" key={entry.slug}>
                  <span className="ranked__pos" aria-hidden="true">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <Link className="ranked__name" to={`/entry/${entry.slug}`}>
                    {entry.title}
                  </Link>
                  <VerdictBadge verdict={entry.larp.verdict} />
                  <span className="ranked__n">{entry.view_count.toLocaleString("en-GB")}</span>
                </li>
              ))}
            </ol>
          </section>
        )}

        <LearnBand page={learn} />

        <NewsletterBox />
      </div>
    </>
  );
}

const HOURS = new Intl.NumberFormat("en-GB");

/**
 * The other answer, given the room it deserves.
 *
 * It was one word in the footer, which is nowhere. The whole premise of the
 * site is that larping something has a cost and learning it has a price, and
 * this is the price: real hours, out of the entries themselves, with the three
 * cheapest named so the number is not just a number.
 */
function LearnBand({ page }: { page: LearnPage | null }) {
  if (!page || page.items.length === 0) return null;
  const cheapest = page.items.slice(0, 3);

  return (
    <section className="band learnband" aria-labelledby="learn-h">
      <div className="learnband__top">
        <div>
          <h2 className="band__h" id="learn-h">Or just learn it</h2>
          <p className="band__sub">
            Every entry priced in the hours it takes to actually know the thing.
          </p>
        </div>
        <p className="learnband__total">
          <span className="learnband__n">{HOURS.format(page.total_hours)}</span>
          <span className="u-label">hours, all in</span>
        </p>
      </div>

      <ul className="learnband__list">
        {cheapest.map((row) => (
          <li className="learnband__row" key={row.slug}>
            <span className="learnband__hours">{HOURS.format(row.hours)}h</span>
            <Link className="learnband__name" to={`/entry/${row.slug}`}>
              {row.title}
            </Link>
            <VerdictBadge verdict={row.verdict} />
          </li>
        ))}
      </ul>

      <Link className="learnband__cta" to="/just-learn-it">
        All {page.items.length} entries, cheapest first →
      </Link>
    </section>
  );
}
