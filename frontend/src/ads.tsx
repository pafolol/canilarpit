import { Link } from "react-router-dom";

/**
 * The ad rail, and the list you edit to fill it.
 *
 * No ad network, no third-party script, no pixel: a booked ad is a line of
 * text and a link, served from our own origin like everything else on the
 * page. That is not squeamishness, it is the only version that keeps the
 * promise on `/privacy` — an ad network is precisely a thing that follows the
 * reader off the site, and the page says nothing here does.
 *
 * An empty list is the normal state, and the rail then sells itself.
 */
export type Ad = {
  /** Who is paying. Printed, because an unlabelled ad is a lie of omission. */
  name: string;
  /** One line. A slot is a mention, not a landing page. */
  line: string;
  href: string;
};

export const ADS: Ad[] = [];

/**
 * How many the rail will show. A ceiling, not a promise: unsold slots are not
 * drawn at all, because eight copies of "advertise here" is an empty car park
 * with eight signs in it. One is the invitation; the rest are inventory.
 */
export const SLOT_COUNT = 8;

/** Where an advertiser writes. Change this to the address you actually read. */
export const ADS_EMAIL = "ads@canilarpit.com";

export const ADS_MAILTO = `mailto:${ADS_EMAIL}?subject=${encodeURIComponent(
  "Advertising on canilarpit",
)}`;

/**
 * Labelled, always. `rel="sponsored"` is the same statement made to a crawler:
 * a paid link that is not declared is what gets a site's outbound links
 * discounted wholesale, and the label is what a reader is owed anyway.
 */
export function AdSlot({ ad }: { ad?: Ad }) {
  return (
    <aside className="ad" aria-label={ad ? "Advertisement" : "Advertise here"}>
      <p className="u-label ad__label">{ad ? "Ad" : "This space"}</p>
      {ad ? (
        <a
          className="ad__body"
          href={ad.href}
          target="_blank"
          rel="sponsored nofollow noopener noreferrer"
        >
          <span className="ad__line">{ad.line}</span>
          <span className="ad__who">{ad.name}</span>
        </a>
      ) : (
        <Link className="ad__body" to="/advertise">
          <span className="ad__line">
            A line and a link, no network, and nothing that follows anybody home.
          </span>
          <span className="ad__who">Advertise here →</span>
        </Link>
      )}
    </aside>
  );
}

/**
 * The column of slots that runs beside the content.
 *
 * Below the desktop breakpoint there is no side to put it on, so the CSS lays
 * it back into the page and shows the first slot only — eight of anything
 * stacked on a phone is a different site.
 */
export function AdRail() {
  const booked = ADS.slice(0, SLOT_COUNT);
  return (
    <div className="adrail">
      {booked.map((ad) => (
        <AdSlot key={ad.href} ad={ad} />
      ))}
      {booked.length < SLOT_COUNT && <AdSlot />}
    </div>
  );
}
