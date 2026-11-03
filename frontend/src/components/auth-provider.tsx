"use client";

import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, ApiError, refreshSession } from "@/lib/api";
import type { User } from "@/lib/types";

type AuthContextValue = {
  user: User | null;
  loading: boolean;
  isAdmin: boolean;
  logout: () => Promise<void>;
  reload: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const me = await api<User>("/auth/me");
      setUser(me);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        const ok = await refreshSession();
        if (ok) {
          setUser(await api<User>("/auth/me", { retry: false }));
          return;
        }
        router.replace("/login");
        return;
      }
      throw err;
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    // fora do corpo síncrono do efeito: a sessão é um sistema externo
    Promise.resolve()
      .then(() => load())
      .catch(() => undefined);
  }, [load]);

  const logout = useCallback(async () => {
    try {
      await api<void>("/auth/logout", { method: "POST", retry: false });
    } finally {
      setUser(null);
      router.replace("/login");
    }
  }, [router]);

  const value = useMemo<AuthContextValue>(
    () => ({ user, loading, isAdmin: user?.role === "admin", logout, reload: load }),
    [user, loading, logout, load],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth precisa estar dentro de AuthProvider");
  return ctx;
}
