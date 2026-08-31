import { useEffect, useState } from "react";
import { api } from "./api";

const BEAT_MS = 45_000;

/**
 * How many people are on the site, right now, as a number and not a mood.
 *
 * It shows 1 when it is 1. A site that inflates this is a site that will inflate
 * the view counts next, and the whole premise here is telling readers the truth
 * about what holds and what does not.
 *
 * The beat pauses while the tab is hidden — the same `document.hidden` guard the
 * exposure clock uses — so a tab left open all afternoon is not a person on the
 * site all afternoon. Coming back sends one immediately rather than waiting out
 * the interval.
 */
export default function Presence() {
  const [current, setCurrent] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;

    const beat = () => {
      if (document.hidden) return;
      api
        .presence()
        .then((result) => !cancelled && setCurrent(result.current))
        // A failed heartbeat is not worth a message. The strip stays as it was.
        .catch(() => undefined);
    };

    beat();
    const id = setInterval(beat, BEAT_MS);
    document.addEventListener("visibilitychange", beat);
    return () => {
      cancelled = true;
      clearInterval(id);
      document.removeEventListener("visibilitychange", beat);
    };
  }, []);

  if (current === null) return null;

  return (
    <div className="presence" aria-live="polite">
      <span className="presence__dot" aria-hidden="true" />
      <span className="presence__n">{current}</span>
      <span className="presence__label">
        {current === 1 ? "larper on the site" : "larpers on the site"}
      </span>
    </div>
  );
}
