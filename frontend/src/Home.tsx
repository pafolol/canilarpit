import { FilterBar, EntryCard, SubmitBox, NewsletterBox, TickerRow, useFilters } from "./components";
import { caught, entries } from "./data";

export default function Home({ category }: { category?: string }) {
  const f = useFilters();
  const pool = category ? entries.filter((e) => e.category === category) : entries;
  const shown = pool.filter(f.match);

  return (
    <>
      <div className="u-shell">
        <header className="hero">
          <p className="hero__lede">
            <span className="hero__n">{pool.length}</span> entries
            {category ? ` in ${category}` : ""}. One question each:
          </p>
          <h1 className="hero__q">Can you larp it, and for how long?</h1>
        </header>
      </div>

      <TickerRow entries={category ? pool : entries} />

      <FilterBar f={f} count={shown.length} lockCategory={category} />

      <div className="u-shell">
        <div className="grid">
          {shown.length === 0 ? (
            <div className="empty">
              <p>No entries match. Loosen a filter.</p>
              <button onClick={f.clear}>Clear all filters</button>
            </div>
          ) : (
            shown.map((e) => <EntryCard key={e.slug} entry={e} />)
          )}
        </div>

        <SubmitBox />

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
