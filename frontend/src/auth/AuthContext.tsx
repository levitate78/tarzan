import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from "react";
import { apiClient, clearToken, getStoredToken, setUnauthorizedHandler, storeToken } from "../api/client";
import type { TokenResponse, UserResponse } from "../api/types";

interface AuthContextValue {
  user: UserResponse | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const fetchCurrentUser = useCallback(async () => {
    const { data } = await apiClient.get<UserResponse>("/auth/me");
    setUser(data);
    return data;
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setUser(null);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setUser(null);
    });
    return () => setUnauthorizedHandler(null);
  }, []);

  useEffect(() => {
    const token = getStoredToken();
    if (!token) {
      setIsLoading(false);
      return;
    }
    fetchCurrentUser()
      .catch(() => {
        clearToken();
        setUser(null);
      })
      .finally(() => setIsLoading(false));
  }, [fetchCurrentUser]);

  const login = useCallback(
    async (username: string, password: string) => {
      const form = new URLSearchParams();
      form.set("username", username);
      form.set("password", password);

      const { data } = await apiClient.post<TokenResponse>("/auth/login", form, {
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
      });
      storeToken(data.access_token);
      await fetchCurrentUser();
    },
    [fetchCurrentUser]
  );

  const value: AuthContextValue = {
    user,
    isLoading,
    isAuthenticated: !!user,
    login,
    logout,
    refreshUser: async () => {
      await fetchCurrentUser();
    },
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}

// Role weights mirroring backend/app/core/rbac.py
const ROLE_WEIGHT: Record<string, number> = {
  admin: 40,
  lead: 30,
  member: 20,
  viewer: 10,
};

export function hasRole(userRole: string | undefined, required: string): boolean {
  if (!userRole) return false;
  return (ROLE_WEIGHT[userRole] ?? 0) >= (ROLE_WEIGHT[required] ?? 0);
}
