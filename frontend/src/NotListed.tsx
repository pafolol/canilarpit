import { Link } from "react-router-dom";
import { SubmitBox } from "./components";
import { useDocumentTitle } from "./useDocumentTitle";

const asTopic = (slug?: string) =>
  (slug ?? "").replace(/^\/+/, "").replace(/[-_/]+/g, " ").trim();

/**
 * The catch-all: a URL with nothing behind it.
 *
 * The server answers these with a real 404 status, so this is the page a
 * crawler is told not to keep and a reader is invited to fill in.
 */
export default function NotListed({ slug }: { slug?: string }) {
  useDocumentTitle("Not listed yet");
  const topic = asTopic(slug);

  return (
    <div className="u-shell">
      <section className="notlisted">
        <h1 className="hero__q">Not listed yet.</h1>
        <p className="notlisted__p">
          Nothing here matches <span className="u-data">{slug}</span>. It may not have
          been written, or it may have been written under a different name.
        </p>
        <SubmitBox topic={topic} />
        <p className="empty__offer">
          Know this one?{" "}
          <Link to={`/submit?topic=${encodeURIComponent(topic)}`}>Submit it yourself</Link>{" "}
          and we will write it up.
        </p>
      </section>
    </div>
  );
}
