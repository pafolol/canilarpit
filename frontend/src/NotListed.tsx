import { SubmitBox } from "./components";

export default function NotListed({ slug, note }: { slug?: string; note?: string }) {
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
        {!note && <SubmitBox />}
      </section>
    </div>
  );
}
