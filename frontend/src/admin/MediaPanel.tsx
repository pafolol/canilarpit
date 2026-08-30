import { useState } from "react";
import { ApiError, api, type Media, type StockImage } from "../api";

/**
 * Images for one guide.
 *
 * Placements live on the draft revision, assets are reusable, and only approved
 * assets reach the public page. Those three facts drive every control here.
 */
export default function MediaPanel({
  guideId,
  media,
  suggestions,
  onChanged,
}: {
  guideId: string;
  media: Media[];
  suggestions: string[];
  onChanged: () => void;
}) {
  const [query, setQuery] = useState(suggestions[0] ?? "");
  const [results, setResults] = useState<StockImage[]>([]);
  const [searching, setSearching] = useState(false);
  const [busyUrl, setBusyUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fail = (cause: unknown, fallback: string) =>
    setError(cause instanceof ApiError ? cause.message : fallback);

  const search = async (term: string) => {
    setQuery(term);
    if (!term.trim()) return;
    setSearching(true);
    setError(null);
    try {
      const found = await api.admin.stockSearch(term.trim());
      setResults(found.results);
    } catch (cause) {
      setResults([]);
      fail(cause, "Stock search failed.");
    } finally {
      setSearching(false);
    }
  };

  const attach = async (image: StockImage) => {
    setBusyUrl(image.remote_url);
    setError(null);
    try {
      const asset = await api.admin.createMedia({
        kind: "stock",
        provider: image.provider,
        remote_url: image.remote_url,
        source_page_url: image.source_page_url,
        attribution: image.attribution,
        license_name: image.license_name,
        license_url: image.license_url,
        alt_text: image.alt_text,
        width: image.width,
        height: image.height,
        metadata: { preview_url: image.preview_url, query },
        approval_status: "approved",
      });
      await api.admin.linkMedia(guideId, {
        media_asset_id: asset.id,
        role: media.length === 0 ? "hero" : "gallery",
        sort_order: media.length,
      });
      onChanged();
    } catch (cause) {
      fail(cause, "Could not attach that image.");
    } finally {
      setBusyUrl(null);
    }
  };

  const approve = async (item: Media, approved: boolean) => {
    setError(null);
    try {
      await api.admin.setMediaApproval(item.id, approved ? "approved" : "rejected");
      onChanged();
    } catch (cause) {
      fail(cause, "Could not change approval.");
    }
  };

  const unlink = async (item: Media) => {
    if (!item.link_id) return;
    setError(null);
    try {
      await api.admin.unlinkMedia(guideId, item.link_id);
      onChanged();
    } catch (cause) {
      fail(cause, "Could not remove that placement.");
    }
  };

  return (
    <section className="panel">
      <div className="panel__head">
        <h2 className="panel__h">Images</h2>
        <p className="panel__sub">
          Only approved images appear on the public page. Placements belong to the draft.
        </p>
      </div>

      {media.length === 0 ? (
        <p className="panel__empty">Nothing placed on this draft yet.</p>
      ) : (
        <ul className="mediaList">
          {media.map((item) => (
            <li className="mediaList__item" key={item.link_id ?? item.id}>
              {item.url ? <img src={item.url} alt={item.alt_text} loading="lazy" /> : null}
              <div className="mediaList__meta">
                <span className={`pill pill--${item.approval_status}`}>{item.approval_status}</span>
                <span className="mediaList__role">{item.role ?? "unplaced"}</span>
                <p className="mediaList__alt">{item.alt_text}</p>
                {item.attribution ? (
                  <p className="mediaList__credit">{item.attribution}</p>
                ) : null}
                <div className="mediaList__actions">
                  <button
                    className="chip"
                    onClick={() => approve(item, item.approval_status !== "approved")}
                  >
                    {item.approval_status === "approved" ? "Unapprove" : "Approve"}
                  </button>
                  {item.link_id ? (
                    <button className="chip" onClick={() => unlink(item)}>
                      Remove
                    </button>
                  ) : null}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      <form
        className="mediaSearch"
        onSubmit={(event) => {
          event.preventDefault();
          void search(query);
        }}
      >
        <label className="u-sr" htmlFor="stock-q">Stock image search</label>
        <input
          id="stock-q"
          className="af__input"
          value={query}
          placeholder="Search stock photographs"
          onChange={(event) => setQuery(event.target.value)}
        />
        <button className="btn" type="submit" disabled={searching}>
          {searching ? "searching…" : "Search"}
        </button>
      </form>

      {suggestions.length > 0 && (
        <div className="mediaSearch__hints">
          <span className="af__hint">From the guide:</span>
          {suggestions.slice(0, 6).map((term) => (
            <button key={term} className="chip" onClick={() => void search(term)}>
              {term}
            </button>
          ))}
        </div>
      )}

      {error && (
        <p className="admin__error" role="alert">
          {error}
        </p>
      )}

      {results.length > 0 && (
        <div className="stockGrid">
          {results.map((image) => (
            <figure className="stockGrid__item" key={image.remote_url}>
              <img src={image.preview_url ?? image.remote_url} alt={image.alt_text} loading="lazy" />
              <figcaption>{image.attribution}</figcaption>
              <button
                className="chip"
                disabled={busyUrl === image.remote_url}
                onClick={() => attach(image)}
              >
                {busyUrl === image.remote_url ? "attaching…" : "Attach"}
              </button>
            </figure>
          ))}
        </div>
      )}
    </section>
  );
}
