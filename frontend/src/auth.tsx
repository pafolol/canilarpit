/**
 * Admin sign-in.
 *
 * Nothing here holds a credential. The session lives in an HttpOnly cookie the
 * browser attaches by itself and this code cannot read, so there is nothing for
 * an XSS on the reading interface to steal, and nothing to clear on sign-out
 * beyond asking the server to end the session - which it actually does, because
 * a session is a row rather than a signature.
 *
 * What the panel does read is the other half of the pair: a deliberately
 * readable CSRF cookie it echoes back as a header on every write. `api.ts`
 * handles that, so nothing in this file has to think about it.
 *
 * The local path is the development one: identity headers instead of a session,
 * offered only while the API reports DEV_AUTH_BYPASS, which it refuses to be in
 * production and ignores at request time regardless.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  ApiError,
  api,
  setAuthHeaderProvider,
  type Account,
  type AuthHeaders,
  type SiteConfig,
} from "./api";
import { Loading } from "./components";

/** Only ever the local development identity. A session is never written here. */
const DEV_STORAGE_KEY = "canilarpit.admin.dev-identity";

export type DevIdentity = { externalId: string; email: string; displayName: string };

export type { Account };

type AuthValue = {
  account: Account | null;
  config: SiteConfig | null;
  status: "loading" | "signed-out" | "signed-in";
  error: string | null;
  signIn: (email: string, password: string) => Promise<void>;
  devSignIn: (identity: DevIdentity) => void;
  signOut: () => void;
  refresh: () => void;
};

const AuthContext = createContext<AuthValue | null>(null);

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}

export const isEditor = (account: Account | null) =>
  account?.role === "editor" || account?.role === "admin";

export const isAdmin = (account: Account | null) => account?.role === "admin";

function readDevIdentity(): DevIdentity | null {
  try {
    const raw = localStorage.getItem(DEV_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as DevIdentity) : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<SiteConfig | null>(null);
  const [account, setAccount] = useState<Account | null>(null);
  const [status, setStatus] = useState<AuthValue["status"]>("loading");
  const [error, setError] = useState<string | null>(null);
  const [devIdentity, setDevIdentity] = useState<DevIdentity | null>(readDevIdentity);
  const [reloads, setReloads] = useState(0);

  // Registered before anything asks who we are, so a development identity is on
  // the very first call rather than the second.
  useEffect(() => {
    setAuthHeaderProvider((): AuthHeaders =>
      devIdentity
        ? {
            "X-Dev-User": devIdentity.externalId,
            "X-Dev-Email": devIdentity.email,
            "X-Dev-Display-Name": devIdentity.displayName,
          }
        : {},
    );
  }, [devIdentity]);

  useEffect(() => {
    let cancelled = false;
    api
      .config()
      .then((next) => !cancelled && setConfig(next))
      .catch(() => !cancelled && setConfig(null));
    return () => {
      cancelled = true;
    };
  }, []);

  // Who the cookie says we are. A 401 here is the ordinary signed-out case and
  // is not an error worth putting in front of anybody; an unreachable API is.
  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    api
      .me()
      .then((me) => {
        if (cancelled) return;
        setAccount(me as Account);
        setStatus("signed-in");
      })
      .catch((cause) => {
        if (cancelled) return;
        setAccount(null);
        setStatus("signed-out");
        setError(cause instanceof ApiError && cause.status === 0 ? cause.message : null);
      });
    return () => {
      cancelled = true;
    };
  }, [devIdentity, reloads]);

  const refresh = useCallback(() => setReloads((count) => count + 1), []);

  const signIn = useCallback(async (email: string, password: string) => {
    setError(null);
    const me = await api.auth.login(email, password);
    setAccount(me);
    setStatus("signed-in");
  }, []);

  const devSignIn = useCallback((identity: DevIdentity) => {
    try {
      localStorage.setItem(DEV_STORAGE_KEY, JSON.stringify(identity));
    } catch {
      // A blocked storage API is survivable: the session ends on refresh.
    }
    setDevIdentity(identity);
  }, []);

  const signOut = useCallback(() => {
    // Ask the server first. The cookie is HttpOnly, so this is the only thing
    // that ends the session rather than merely forgetting about it here.
    void api.auth.logout().catch(() => undefined);
    try {
      localStorage.removeItem(DEV_STORAGE_KEY);
    } catch {
      // ignore
    }
    setDevIdentity(null);
    setAccount(null);
    setStatus("signed-out");
    setError(null);
  }, []);

  const value = useMemo<AuthValue>(
    () => ({ account, config, status, error, signIn, devSignIn, signOut, refresh }),
    [account, config, status, error, signIn, devSignIn, signOut, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function AuthGate({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  if (status === "loading") {
    return (
      <div className="admin u-shell">
        <Loading what="your account" />
      </div>
    );
  }
  return <>{children}</>;
}
