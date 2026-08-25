import React, { createContext, useCallback, useEffect, useState } from "react";
import { apiFetch, apiFetchJson } from "../../utils/api";

export const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(() => localStorage.getItem("ai_hiring_access_token") || null);
  const [refreshToken, setRefreshToken] = useState(() => localStorage.getItem("ai_hiring_refresh_token") || null);
  const [loading, setLoading] = useState(true);
  const [sessionError, setSessionError] = useState("");

  const logout = useCallback(async () => {
    try {
      if (token) {
        await apiFetch("/api/auth/logout", { method: "POST" });
      }
    } catch {
      // Ignore logout failure
    } finally {
      localStorage.removeItem("ai_hiring_access_token");
      localStorage.removeItem("ai_hiring_refresh_token");
      setToken(null);
      setRefreshToken(null);
      setUser(null);
    }
  }, [token]);

  const login = async (email, password) => {
    setSessionError("");
    const data = await apiFetchJson("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });

    localStorage.setItem("ai_hiring_access_token", data.access_token);
    localStorage.setItem("ai_hiring_refresh_token", data.refresh_token);
    setToken(data.access_token);
    setRefreshToken(data.refresh_token);
    setUser(data.user);
    return data.user;
  };

  const fetchCurrentUser = useCallback(async () => {
    if (!token) {
      setLoading(false);
      return;
    }
    try {
      const profile = await apiFetchJson("/api/auth/me");
      setUser(profile);
    } catch (err) {
      console.warn("Failed to validate current user:", err);
      // Try refresh
      if (refreshToken) {
        try {
          const refreshed = await apiFetchJson("/api/auth/refresh", {
            method: "POST",
            body: JSON.stringify({ refresh_token: refreshToken }),
          });
          localStorage.setItem("ai_hiring_access_token", refreshed.access_token);
          setToken(refreshed.access_token);
          setUser(refreshed.user);
          return;
        } catch {
          // Refresh failed
        }
      }
      logout();
    } finally {
      setLoading(false);
    }
  }, [token, refreshToken, logout]);

  useEffect(() => {
    fetchCurrentUser();
  }, [fetchCurrentUser]);

  // Listen for unauthorized 401 events globally
  useEffect(() => {
    function handleUnauthorized() {
      setSessionError("Your session expired or was signed in from another location. Please log in again.");
      logout();
    }
    window.addEventListener("auth:unauthorized", handleUnauthorized);
    return () => window.removeEventListener("auth:unauthorized", handleUnauthorized);
  }, [logout]);

  const value = {
    user,
    token,
    role: user?.role || null,
    isAuthenticated: !!user,
    loading,
    sessionError,
    setSessionError,
    login,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
