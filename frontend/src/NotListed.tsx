import { Link } from "react-router-dom";
import { SubmitBox } from "./components";
import { useDocumentTitle } from "./useDocumentTitle";

const asTopic = (slug?: string) =>
  (slug ?? "").replace(/^\/+/, "").replace(/[-_/]+/g, " ").trim();

export default function NotListed({ slug, note }: { slug?: string; note?: string }) {
  useDocumentTitle(note ? "Not built yet" : "Not listed yet");
  return (
    <div className="u-shell">
      <section className="notlisted">
        <h1 className="hero__q">{note ? "Not built yet." : "Not listed yet."}</h1>
        <p className="notlisted__p">
          {note ?? (
            <>
              Nothing here matches <span className="u-data">{slug}</span>. It may not have been written, or it may
              have been written under a different name.
            </>
          )}
        </p>
        {!note && (
          <>
            <SubmitBox topic={asTopic(slug)} />
            <p className="empty__offer">
              Know this one?{" "}
              <Link to={`/submit?topic=${encodeURIComponent(asTopic(slug))}`}>
                Submit it yourself
              </Link>{" "}
              and we will write it up.
            </p>
          </>
        )}
      </section>
    </div>
  );
}
