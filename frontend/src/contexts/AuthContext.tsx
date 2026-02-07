"use client";

import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react";
import type { User } from "@/types";
import { authLogin, authSignup, authLogout, authMe, setAccessToken, setOnAuthError } from "@/lib/api";

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const clearAuth = useCallback(() => {
    setUser(null);
    setAccessToken(null);
    localStorage.removeItem("refresh_token");
  }, []);

  // 앱 로드 시 Refresh Token으로 세션 복원
  useEffect(() => {
    setOnAuthError(clearAuth);

    const restore = async () => {
      const rt = localStorage.getItem("refresh_token");
      if (!rt) {
        setIsLoading(false);
        return;
      }

      try {
        // refresh를 통해 access token 획득 → me 호출
        const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
        const res = await fetch(`${API_URL}/api/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: rt }),
        });

        if (res.ok) {
          const data = await res.json();
          setAccessToken(data.access_token);
          localStorage.setItem("refresh_token", data.refresh_token);
          const me = await authMe();
          setUser(me);
        } else {
          clearAuth();
        }
      } catch {
        clearAuth();
      } finally {
        setIsLoading(false);
      }
    };

    restore();
  }, [clearAuth]);

  const login = async (email: string, password: string) => {
    const tokens = await authLogin(email, password);
    setAccessToken(tokens.access_token);
    localStorage.setItem("refresh_token", tokens.refresh_token);
    const me = await authMe();
    setUser(me);
  };

  const signup = async (email: string, username: string, password: string) => {
    await authSignup(email, username, password);
    // 회원가입 후 자동 로그인
    await login(email, password);
  };

  const logout = async () => {
    const rt = localStorage.getItem("refresh_token");
    if (rt) {
      await authLogout(rt);
    }
    clearAuth();
  };

  return (
    <AuthContext.Provider value={{ user, isLoading, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
