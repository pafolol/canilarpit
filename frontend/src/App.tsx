import { Suspense, lazy, useEffect, useState } from "react";
import { Link, NavLink, Route, Routes, useLocation, useParams } from "react-router-dom";
import Advertise from "./Advertise";
import Entry from "./Entry";
import Faq from "./Faq";
import { Loading } from "./components";
import Home from "./Home";
import JustLearnIt from "./JustLearnIt";
import NotListed from "./NotListed";
import Presence from "./Presence";
import Privacy from "./Privacy";
import Submit from "./Submit";
import Thanks from "./Thanks";
import { startAnalytics } from "./analytics";

// Split off the public bundle on purpose. A reader who never opens /admin
// should never download the panel — one less thing shipped to everybody, and
// one less thing running on the pages a stranger actually visits.
const AdminApp = lazy(() => import("./admin/AdminApp"));

function CategoryRoute() {
  const { slug = "" } = useParams();
  return <Home category={slug} />;
}

function useOffline() {
  const [offline, setOffline] = useState(!navigator.onLine);
  useEffect(() => {
    const on = () => setOffline(!navigator.onLine);
    addEventListener("online", on);
    addEventListener("offline", on);
    return () => {
      removeEventListener("online", on);
      removeEventListener("offline", on);
    };
  }, []);
  return offline;
}

/**
 * The one conversion action the site has, kept in reach on a phone.
 *
 * Hidden where it would be noise: the submit flow itself, and the admin panel.
 * Desktop already has it in the footer and in every empty state, so this is
 * mobile-only in CSS rather than another thing to scroll past.
 */
function StickyCta({ pathname }: { pathname: string }) {
  const hidden = ["/submit", "/thanks", "/admin"].some(
    (p) => pathname === p || pathname.startsWith(`${p}/`),
  );
  if (hidden) return null;
  return (
    <div className="ctabar">
      <span className="ctabar__text">Missing one you know?</span>
      <Link className="ctabar__btn" to="/submit">
        Submit an entry
      </Link>
    </div>
  );
}

export default function App() {
  const offline = useOffline();
  const { pathname } = useLocation();
  useEffect(() => {
    // Braces matter: a concise body would return whatever scrollTo returns, and
    // React treats a non-undefined return value as the cleanup function.
    window.scrollTo(0, 0);
  }, [pathname]);

  // Loads nothing at all unless VITE_GA_ID is set. Once, not per navigation.
  useEffect(() => {
    startAnalytics();
  }, []);

  return (
    <div className="shell">
      {/* The one thing on the page that is about right now rather than about the entry. */}
      <Presence />

      {/* Offline turns the header hairline to --rule. No modal. */}
      <header className={`hdr${offline ? " is-offline" : ""}`}>
        <div className="hdr__in u-shell">
          <Link className="hdr__mark" to="/">canilarpit</Link>
          <nav className="hdr__nav" aria-label="Primary">
            <NavLink className="hdr__link hdr__link--type" to="/?type=scene">Scenes</NavLink>
            <NavLink className="hdr__link hdr__link--type" to="/?type=taste">Taste</NavLink>
            <NavLink className="hdr__link hdr__link--type" to="/?type=role">Roles</NavLink>
            <NavLink className="hdr__link hdr__learn" to="/just-learn-it">Just learn it</NavLink>
          </nav>
        </div>
      </header>

      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/entry/:slug" element={<Entry />} />
          <Route path="/category/:slug" element={<CategoryRoute />} />
          <Route path="/submit" element={<Submit />} />
          <Route path="/thanks" element={<Thanks />} />
          <Route path="/faq" element={<Faq />} />
          <Route path="/privacy" element={<Privacy />} />
          <Route path="/advertise" element={<Advertise />} />
          <Route
            path="/admin/*"
            element={
              <Suspense fallback={<div className="admin u-shell"><Loading what="the panel" /></div>}>
                <AdminApp />
              </Suspense>
            }
          />
          <Route path="/just-learn-it" element={<JustLearnIt />} />
          <Route path="*" element={<NotListed slug={pathname} />} />
        </Routes>
      </main>

      <StickyCta pathname={pathname} />

      <footer className="ftr">
        <div className="ftr__in u-shell">
          <Link to="/just-learn-it">Just learn it</Link>
          <span className="ftr__sep" aria-hidden="true">·</span>
          <Link to="/submit">Submit</Link>
          <span className="ftr__sep" aria-hidden="true">·</span>
          <Link to="/faq">Questions</Link>
          <span className="ftr__sep" aria-hidden="true">·</span>
          <Link to="/privacy">Privacy</Link>
          <span className="ftr__sep" aria-hidden="true">·</span>
          <Link to="/advertise">Advertise</Link>
          <span className="ftr__sep" aria-hidden="true">·</span>
          <Link to="/admin">Editors</Link>
          <span className="ftr__note">{offline ? "Offline. The page still works." : "Read it before you need it."}</span>
        </div>
      </footer>
    </div>
  );
}
