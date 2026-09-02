import { Link } from "react-router-dom";
import { ADS_EMAIL, ADS_MAILTO } from "./ads";
import { useDocumentTitle } from "./useDocumentTitle";

/**
 * The other half of the slot: where somebody who saw it writes to us.
 *
 * Deliberately a mail address rather than a form. A form here would need its
 * own endpoint, its own spam obstacles and its own queue for an editor to
 * read, which is a lot of machinery for a conversation that has to happen over
 * mail anyway — an invoice does not fit in a text field.
 */
export default function Advertise() {
  useDocumentTitle(
    "Advertise",
    "One ad slot, sold direct. A line of text and a link, no network and no tracking.",
  );

  return (
    <div className="u-shell">
      <section className="notlisted">
        <h1 className="hero__q">Advertise here.</h1>
        <p className="notlisted__p">
          There is one slot, it is sold direct, and it is a line of text with a link on
          it. If that sounds small, that is the offer.
        </p>

        <h2 className="privacy__h">What you get</h2>
        <ul className="privacy__list">
          <li>
            <strong>One line and your name</strong>, at the foot of the search results
            and at the foot of every entry. Nothing else on the page competes with it,
            because nothing else on the page is an ad.
          </li>
          <li>
            <strong>Served from here.</strong> No ad network, no script of yours running
            on our pages, no pixel. Your link is a link. It carries{" "}
            <code>rel="sponsored"</code>, which is the honest label and what search
            engines expect on a paid one.
          </li>
          <li>
            <strong>Labelled as an ad</strong>, in the same type as everything else. We
            are not going to dress it as an entry.
          </li>
        </ul>

        <h2 className="privacy__h">Who reads this</h2>
        <p className="notlisted__p">
          People about to walk into a conversation they are underqualified for: a
          screening, a tasting, a standup, a first day. They arrive by typing one word
          into the search, they read one entry closely, and they leave. Ask us for the
          current numbers and we will send the real ones — the site counts reads and it
          does not print numbers it does not mean.
        </p>

        <h2 className="privacy__h">What we will not run</h2>
        <p className="notlisted__p">
          Anything that would make the site worse to trust: a course promising you can
          fake a credential that hurts somebody, an exam or licence service, a get-rich
          scheme, or anything that needs a reader to be careless. The entries filed under{" "}
          <strong>DON'T</strong> exist because some claims endanger people, and an ad
          selling one of those would undo the whole point.
        </p>

        <h2 className="privacy__h">Get in touch</h2>
        <p className="notlisted__p">
          Write to <a href={ADS_MAILTO}>{ADS_EMAIL}</a> with what you sell and the line
          you would want to run. A person reads it and answers with rates and the next
          free slot — usually within a couple of days.
        </p>

        <p className="notlisted__p">
          <Link to="/">← Back to the search</Link>
          <span className="ftr__sep" aria-hidden="true">
            ·
          </span>
          <Link to="/privacy">What the site keeps</Link>
        </p>
      </section>
    </div>
  );
}
