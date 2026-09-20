import React, { createContext, useCallback, useEffect, useRef, useState } from "react";
import { apiFetch, apiFetchJson, resetUnauthorizedFlag } from "../../utils/api";

export const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(() => localStorage.getItem("ai_hiring_access_token") || null);
  const [refreshToken, setRefreshToken] = useState(() => localStorage.getItem("ai_hiring_refresh_token") || null);
  const [loading, setLoading] = useState(true);
  const [sessionError, setSessionError] = useState("");

  // BUG 26: In-flight guard so logout() is a singleton
  const logoutInProgress = useRef(false);

  const clearLocalAuth = useCallback(() => {
    localStorage.removeItem("ai_hiring_access_token");
    localStorage.removeItem("ai_hiring_refresh_token");
    setToken(null);
    setRefreshToken(null);
    setUser(null);
  }, []);

  const logout = useCallback(async () => {
    // BUG 26: If already logging out, just clear local state
    if (logoutInProgress.current) {
      clearLocalAuth();
      return;
    }
    logoutInProgress.current = true;
    try {
      if (token) {
        await apiFetch("/api/auth/logout", { method: "POST" });
      }
    } catch {
      // Ignore logout failure
    } finally {
      clearLocalAuth();
      logoutInProgress.current = false;
    }
  }, [token, clearLocalAuth]);

  const login = async (email, password) => {
    setSessionError("");
    // Reset the 401 dedup flag on fresh login
    resetUnauthorizedFlag();
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
          localStorage.setItem("ai_hiring_refresh_token", refreshed.refresh_token);
          setToken(refreshed.access_token);
          setRefreshToken(refreshed.refresh_token);
          setUser(refreshed.user);
          return;
        } catch {
          // Refresh failed — do silent local logout (token is already invalid)
        }
      }
      // BUG 26: Silent logout — just clear local state, no API call
      clearLocalAuth();
    } finally {
      setLoading(false);
    }
  }, [token, refreshToken, clearLocalAuth]);

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

  const hasPermission = useCallback(
    (perm) => {
      if (!user) return false;
      // Tenant owners always have full access, mirroring the backend rule.
      if (user.role === "super_admin" || user.role === "company_admin") return true;
      const perms = user.permissions || [];
      return perms.includes("*") || perms.includes(perm);
    },
    [user],
  );

  const value = {
    user,
    token,
    role: user?.role || null,
    permissions: user?.permissions || [],
    hasPermission,
    isAuthenticated: !!user,
    loading,
    sessionError,
    setSessionError,
    login,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
