import { Link, useLocation } from "react-router-dom";
import { useDocumentTitle } from "./useDocumentTitle";

type Receipt = { message?: string; guideSlug?: string; guideTitle?: string };

/**
 * Where a submission lands once it is accepted.
 *
 * The form used to swap itself for a confirmation in place, which works but
 * leaves the reader on `/submit` with nothing to link to, nothing in history,
 * and no distinct URL to count as a conversion. The receipt arrives through
 * router state, so a direct visit still renders — it just says less.
 */
export default function Thanks() {
  const { state } = useLocation() as { state: Receipt | null };
  useDocumentTitle(
    "Thank you",
    "Your submission is with the editors. Somebody reads every one within 48 hours.",
  );

  return (
    <div className="u-shell">
      <section className="notlisted">
        <h1 className="hero__q">Thank you.</h1>
        <p className="notlisted__p">
          {state?.message ??
            "Your submission is with the editors, and somebody reads every one of them."}
        </p>
        <p className="notlisted__p">
          An editor reads every submission <strong>within 48 hours</strong>. If it gets
          written up, your name goes on the entry as "Suggested by" — if you asked for it
          to.
        </p>

        {state?.guideSlug ? (
          <p className="notlisted__p">
            We already have one on this:{" "}
            <Link to={`/entry/${state.guideSlug}`}>{state.guideTitle}</Link>.
          </p>
        ) : null}

        <p className="notlisted__p">
          <Link to="/">← Back to the search</Link>
          <span className="ftr__sep" aria-hidden="true">
            ·
          </span>
          <Link to="/submit">Submit another</Link>
        </p>
      </section>
    </div>
  );
}
