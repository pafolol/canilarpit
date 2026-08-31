import { useEffect, useState } from "react";
import { api, type Category, type EntryType, type GuideCard, type Page, type Verdict } from "./api";
import {
  EntryCard,
  ErrorState,
  FilterBar,
  Loading,
  NewsletterBox,
  SearchField,
  SubmitBox,
  TickerRow,
  useFilters,
} from "./components";
import SubmissionForm from "./SubmissionForm";
import { caught } from "./data";

const PAGE_SIZE = 48;

export default function Home({ category }: { category?: string }) {
  const f = useFilters();
  const activeCategory = category ?? f.category;

  const [categories, setCategories] = useState<Category[]>([]);
  const [newest, setNewest] = useState<GuideCard[]>([]);
  const [result, setResult] = useState<Page<GuideCard> | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [reloads, setReloads] = useState(0);

  useEffect(() => {
    api.categories().then(setCategories).catch(() => setCategories([]));
    api
      .guides({ sort: "newest", page_size: 20 })
      .then((page) => setNewest(page.items))
      .catch(() => setNewest([]));
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
        sort: f.q ? "relevance" : "newest",
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
          <Loading />
        ) : items.length === 0 ? (
          <div className="empty">
            {f.q ? (
              <>
                <p>
                  Nothing written for <span className="u-data">{f.q}</span> yet.
                </p>
                <SubmissionForm topic={f.q} />
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

        {items.length > 0 && <SubmitBox />}

        <section className="caught">
          <h2 className="caught__h">Caught</h2>
          <p className="caught__sub">Three collapses, and the question that did it.</p>
          <ul className="caught__list">
            {caught.map((c) => (
              <li className="caught__item" key={c.question}>
                <p className="u-label caught__where">{c.where}</p>
                <p className="caught__q">&ldquo;{c.question}&rdquo;</p>
                <p className="caught__after">{c.after}</p>
              </li>
            ))}
          </ul>
        </section>

        <NewsletterBox />
      </div>
    </>
  );
}
