import { Link } from "react-router-dom";
import { useDocumentTitle } from "./useDocumentTitle";

/**
 * The five questions the site actually gets asked.
 *
 * No FAQPage schema: Google stopped rendering those results for everybody
 * except health and government sites in 2023, and the markup would mean
 * keeping a second copy of this prose in `api/routes/site.py`.
 */

const FAQS: { q: string; a: React.ReactNode }[] = [
  {
    q: "What does it mean to larp something?",
    a: (
      <>
        To present yourself as knowing or being something you do not — a film you never
        watched, a scene you do not belong to, a job you do not do. Every entry is the
        briefing you would read beforehand: what to say, what gives you away, and how
        long it holds before somebody asks the question that collapses it.
      </>
    ),
  },
  {
    q: "What do the four verdicts mean?",
    a: (
      <>
        <strong>YES</strong> holds indefinitely. <strong>KINDA</strong> holds at the bar
        and fails at the table. <strong>TALK ONLY</strong> means the conversation holds
        but the doing does not — you can discuss the instrument, you cannot play it.{" "}
        <strong>DON'T</strong> is reserved for claims that endanger or defraud someone,
        and those entries exist to say so.
      </>
    ),
  },
  {
    q: "Where do the guides come from?",
    a: (
      <>
        A model writes the first draft and every source URL in it is fetched: dead links
        are dropped, along with the citations that pointed at them. Then an editor checks
        it and a person publishes it. Nothing reaches the site unpublished by a human,
        and an entry with no honest counter says so rather than inventing one.
      </>
    ),
  },
  {
    q: "Can I suggest an entry?",
    a: (
      <>
        Yes — <Link to="/submit">submit it</Link>. Tell us what the thing is and what
        somebody would need to know to hold a conversation about it. An editor reads
        every submission within 48 hours. If it gets written up, your name goes on the
        entry as "Suggested by" if you want it there.
      </>
    ),
  },
  {
    q: "Do you track me?",
    a: (
      <>
        No account, no ad network, and no raw IP address stored anywhere. Reads and the
        "who is here now" count are kept against a one-way hash, which is enough to count
        against and useless for identifying anybody. The one{" "}
        <Link to="/advertise">ad slot</Link> is a line of text served from here, so
        nothing on it can follow you either. The{" "}
        <Link to="/privacy">privacy page</Link> says exactly what is kept and for how
        long.
      </>
    ),
  },
];

export default function Faq() {
  useDocumentTitle(
    "Questions",
    "What larping means here, what the four verdicts mean, where the guides come from, and what the site keeps.",
  );

  return (
    <div className="u-shell">
      <section className="notlisted">
        <h1 className="hero__q">Questions.</h1>
        <p className="notlisted__p">
          Five of them, answered honestly. If yours is not here,{" "}
          <Link to="/submit">tell us</Link>.
        </p>

        <dl className="faq">
          {FAQS.map((item) => (
            <div className="faq__item" key={item.q}>
              <dt className="faq__q">{item.q}</dt>
              <dd className="faq__a">{item.a}</dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}
