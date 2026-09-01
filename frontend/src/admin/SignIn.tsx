import { useState } from "react";
import { ApiError } from "../api";
import { useAuth } from "../auth";

/**
 * The way in. Email and password, and nothing else.
 *
 * There is no "create account" link because there is no registration endpoint:
 * accounts are made by an administrator, from the Editors tab or the CLI. An
 * admin panel that lets a stranger make an account is an admin panel with a
 * stranger in it.
 */
export default function SignIn() {
  const { config, signIn, devSignIn, error: authError } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const devAvailable = config?.dev_auth_bypass ?? false;
  const noAccountsYet = config ? !config.sign_in_ready : false;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signIn(email.trim(), password);
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : "Sign-in failed. Try again.",
      );
      setPassword("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="admin__signin">
      <h1 className="admin__h1">Editor sign-in</h1>
      <p className="admin__lede">The catalog is public. Writing to it is not.</p>

      {noAccountsYet ? (
        <p className="admin__note">
          No account has a password yet. Make the first one from the repository:{" "}
          <code>canilarpit create-user you@example.com --role admin</code>
        </p>
      ) : null}

      <form className="admin__form" onSubmit={submit}>
        <label className="af">
          <span className="af__label">Email</span>
          <input
            className="af__input"
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>
        <label className="af">
          <span className="af__label">Password</span>
          <input
            className="af__input"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        <button className="btn" type="submit" disabled={busy || !email.trim() || !password}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>

      {error ? (
        <p className="admin__error" role="alert">
          {error}
        </p>
      ) : null}
      {!error && authError ? <p className="admin__error">{authError}</p> : null}

      {devAvailable ? (
        <>
          <hr className="admin__rule" />
          <p className="admin__note">
            <strong>Local development.</strong> The API has DEV_AUTH_BYPASS on, so it
            accepts an identity header instead of a password. A production deployment
            refuses to start with this enabled, and ignores the header even if it arrives.
          </p>
          <button
            className="chip"
            onClick={() =>
              devSignIn({
                externalId: "local-admin",
                email: "editor@example.com",
                displayName: "Local editor",
              })
            }
          >
            Sign in as local-admin
          </button>
        </>
      ) : null}
    </div>
  );
}
