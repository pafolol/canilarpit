import { useEffect } from "react";

const SITE = "canilarpit";

/**
 * Keeps the tab honest as the reader navigates.
 *
 * The real sharing tags are injected server-side, in `api/routes/site.py`,
 * because nothing that reads a link runs JavaScript. Those tags describe the
 * first page loaded and nothing after it, so on a client-side navigation the
 * title and description here are the only things that still tell the truth —
 * for the tab, for a bookmark, and for the browser's own history.
 */
export function useDocumentTitle(title: string | null, description?: string | null) {
  useEffect(() => {
    if (!title) return;
    const previous = document.title;
    document.title = title === SITE ? SITE : `${title} — ${SITE}`;
    return () => {
      document.title = previous;
    };
  }, [title]);

  useEffect(() => {
    if (!description) return;
    const tag = document.querySelector<HTMLMetaElement>('meta[name="description"]');
    if (!tag) return;
    const previous = tag.content;
    tag.content = description;
    return () => {
      tag.content = previous;
    };
  }, [description]);
}
