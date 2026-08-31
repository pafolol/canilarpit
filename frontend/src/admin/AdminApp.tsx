import { NavLink, Route, Routes } from "react-router-dom";
import { isEditor, useAuth } from "../auth";
import { Loading } from "../components";
import Dashboard from "./Dashboard";
import Generate from "./Generate";
import GuideEditor from "./GuideEditor";
import Submissions from "./Submissions";
import SignIn from "./SignIn";

export default function AdminApp() {
  const { account, status, signOut, error } = useAuth();

  if (status === "loading") {
    return (
      <div className="admin u-shell">
        <Loading what="your account" />
      </div>
    );
  }

  if (status !== "signed-in") {
    return (
      <div className="admin u-shell">
        <SignIn />
      </div>
    );
  }

  if (!isEditor(account)) {
    return (
      <div className="admin u-shell">
        <h1 className="admin__h1">Not an editor</h1>
        <p className="admin__lede">
          You are signed in as <code>{account?.email ?? account?.id}</code> with the role{" "}
          <code>{account?.role}</code>. Guide editing needs <code>editor</code> or{" "}
          <code>admin</code>.
        </p>
        <p className="admin__note">
          Promote the account from the backend:{" "}
          <code>canilarpit set-role &lt;clerk-user-id&gt; admin</code>.
        </p>
        <button className="chip" onClick={signOut}>
          Sign out
        </button>
        {error ? <p className="admin__error">{error}</p> : null}
      </div>
    );
  }

  return (
    <div className="admin u-shell">
      <nav className="admin__nav" aria-label="Admin">
        <NavLink className="admin__link" to="/admin" end>
          Catalog
        </NavLink>
        <NavLink className="admin__link" to="/admin/submissions">
          Submissions
        </NavLink>
        <NavLink className="admin__link" to="/admin/generate">
          Generate
        </NavLink>
        <span className="admin__who">
          {account?.email ?? account?.display_name ?? "signed in"} · {account?.role}
        </span>
        <button className="chip" onClick={signOut}>
          Sign out
        </button>
      </nav>

      <Routes>
        <Route index element={<Dashboard />} />
        <Route path="submissions" element={<Submissions />} />
        <Route path="generate" element={<Generate />} />
        <Route path="guides/:id" element={<GuideEditor />} />
      </Routes>
    </div>
  );
}
