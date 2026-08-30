/**
 * Admin sign-in.
 *
 * Two paths, both ending in headers the backend already understands:
 *
 *  - a Clerk session token, pasted or handed over by a Clerk frontend SDK, sent
 *    as `Authorization: Bearer ...`;
 *  - the local development identity headers the backend accepts only while
 *    DEV_AUTH_BYPASS is on, which it refuses to be in production.
 *
 * The credential lives in localStorage so a refresh does not sign you out. It
 * never leaves this origin except as a request header to the API.
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
import { api, setAuthHeaderProvider, type SiteConfig } from "./api";

const STORAGE_KEY = "canilarpit.admin.credential";

export type Credential =
  | { mode: "token"; token: string }
  | { mode: "dev"; clerkUserId: string; email: string; displayName: string };

export type Account = {
  id: string;
  role: string;
  email: string | null;
  display_name: string | null;
};

type AuthValue = {
  credential: Credential | null;
  account: Account | null;
  config: SiteConfig | null;
  status: "loading" | "signed-out" | "signed-in" | "error";
  error: string | null;
  signIn: (credential: Credential) => Promise<void>;
  signOut: () => void;
};

const AuthContext = createContext<AuthValue | null>(null);

function headersFor(credential: Credential | null): Record<string, string> {
  if (!credential) return {};
  if (credential.mode === "token") return { Authorization: `Bearer ${credential.token}` };
  return {
    "X-Dev-Clerk-User-Id": credential.clerkUserId,
    "X-Dev-Email": credential.email,
    "X-Dev-Display-Name": credential.displayName,
  };
}

function readStored(): Credential | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Credential) : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [credential, setCredential] = useState<Credential | null>(readStored);
  const [account, setAccount] = useState<Account | null>(null);
  const [config, setConfig] = useState<SiteConfig | null>(null);
  const [status, setStatus] = useState<AuthValue["status"]>("loading");
  const [error, setError] = useState<string | null>(null);

  // The provider is a function so a fresh credential is picked up without
  // rebuilding the api module.
  useEffect(() => {
    setAuthHeaderProvider(() => headersFor(credential));
  }, [credential]);

  useEffect(() => {
    api.config().then(setConfig).catch(() => setConfig(null));
  }, []);

  useEffect(() => {
    if (!credential) {
      setAccount(null);
      setStatus("signed-out");
      return;
    }
    let cancelled = false;
    setStatus("loading");
    api
      .me()
      .then((me) => {
        if (cancelled) return;
        setAccount(me as Account);
        setError(null);
        setStatus("signed-in");
      })
      .catch((cause) => {
        if (cancelled) return;
        setAccount(null);
        setError(cause instanceof Error ? cause.message : "Sign-in failed");
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [credential]);

  const signIn = useCallback(async (next: Credential) => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      // A blocked storage API is survivable: the session just ends on refresh.
    }
    setCredential(next);
  }, []);

  const signOut = useCallback(() => {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // ignore
    }
    setCredential(null);
    setAccount(null);
    setError(null);
  }, []);

  const value = useMemo<AuthValue>(
    () => ({ credential, account, config, status, error, signIn, signOut }),
    [credential, account, config, status, error, signIn, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}

export const isEditor = (account: Account | null) =>
  account?.role === "editor" || account?.role === "admin";

export const isAdmin = (account: Account | null) => account?.role === "admin";
