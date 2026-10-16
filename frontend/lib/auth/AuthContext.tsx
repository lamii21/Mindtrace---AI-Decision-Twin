"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import * as authApi from "@/lib/api/auth";
import { clearTokens, getAccessToken, setTokens } from "@/lib/api/client";
import type { MeResponse } from "@/lib/api/types";

interface AuthState {
  user: MeResponse | null;
  status: "loading" | "authenticated" | "unauthenticated";
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<MeResponse | null>(null);
  const [status, setStatus] = useState<AuthState["status"]>("loading");

  const refreshMe = useCallback(async () => {
    const token = getAccessToken();
    if (!token) {
      setStatus("unauthenticated");
      return;
    }
    try {
      const me = await authApi.me();
      setUser(me);
      setStatus("authenticated");
    } catch {
      clearTokens();
      setUser(null);
      setStatus("unauthenticated");
    }
  }, []);

  useEffect(() => {
    void refreshMe();
  }, [refreshMe]);

  const login = useCallback(
    async (email: string, password: string) => {
      const pair = await authApi.login(email, password);
      setTokens(pair.access_token, pair.refresh_token);
      await refreshMe();
    },
    [refreshMe],
  );

  const register = useCallback(
    async (email: string, password: string) => {
      await authApi.register(email, password);
      await login(email, password);
    },
    [login],
  );

  const logout = useCallback(() => {
    clearTokens();
    setUser(null);
    setStatus("unauthenticated");
  }, []);

  return (
    <AuthContext.Provider value={{ user, status, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
