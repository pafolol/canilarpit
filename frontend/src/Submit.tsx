import { Link, useSearchParams } from "react-router-dom";
import SubmissionForm from "./SubmissionForm";

/**
 * The long version, on its own page.
 *
 * The empty state offers the one-line request first, because most people only
 * want to say "write this one". This is for the reader who already knows the
 * subject and is willing to spend five minutes on it.
 */
export default function Submit() {
  const [params] = useSearchParams();
  const topic = params.get("topic") ?? "";

  return (
    <div className="u-shell">
      <section className="notlisted">
        <h1 className="hero__q">Write it with us.</h1>
        <p className="notlisted__p">
          You know something we have not written down. Tell us what, and what somebody
          would need to hold a conversation about it. An editor reads every one of these,
          checks it, and your name goes on the entry if you want it there.
        </p>
        <SubmissionForm topic={topic} />
        <p className="notlisted__p">
          <Link to={topic ? `/?q=${encodeURIComponent(topic)}` : "/"}>
            ← Back to the search
          </Link>
        </p>
      </section>
    </div>
  );
}
