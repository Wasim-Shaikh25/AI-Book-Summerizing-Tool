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
  apiFetch,
  clearToken,
  fetchAuthConfig,
  getSkipAuthPreference,
  getToken,
  setSkipAuthPreference,
  setToken,
  type UserProfile,
} from "./api";

interface AuthContextValue {
  user: UserProfile | null;
  loading: boolean;
  authEnabled: boolean;
  backendOk: boolean;
  skipAuth: boolean;
  setSkipAuth: (skip: boolean) => void;
  loginWithToken: (token: string) => Promise<void>;
  enterWithoutAuth: () => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [authEnabled, setAuthEnabled] = useState(true);
  const [backendOk, setBackendOk] = useState(false);
  const [skipAuth, setSkipAuthState] = useState(getSkipAuthPreference);

  const setSkipAuth = useCallback((skip: boolean) => {
    setSkipAuthPreference(skip);
    setSkipAuthState(skip);
  }, []);

  const enterWithoutAuth = useCallback(async () => {
    const profile = await apiFetch<UserProfile>("/api/auth/guest", { method: "POST" });
    clearToken();
    setUser(profile);
    setSkipAuth(true);
  }, [setSkipAuth]);

  const refreshUser = useCallback(async () => {
    const cfg = await fetchAuthConfig();
    setAuthEnabled(cfg.auth_enabled);
    setBackendOk(cfg.backend_ok);

    if (!cfg.backend_ok) {
      setUser(null);
      setLoading(false);
      return;
    }

    if (!cfg.auth_enabled || getSkipAuthPreference()) {
      try {
        const profile = await apiFetch<UserProfile>("/api/auth/me");
        setUser(profile);
      } catch {
        await enterWithoutAuth();
      } finally {
        setLoading(false);
      }
      return;
    }

    const token = getToken();
    if (!token) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const profile = await apiFetch<UserProfile>("/api/auth/me");
      setUser(profile);
    } catch {
      clearToken();
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, [enterWithoutAuth]);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  const loginWithToken = useCallback(
    async (token: string) => {
      setToken(token);
      setSkipAuth(false);
      setLoading(true);
      await refreshUser();
    },
    [refreshUser, setSkipAuth]
  );

  const logout = useCallback(() => {
    clearToken();
    setUser(null);
    if (!authEnabled) {
      void enterWithoutAuth();
    }
  }, [authEnabled, enterWithoutAuth]);

  const value = useMemo(
    () => ({
      user,
      loading,
      authEnabled,
      backendOk,
      skipAuth,
      setSkipAuth,
      loginWithToken,
      enterWithoutAuth,
      logout,
      refreshUser,
    }),
    [
      user,
      loading,
      authEnabled,
      backendOk,
      skipAuth,
      setSkipAuth,
      loginWithToken,
      enterWithoutAuth,
      logout,
      refreshUser,
    ]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
