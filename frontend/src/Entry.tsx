import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, api, clockOf, type GuideCard, type GuideDetail, type Media } from "./api";
import {
  CribBlock,
  ErrorState,
  ExposureClock,
  FlagChips,
  Loading,
  TellsList,
  TypeGlyph,
  VerdictBadge,
  clockLabel,
} from "./components";
import NotListed from "./NotListed";

type Block = { id: string; label: string; node: ReactNode };

export default function Entry() {
  const { slug = "" } = useParams();
  const [entry, setEntry] = useState<GuideDetail | null>(null);
  const [related, setRelated] = useState<GuideCard[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(true);
  const [active, setActive] = useState("");
  const [sheet, setSheet] = useState(false);
  const head = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    setBusy(true);
    setEntry(null);
    setError(null);
    api
      .guide(slug)
      .then((detail) => {
        if (cancelled) return;
        setEntry(detail);
        // Recording the view is a member feature; failing it must not break the page.
        api
          .related(slug)
          .then((rows) => !cancelled && setRelated(rows))
          .catch(() => undefined);
      })
      .catch((cause) => !cancelled && setError(cause))
      .finally(() => !cancelled && setBusy(false));
    return () => {
      cancelled = true;
    };
  }, [slug]);

  const larp = entry?.content.larp;
  const stop = larp?.verdict === "dont";
  const blocks: Block[] = !entry || !larp ? [] : buildBlocks(entry);

  useEffect(() => {
    const el = head.current;
    if (!el) return;
    const ro = new ResizeObserver(() =>
      document.documentElement.style.setProperty("--head-h", `${el.offsetHeight}px`),
    );
    ro.observe(el);
    return () => ro.disconnect();
  }, [slug, entry]);

  useEffect(() => {
    if (!entry) return;
    const obs = new IntersectionObserver(
      (records) => {
        const first = records
          .filter((r) => r.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        if (first) setActive(first.target.id);
      },
      { rootMargin: "-26% 0px -58% 0px" },
    );
    for (const b of blocks) {
      const el = document.getElementById(b.id);
      if (el) obs.observe(el);
    }
    return () => obs.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug, entry]);

  if (busy) {
    return (
      <div className="u-shell">
        <Loading what="the entry" />
      </div>
    );
  }
  if (error instanceof ApiError && error.status === 404) return <NotListed slug={slug} />;
  if (error) {
    return (
      <div className="u-shell">
        <ErrorState error={error} />
      </div>
    );
  }
  if (!entry || !larp) return <NotListed slug={slug} />;

  const clock = clockOf(larp);
  const hero = entry.media.find((m) => m.role === "hero") ?? entry.media[0] ?? null;
  const gallery = entry.media.filter((m) => m !== hero);

  const jump = blocks.map((b) => (
    <a
      key={b.id}
      className="rail__jumplink"
      href={`#${b.id}`}
      aria-current={active === b.id ? "true" : undefined}
    >
      {b.label}
    </a>
  ));

  return (
    <div className="u-shell">
      {/* mobile only */}
      <div className="entrybar">
        <TypeGlyph type={larp.entry_type} label />
        <ExposureClock seconds={clock} running={!stop} className="entrybar__clock" />
        <button className="entrybar__index" onClick={() => setSheet(true)} aria-expanded={sheet}>
          Index
        </button>
      </div>

      <div className="entry">
        <aside className="rail">
          <TypeGlyph type={larp.entry_type} label />

          <div className="rail__clockwrap">
            <ExposureClock seconds={clock} running={!stop} size="l" />
            <p className="u-label rail__clocklabel">{clock === null ? "no clock" : "to exposure"}</p>
            {/* Spoken once. The digits above stay aria-hidden. */}
            <p className="u-sr">{clockLabel(clock)}</p>
          </div>

          <FlagChips flags={larp.flags} stack />

          <nav className="rail__jump" aria-label="Sections">
            <p className="u-label rail__jumphead">Sections</p>
            {jump}
          </nav>

          <p className="rail__meta">
            <Link className="rail__cat" to={`/category/${entry.category.slug}`}>
              {entry.category.title}
            </Link>
          </p>
        </aside>

        <article className="doc">
          <div className="doc__head" ref={head}>
            <div className="doc__type">
              <TypeGlyph type={larp.entry_type} label />
            </div>
            <div className="doc__title">
              <h1 className="doc__name">{entry.title}</h1>
              <VerdictBadge verdict={larp.verdict} size="m" />
            </div>
            <p className="doc__dek">{larp.dek}</p>
            {entry.content.spoiler_warning && (
              <p className="doc__spoiler">Spoilers below. That is the point.</p>
            )}
          </div>

          {hero && <Figure media={hero} />}

          {blocks.map((b) => (
            <div key={b.id}>{b.node}</div>
          ))}

          {gallery.length > 0 && (
            <section className="sec" aria-labelledby="gallery-h">
              <h2 className="sec__h" id="gallery-h">References</h2>
              <div className="gallery">
                {gallery.map((media) => (
                  <Figure key={media.id} media={media} />
                ))}
              </div>
            </section>
          )}

          {entry.sources.length > 0 && (
            <section className="sec" id="sources" aria-labelledby="sources-h">
              <h2 className="sec__h" id="sources-h">Sources</h2>
              <ol className="sources">
                {entry.sources.map((source) => (
                  <li key={source.key}>
                    <a href={source.url} target="_blank" rel="noreferrer noopener">
                      {source.title}
                    </a>
                    {source.publisher ? <span className="sources__pub"> — {source.publisher}</span> : null}
                  </li>
                ))}
              </ol>
            </section>
          )}

          {related.length > 0 && (
            <section className="sec" aria-labelledby="related-h">
              <h2 className="sec__h" id="related-h">Next door</h2>
              <ul className="related">
                {related.map((item) => (
                  <li key={item.slug}>
                    <Link to={`/entry/${item.slug}`}>{item.title}</Link>
                    <VerdictBadge verdict={item.larp.verdict} />
                  </li>
                ))}
              </ul>
            </section>
          )}
        </article>
      </div>

      {sheet && (
        <>
          <button className="sheet__scrim" aria-label="Close index" onClick={() => setSheet(false)} />
          <nav className="sheet" aria-label="Sections">
            <p className="u-label">Sections</p>
            {blocks.map((b) => (
              <a key={b.id} className="sheet__link" href={`#${b.id}`} onClick={() => setSheet(false)}>
                {b.label}
              </a>
            ))}
          </nav>
        </>
      )}
    </div>
  );
}

function buildBlocks(entry: GuideDetail): Block[] {
  const larp = entry.content.larp;
  const stop = larp.verdict === "dont";
  const content = entry.content;

  const costBlock: Block = {
    id: "cost",
    label: "cost",
    node: (
      <Section id="cost" heading="Cost of getting caught">
        {larp.cost.map((p) => (
          <p key={p}>{p}</p>
        ))}
      </Section>
    ),
  };

  const blocks: Block[] = [];

  // A DON'T entry drops the crib sheet entirely and opens on the cost.
  if (!stop && larp.crib.length > 0) {
    blocks.push({
      id: "crib",
      label: "crib",
      node: <CribBlock id="crib" title={entry.title} sections={larp.crib} />,
    });
  }

  if (stop) {
    blocks.push(costBlock);
  } else if (larp.surface.length > 0) {
    blocks.push({
      id: "surface",
      label: "surface",
      node: (
        <Section id="surface" heading="The surface layer">
          {larp.surface.map((p) => (
            <p key={p}>{p}</p>
          ))}
        </Section>
      ),
    });
  }

  blocks.push({
    id: "follow-up",
    label: "follow-up",
    node: (
      <Section id="follow-up" heading="The follow-up that kills you">
        <p className="sec__pull">{larp.follow_up[0]}</p>
        {larp.follow_up.slice(1).map((p) => (
          <p key={p}>{p}</p>
        ))}
      </Section>
    ),
  });

  blocks.push({
    id: "tells",
    label: "tells",
    node: (
      <Section id="tells" heading="Tells">
        <TellsList tells={larp.tells} />
      </Section>
    ),
  });

  if (content.quick_brief.length > 0) {
    blocks.push({
      id: "brief",
      label: "brief",
      node: (
        <Section id="brief" heading="The brief">
          <ul className="brief">
            {content.quick_brief.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          {content.overview
            .split("\n\n")
            .filter(Boolean)
            .map((p) => (
              <p key={p}>{p}</p>
            ))}
        </Section>
      ),
    });
  }

  if (content.vocabulary.length > 0) {
    blocks.push({
      id: "words",
      label: "words",
      node: (
        <Section id="words" heading="The words">
          <dl className="vocab">
            {content.vocabulary.map((item) => (
              <div className="vocab__row" key={item.term}>
                <dt>{item.term}</dt>
                <dd>
                  {item.meaning}
                  {item.example ? <span className="vocab__eg"> {item.example}</span> : null}
                </dd>
              </div>
            ))}
          </dl>
        </Section>
      ),
    });
  }

  if (content.questions.length > 0) {
    blocks.push({
      id: "asked",
      label: "asked",
      node: (
        <Section id="asked" heading="What you will be asked">
          <dl className="qa">
            {content.questions.map((item) => (
              <div className="qa__row" key={item.question}>
                <dt>{item.question}</dt>
                <dd>{item.answer}</dd>
              </div>
            ))}
          </dl>
        </Section>
      ),
    });
  }

  if (!stop) blocks.push(costBlock);

  blocks.push({
    id: "learn",
    label: "just learn it",
    node: (
      <Section id="learn" heading="Just learn it">
        <div className="learn">
          <div className="learn__row">
            <span className="u-label">Hours</span>
            <span className="u-data">{larp.learn.hours.toLocaleString("en-GB")}</span>
          </div>
          <div className="learn__row">
            <span className="u-label">The one book</span>
            <span>{larp.learn.book}</span>
          </div>
          <div className="learn__row">
            <span className="u-label">The one thing to make</span>
            <span>{larp.learn.make}</span>
          </div>
        </div>
      </Section>
    ),
  });

  return blocks;
}

function Figure({ media }: { media: Media }) {
  if (!media.url) return null;
  return (
    <figure className="figure">
      <img src={media.url} alt={media.alt_text} loading="lazy" />
      <figcaption>
        {media.caption ? <span>{media.caption} </span> : null}
        {media.kind === "generated" ? <span className="figure__gen">Generated image. </span> : null}
        {media.attribution ? (
          media.source_page_url ? (
            <a href={media.source_page_url} target="_blank" rel="noreferrer noopener">
              {media.attribution}
            </a>
          ) : (
            <span>{media.attribution}</span>
          )
        ) : null}
      </figcaption>
    </figure>
  );
}

function Section({ id, heading, children }: { id: string; heading: string; children: ReactNode }) {
  return (
    <section className="sec" id={id} aria-labelledby={`${id}-h`}>
      <h2 className="sec__h" id={`${id}-h`}>{heading}</h2>
      {children}
    </section>
  );
}
