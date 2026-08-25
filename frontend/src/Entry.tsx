import { useEffect, useRef, useState, type ReactNode } from "react";
import { useParams } from "react-router-dom";
import {
  CribBlock,
  ExposureClock,
  FlagChips,
  TellsList,
  TypeGlyph,
  VerdictBadge,
  clockLabel,
} from "./components";
import { bySlug } from "./data";
import NotListed from "./NotListed";

type Block = { id: string; label: string; node: ReactNode };

export default function Entry() {
  const { slug = "" } = useParams();
  const entry = bySlug(slug);
  const [active, setActive] = useState("");
  const [sheet, setSheet] = useState(false);
  const head = useRef<HTMLDivElement>(null);

  const stop = entry?.verdict === "DON'T";

  const blocks: Block[] = !entry
    ? []
    : [
        // ⛔️ entries drop the crib block entirely and open on the cost.
        ...(stop
          ? []
          : [
              {
                id: "crib",
                label: "crib",
                node: <CribBlock id="crib" title={entry.name} sections={entry.crib} />,
              },
            ]),
        ...(stop
          ? [
              {
                id: "cost",
                label: "cost",
                node: (
                  <Section id="cost" heading="Cost of getting caught">
                    {entry.cost.map((p) => (
                      <p key={p}>{p}</p>
                    ))}
                  </Section>
                ),
              },
            ]
          : [
              {
                id: "surface",
                label: "surface",
                node: (
                  <Section id="surface" heading="The surface layer">
                    {entry.surface.map((p) => (
                      <p key={p}>{p}</p>
                    ))}
                  </Section>
                ),
              },
            ]),
        {
          id: "follow-up",
          label: "follow-up",
          node: (
            <Section id="follow-up" heading="The follow-up that kills you">
              <p className="sec__pull">{entry.followUp[0]}</p>
              {entry.followUp.slice(1).map((p) => (
                <p key={p}>{p}</p>
              ))}
            </Section>
          ),
        },
        {
          id: "tells",
          label: "tells",
          node: (
            <Section id="tells" heading="Tells">
              <TellsList tells={entry.tells} />
            </Section>
          ),
        },
        ...(stop
          ? []
          : [
              {
                id: "cost",
                label: "cost",
                node: (
                  <Section id="cost" heading="Cost of getting caught">
                    {entry.cost.map((p) => (
                      <p key={p}>{p}</p>
                    ))}
                  </Section>
                ),
              },
            ]),
        {
          id: "learn",
          label: "just learn it",
          node: (
            <Section id="learn" heading="Just learn it">
              <div className="learn">
                <div className="learn__row">
                  <span className="u-label">Hours</span>
                  <span className="u-data">{entry.learn.hours.toLocaleString("en-GB")}</span>
                </div>
                <div className="learn__row">
                  <span className="u-label">The one book</span>
                  <span>{entry.learn.book}</span>
                </div>
                <div className="learn__row">
                  <span className="u-label">The one thing to make</span>
                  <span>{entry.learn.make}</span>
                </div>
              </div>
            </Section>
          ),
        },
      ];

  useEffect(() => {
    const el = head.current;
    if (!el) return;
    const ro = new ResizeObserver(() =>
      document.documentElement.style.setProperty("--head-h", `${el.offsetHeight}px`),
    );
    ro.observe(el);
    return () => ro.disconnect();
  }, [slug]);

  useEffect(() => {
    if (!blocks.length) return;
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
  }, [slug]);

  if (!entry) return <NotListed slug={slug} />;

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
        <TypeGlyph type={entry.type} label />
        <ExposureClock
          seconds={entry.clock}
          running={!stop}
          className="entrybar__clock"
        />
        <button className="entrybar__index" onClick={() => setSheet(true)} aria-expanded={sheet}>
          Index
        </button>
      </div>

      <div className="entry">
        <aside className="rail">
          <TypeGlyph type={entry.type} label />

          <div className="rail__clockwrap">
            <ExposureClock seconds={entry.clock} running={!stop} size="l" />
            <p className="u-label rail__clocklabel">
              {entry.clock === null ? "no clock" : "to exposure"}
            </p>
            {/* Spoken once. The digits above stay aria-hidden. */}
            <p className="u-sr">{clockLabel(entry.clock)}</p>
          </div>

          <FlagChips flags={entry.flags} stack />

          <nav className="rail__jump" aria-label="Sections">
            <p className="u-label rail__jumphead">Sections</p>
            {jump}
          </nav>
        </aside>

        <article className="doc">
          <div className="doc__head" ref={head}>
            <div className="doc__type">
              <TypeGlyph type={entry.type} label />
            </div>
            <div className="doc__title">
              <h1 className="doc__name">{entry.name}</h1>
              <VerdictBadge verdict={entry.verdict} size="m" />
            </div>
            <p className="doc__dek">{entry.dek}</p>
          </div>
          {blocks.map((b) => (
            <div key={b.id}>{b.node}</div>
          ))}
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

function Section({ id, heading, children }: { id: string; heading: string; children: ReactNode }) {
  return (
    <section className="sec" id={id} aria-labelledby={`${id}-h`}>
      <h2 className="sec__h" id={`${id}-h`}>{heading}</h2>
      {children}
    </section>
  );
}
