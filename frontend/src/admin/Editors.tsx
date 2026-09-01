import { useCallback, useEffect, useState } from "react";
import { ApiError, api, type Account } from "../api";
import { useAuth } from "../auth";
import { Loading } from "../components";

/**
 * Accounts, and the only place they are made.
 *
 * An administrator can create an account, change a role, disable one, and set a
 * password for somebody locked out - but cannot read a password, because none
 * is stored. Changing your *own* password is deliberately not here: that asks
 * for the current one, which is what stops a borrowed unlocked laptop from
 * becoming a permanent takeover.
 */
export default function Editors() {
  const { account } = useAuth();
  const [rows, setRows] = useState<Account[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [role, setRole] = useState<"member" | "editor" | "admin">("editor");
  const [password, setPassword] = useState("");

  const load = useCallback(() => {
    api
      .editors.list()
      .then(setRows)
      .catch((cause) => setError(cause instanceof ApiError ? cause.message : "Could not load"));
  }, []);

  useEffect(load, [load]);

  async function act<T>(work: () => Promise<T>) {
    setBusy(true);
    setError(null);
    try {
      await work();
      load();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "That did not work.");
    } finally {
      setBusy(false);
    }
  }

  if (rows === null) return <Loading what="the editors" />;

  return (
    <section className="admin__panel">
      <h1 className="admin__h1">Editors</h1>
      <p className="admin__lede">
        There is no sign-up page. Every account is made here, or with{" "}
        <code>canilarpit create-user</code>.
      </p>

      {error ? (
        <p className="admin__error" role="alert">
          {error}
        </p>
      ) : null}

      <table className="admin__table">
        <thead>
          <tr>
            <th>Email</th>
            <th>Role</th>
            <th>Sign-in</th>
            <th>State</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const self = row.id === account?.id;
            return (
              <tr key={row.id}>
                <td>
                  {row.email ?? <em>no address</em>}
                  {self ? " (you)" : ""}
                </td>
                <td>
                  <select
                    className="af__input"
                    value={row.role}
                    // Demoting yourself is how a deployment ends up with no
                    // administrator; the API refuses it too.
                    disabled={busy || self}
                    onChange={(event) =>
                      void act(() => api.editors.update(row.id, { role: event.target.value }))
                    }
                  >
                    <option value="member">member</option>
                    <option value="editor">editor</option>
                    <option value="admin">admin</option>
                  </select>
                </td>
                <td>{row.email ? "password" : "no login"}</td>
                <td>{row.is_active ? "active" : "disabled"}</td>
                <td>
                  <button
                    className="chip"
                    disabled={busy || self}
                    onClick={() =>
                      void act(() =>
                        api.editors.update(row.id, { is_active: !row.is_active }),
                      )
                    }
                  >
                    {row.is_active ? "Disable" : "Enable"}
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <h2 className="admin__h2">Add an editor</h2>
      <form
        className="admin__form"
        onSubmit={(event) => {
          event.preventDefault();
          void act(async () => {
            await api.editors.create({
              email: email.trim(),
              password,
              display_name: displayName.trim() || null,
              role,
            });
            setEmail("");
            setDisplayName("");
            setPassword("");
          });
        }}
      >
        <label className="af">
          <span className="af__label">Email</span>
          <input
            className="af__input"
            type="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>
        <label className="af">
          <span className="af__label">Display name</span>
          <input
            className="af__input"
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
          />
        </label>
        <label className="af">
          <span className="af__label">Role</span>
          <select
            className="af__input"
            value={role}
            onChange={(event) => setRole(event.target.value as typeof role)}
          >
            <option value="editor">editor</option>
            <option value="admin">admin</option>
            <option value="member">member</option>
          </select>
        </label>
        <label className="af">
          <span className="af__label">First password</span>
          <input
            className="af__input"
            type="password"
            autoComplete="new-password"
            minLength={12}
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <span className="af__hint">
            At least 12 characters. They can change it once they are in; nobody,
            including you, can read it back.
          </span>
        </label>
        <button className="btn" type="submit" disabled={busy}>
          Create account
        </button>
      </form>
    </section>
  );
}
