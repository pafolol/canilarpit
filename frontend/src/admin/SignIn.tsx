import { useState } from "react";
import { useAuth } from "../auth";

export default function SignIn() {
  const { config, signIn, error, status } = useAuth();
  const devAvailable = config?.dev_auth_bypass ?? false;
  const [mode, setMode] = useState<"dev" | "token">(devAvailable ? "dev" : "token");
  const [clerkUserId, setClerkUserId] = useState("local-admin");
  const [email, setEmail] = useState("editor@example.com");
  const [token, setToken] = useState("");

  return (
    <div className="admin__signin">
      <h1 className="admin__h1">Editor sign-in</h1>
      <p className="admin__lede">
        The catalog is public. Writing to it is not.
      </p>

      <div className="admin__tabs" role="tablist">
        <button
          role="tab"
          aria-selected={mode === "dev"}
          className="chip"
          disabled={!devAvailable}
          onClick={() => setMode("dev")}
        >
          Local development
        </button>
        <button
          role="tab"
          aria-selected={mode === "token"}
          className="chip"
          onClick={() => setMode("token")}
        >
          Clerk session token
        </button>
      </div>

      {mode === "dev" ? (
        <form
          className="admin__form"
          onSubmit={(event) => {
            event.preventDefault();
            void signIn({
              mode: "dev",
              clerkUserId: clerkUserId.trim(),
              email: email.trim(),
              displayName: "Local editor",
            });
          }}
        >
          <p className="admin__note">
            {devAvailable
              ? "The API has DEV_AUTH_BYPASS on, so it accepts an identity header instead of a token. This is refused in production."
              : "The API has DEV_AUTH_BYPASS off. Use a Clerk token instead."}
          </p>
          <label className="af">
            <span className="af__label">Clerk user id</span>
            <input
              className="af__input"
              value={clerkUserId}
              onChange={(event) => setClerkUserId(event.target.value)}
            />
          </label>
          <label className="af">
            <span className="af__label">Email</span>
            <input
              className="af__input"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
          <button className="btn" type="submit" disabled={!devAvailable}>
            Sign in
          </button>
          <p className="admin__note">
            A new id signs in as <code>member</code>. Promote it once with{" "}
            <code>canilarpit set-role {clerkUserId || "&lt;id&gt;"} admin</code>.
          </p>
        </form>
      ) : (
        <form
          className="admin__form"
          onSubmit={(event) => {
            event.preventDefault();
            void signIn({ mode: "token", token: token.trim() });
          }}
        >
          <p className="admin__note">
            Paste a Clerk session JWT. A Clerk frontend SDK can call{" "}
            <code>signIn</code> with the same value once it is wired up.
          </p>
          <label className="af">
            <span className="af__label">Session token</span>
            <textarea
              className="af__input af__input--area"
              rows={4}
              value={token}
              onChange={(event) => setToken(event.target.value)}
            />
          </label>
          <button className="btn" type="submit" disabled={!token.trim()}>
            Sign in
          </button>
        </form>
      )}

      {status === "error" && error ? (
        <p className="admin__error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
