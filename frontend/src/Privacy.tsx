import { Link } from "react-router-dom";
import { GA_ID } from "./analytics";
import { useDocumentTitle } from "./useDocumentTitle";

/**
 * What the site keeps, in the same plain terms the entries use.
 *
 * Everything here is a claim the code has to keep true. The counting is
 * described in `backend/app/api/routes/public.py`, the hash in the submission
 * pipeline, and both are keyed on the same HMAC so neither stores an address.
 */
export default function Privacy() {
  useDocumentTitle(
    "Privacy",
    "No accounts, no ad network, and no raw IP address stored anywhere. What the site keeps, and for how long.",
  );

  return (
    <div className="u-shell">
      <section className="notlisted">
        <h1 className="hero__q">Privacy.</h1>
        <p className="notlisted__p">
          There is no reader account, and an ad is a line of text written into the page
          here. What follows is the whole of it.
        </p>

        <h2 className="privacy__h">No address is stored</h2>
        <p className="notlisted__p">
          Counting readers needs a way to tell one from another, and an IP address is the
          obvious one — so the site does not keep it. Your address, browser string and
          language are run through a one-way hash and only the result is written down. It
          is enough to count against and to block abuse with, and useless for identifying
          anybody. Rotating the secret behind it erases every stored hash at once.
        </p>

        <h2 className="privacy__h">What is counted</h2>
        <ul className="privacy__list">
          <li>
            <strong>Reads.</strong> One per entry per reader per half hour. Without that
            window the number would be a refresh count, and the site does not print
            numbers it does not mean.
          </li>
          <li>
            <strong>Who is here now.</strong> One row per reader, swept every few
            minutes. Nothing survives five minutes past your last heartbeat.
          </li>
          <li>
            <strong>Searches that found nothing.</strong> The word you typed, so editors
            can see what is missing. The word, not who typed it.
          </li>
        </ul>

        <h2 className="privacy__h">If you submit an entry</h2>
        <p className="notlisted__p">
          The form keeps what you wrote and the name you asked to be credited under, so
          an editor can read it and put your name on the entry if it gets written up.
          Leave the name blank and nothing identifies you. The same one-way hash is used
          to stop one person flooding the queue.
        </p>

        <h2 className="privacy__h">What loads from elsewhere</h2>
        <p className="notlisted__p">
          Typefaces come from Google Fonts, and the pictures on an entry are served by
          whoever holds them — Wikimedia Commons, TVmaze, AniList and others named in the
          credit under each image. Those hosts see your address the way any site you
          visit does. The site cannot avoid that without hosting copies it has no right
          to host.
        </p>
        <p className="notlisted__p">
          The ad slot loads nothing. It is a line of text and a link, served from this
          origin like the rest of the page — no ad network, no script belonging to an
          advertiser, no pixel. Following the link takes you to whoever bought it, who
          then sees your address the way any site you visit does; the link is marked{" "}
          <code>noreferrer</code>, so it does not carry which entry you were reading.
        </p>

        <h2 className="privacy__h">Storage on your device</h2>
        <p className="notlisted__p">
          {GA_ID ? (
            <>
              Google Analytics is switched on for this deployment, and it sets its own
              cookies to tell one visit from another. That is the one thing on the site
              that does.
            </>
          ) : (
            <>Reading the site sets nothing: no cookie, no local storage.</>
          )}{" "}
          Editors signing in to the admin panel get one entry in local storage so a
          refresh does not sign them out, and signing out removes it.
        </p>

        <p className="notlisted__p">
          <Link to="/">← Back to the search</Link>
        </p>
      </section>
    </div>
  );
}
