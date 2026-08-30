import { useEffect, useState } from "react";
import { Link, NavLink, Route, Routes, useLocation, useParams } from "react-router-dom";
import AdminApp from "./admin/AdminApp";
import Entry from "./Entry";
import Home from "./Home";
import NotListed from "./NotListed";

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

export default function App() {
  const offline = useOffline();
  const { pathname } = useLocation();
  useEffect(() => {
    // Braces matter: a concise body would return whatever scrollTo returns, and
    // React treats a non-undefined return value as the cleanup function.
    window.scrollTo(0, 0);
  }, [pathname]);

  return (
    <div className="shell">
      {/* Offline turns the header hairline to --rule. No modal. */}
      <header className={`hdr${offline ? " is-offline" : ""}`}>
        <div className="hdr__in u-shell">
          <Link className="hdr__mark" to="/">canilarpit</Link>
          <nav className="hdr__nav" aria-label="Primary">
            <NavLink className="hdr__link hdr__link--type" to="/?type=scene">Scenes</NavLink>
            <NavLink className="hdr__link hdr__link--type" to="/?type=taste">Taste</NavLink>
            <NavLink className="hdr__link hdr__link--type" to="/?type=role">Roles</NavLink>
            <NavLink className="hdr__link hdr__spot" to="/spot-the-larper">Spot →</NavLink>
          </nav>
        </div>
      </header>

      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/entry/:slug" element={<Entry />} />
          <Route path="/category/:slug" element={<CategoryRoute />} />
          <Route path="/admin/*" element={<AdminApp />} />
          <Route
            path="/spot-the-larper"
            element={<NotListed note="Every tell on the site, as one flat list. It comes after the entry pages." />}
          />
          <Route
            path="/just-learn-it"
            element={<NotListed note="Hours, the one book, the one thing to make. It comes after the entry pages." />}
          />
          <Route path="/stats" element={<NotListed note="Counts, medians, and what gets submitted most. It comes later." />} />
          <Route path="*" element={<NotListed slug={pathname} />} />
        </Routes>
      </main>

      <footer className="ftr">
        <div className="ftr__in u-shell">
          <Link to="/just-learn-it">Just learn it</Link>
          <span className="ftr__sep" aria-hidden="true">·</span>
          <Link to="/spot-the-larper">Spot the larper</Link>
          <span className="ftr__sep" aria-hidden="true">·</span>
          <Link to="/">Submit</Link>
          <span className="ftr__sep" aria-hidden="true">·</span>
          <Link to="/stats">Stats</Link>
          <span className="ftr__sep" aria-hidden="true">·</span>
          <Link to="/admin">Editors</Link>
          <span className="ftr__note">{offline ? "Offline. The page still works." : "Read it before you need it."}</span>
        </div>
      </footer>
    </div>
  );
}
