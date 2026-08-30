import { useEffect, useState } from "react";
import {
  ApiError,
  api,
  type ImageCandidate,
  type ImageProviderInfo,
  type ImageQuery,
  type Media,
} from "../api";

/**
 * Images for one guide.
 *
 * Placements live on the draft revision, assets are reusable, and only approved
 * assets reach the public page. Which source to search matters as much as the
 * words: a fictional character is not in a stock photography library.
 */
export default function MediaPanel({
  guideId,
  media,
  brief,
  guideType,
  categorySlug,
  onChanged,
}: {
  guideId: string;
  media: Media[];
  brief: ImageQuery[];
  guideType?: string;
  categorySlug?: string;
  onChanged: () => void;
}) {
  const [providers, setProviders] = useState<ImageProviderInfo[]>([]);
  const [provider, setProvider] = useState<string>(brief[0]?.provider ?? "auto");
  const [query, setQuery] = useState(brief[0]?.query ?? "");
  const [results, setResults] = useState<ImageCandidate[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [searching, setSearching] = useState(false);
  const [busyUrl, setBusyUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.admin.imageProviders().then(setProviders).catch(() => setProviders([]));
  }, []);

  const fail = (cause: unknown, fallback: string) =>
    setError(cause instanceof ApiError ? cause.message : fallback);

  const search = async (term: string, providerId: string) => {
    setQuery(term);
    setProvider(providerId);
    if (!term.trim()) return;
    setSearching(true);
    setError(null);
    try {
      const found = await api.admin.imageSearch(term.trim(), {
        provider: providerId,
        guide_type: guideType,
        category: categorySlug,
      });
      setResults(found.results);
      setWarnings(found.warnings);
    } catch (cause) {
      setResults([]);
      setWarnings([]);
      fail(cause, "Image search failed.");
    } finally {
      setSearching(false);
    }
  };

  const attach = async (image: ImageCandidate) => {
    setBusyUrl(image.remote_url);
    setError(null);
    try {
      const asset = await api.admin.createMedia({
        // Promotional stills are not stock; recording that keeps the rights honest.
        kind: image.editorial_only ? "external" : "stock",
        provider: image.provider,
        remote_url: image.remote_url,
        source_page_url: image.source_page_url,
        attribution: image.attribution,
        license_name: image.license_name,
        license_url: image.license_url,
        alt_text: image.alt_text.slice(0, 500),
        width: image.width,
        height: image.height,
        metadata: {
          preview_url: image.preview_url,
          subject: image.subject,
          editorial_only: image.editorial_only,
          query,
        },
        approval_status: "approved",
      });
      await api.admin.linkMedia(guideId, {
        media_asset_id: asset.id,
        role: media.length === 0 ? "hero" : "gallery",
        caption: image.subject,
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

  const chosen = providers.find((item) => item.id === provider);

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
                <span className="mediaList__role">
                  {item.provider} · {item.role ?? "unplaced"}
                </span>
                <p className="mediaList__alt">{item.caption || item.alt_text}</p>
                {item.attribution ? (
                  <p className="mediaList__credit">
                    {item.attribution}
                    {item.license_name ? ` — ${item.license_name}` : ""}
                  </p>
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

      {brief.length > 0 && (
        <div className="mediaBrief">
          <span className="af__label">The guide asked for</span>
          <ul className="briefList">
            {brief.map((item, index) => (
              <li key={`${item.provider}-${item.query}-${index}`}>
                <button className="chip" onClick={() => void search(item.query, item.provider)}>
                  <span className="briefList__provider">{item.provider}</span>
                  {item.query}
                </button>
                {item.subject ? <span className="briefList__subject">{item.subject}</span> : null}
              </li>
            ))}
          </ul>
        </div>
      )}

      <form
        className="mediaSearch"
        onSubmit={(event) => {
          event.preventDefault();
          void search(query, provider);
        }}
      >
        <label className="u-sr" htmlFor="image-provider">Image source</label>
        <select
          id="image-provider"
          className="af__input"
          value={provider}
          onChange={(event) => setProvider(event.target.value)}
        >
          <option value="auto">Auto — pick from the category</option>
          {providers.map((item) => (
            <option key={item.id} value={item.id} disabled={!item.configured}>
              {item.title}
              {item.configured ? "" : " (no key)"}
            </option>
          ))}
        </select>
        <label className="u-sr" htmlFor="image-q">Image search</label>
        <input
          id="image-q"
          className="af__input"
          value={query}
          placeholder={chosen ? `Search ${chosen.title}` : "Search for an image"}
          onChange={(event) => setQuery(event.target.value)}
        />
        <button className="btn" type="submit" disabled={searching}>
          {searching ? "searching…" : "Search"}
        </button>
        {chosen ? <p className="af__hint mediaSearch__about">{chosen.subjects}</p> : null}
      </form>

      {error && (
        <p className="admin__error" role="alert">
          {error}
        </p>
      )}
      {warnings.length > 0 && (
        <ul className="run__warnings">
          {warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      )}

      {results.length > 0 && (
        <div className="stockGrid">
          {results.map((image) => (
            <figure className="stockGrid__item" key={image.remote_url}>
              <img src={image.preview_url ?? image.remote_url} alt={image.alt_text} loading="lazy" />
              <figcaption>
                <span className="stockGrid__provider">{image.provider}</span>
                {image.editorial_only ? (
                  <span className="stockGrid__editorial" title={image.license_name ?? ""}>
                    rights reserved
                  </span>
                ) : null}
                <span className="stockGrid__subject">{image.subject ?? image.alt_text}</span>
              </figcaption>
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
