import React, { createContext, useCallback, useEffect, useRef, useState } from "react";
import { apiFetch, apiFetchJson, resetPermissionChangeFlag, resetUnauthorizedFlag } from "../../utils/api";

export const AuthContext = createContext(null);

// The backend may return permissions in any order, so a pure reordering must
// not be mistaken for a permission change.
function samePermissions(a, b) {
  const left = [...(a || [])].sort();
  const right = [...(b || [])].sort();
  return left.length === right.length && left.every((p, i) => p === right[i]);
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(() => localStorage.getItem("ai_hiring_access_token") || null);
  const [refreshToken, setRefreshToken] = useState(() => localStorage.getItem("ai_hiring_refresh_token") || null);
  const [loading, setLoading] = useState(true);
  const [sessionError, setSessionError] = useState("");
  const [accessChanged, setAccessChanged] = useState(false);

  // BUG 26: In-flight guard so logout() is a singleton
  const logoutInProgress = useRef(false);

  // BUG 9: Deduplicate in-flight refreshes by returning the active promise.
  const refreshPromiseRef = useRef(null);
  // Staleness tracker: skip refresh if last successful profile load was < 60s ago
  const PROFILE_STALE_MS = 60 * 1000;
  const lastRefreshAt = useRef(0);

  // Mirrors of the latest committed values, so refreshProfile can stay a stable
  // callback (safe to use in event listeners) while still diffing and
  // authenticating against current state.
  const userRef = useRef(null);
  const tokenRef = useRef(null);
  useEffect(() => {
    userRef.current = user;
    tokenRef.current = token;
  }, [user, token]);

  const clearLocalAuth = useCallback(() => {
    localStorage.removeItem("ai_hiring_access_token");
    localStorage.removeItem("ai_hiring_refresh_token");
    setToken(null);
    setRefreshToken(null);
    setUser(null);
    setAccessChanged(false);
    lastRefreshAt.current = 0;
    refreshPromiseRef.current = null;
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
    resetPermissionChangeFlag();
    const data = await apiFetchJson("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });

    localStorage.setItem("ai_hiring_access_token", data.access_token);
    localStorage.setItem("ai_hiring_refresh_token", data.refresh_token);
    setToken(data.access_token);
    setRefreshToken(data.refresh_token);
    setUser(data.user);
    setAccessChanged(false);
    lastRefreshAt.current = Date.now();
    return data.user;
  };

  /**
   * Re-read the current profile without touching `loading` and without ever
   * logging the user out.
   *
   * Deduplicates in-flight requests and throttles unless `force` is set.
   */
  const refreshProfile = useCallback(async (options = {}) => {
    const { force = false } = options || {};
    if (!tokenRef.current) return null;

    // Throttle by staleness unless force is requested
    const now = Date.now();
    if (!force && lastRefreshAt.current > 0 && now - lastRefreshAt.current < PROFILE_STALE_MS) {
      return userRef.current;
    }

    // Deduplicate: if a refresh is already in-flight, return the same promise
    if (refreshPromiseRef.current) {
      return refreshPromiseRef.current;
    }

    const promise = (async () => {
      try {
        const profile = await apiFetchJson("/api/auth/me");
        lastRefreshAt.current = Date.now();
        const prev = userRef.current;
        const changed =
          !!prev &&
          (prev.role !== profile.role ||
            !samePermissions(prev.permissions, profile.permissions));
        if (!prev || changed) {
          setUser(profile);
          if (changed) setAccessChanged(true);
        }
        return profile;
      } catch (err) {
        // Best-effort by design: a transient failure here (offline, 5xx) must
        // not destroy an otherwise valid session. Deciding to log out is the
        // initial-load path's job, not the revalidation path's.
        console.warn("Permission revalidation failed:", err);
        return null;
      } finally {
        refreshPromiseRef.current = null;
      }
    })();

    refreshPromiseRef.current = promise;
    return promise;
  }, []);

  const fetchCurrentUser = useCallback(async () => {
    if (!token) {
      setLoading(false);
      return;
    }
    try {
      const profile = await apiFetchJson("/api/auth/me");
      lastRefreshAt.current = Date.now();
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
          lastRefreshAt.current = Date.now();
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

  // Revalidate cheaply: only revalidate when profile is stale (> 60s), except for
  // explicit permission-change events which force an immediate refresh.
  useEffect(() => {
    function handleFocus() {
      if (Date.now() - lastRefreshAt.current >= PROFILE_STALE_MS) {
        refreshProfile();
      }
    }
    function handleVisibility() {
      if (document.visibilityState === "visible" && Date.now() - lastRefreshAt.current >= PROFILE_STALE_MS) {
        refreshProfile();
      }
    }
    function handlePermissionsChanged() {
      refreshProfile({ force: true });
    }
    window.addEventListener("focus", handleFocus);
    document.addEventListener("visibilitychange", handleVisibility);
    window.addEventListener("auth:permissions-changed", handlePermissionsChanged);
    return () => {
      window.removeEventListener("focus", handleFocus);
      document.removeEventListener("visibilitychange", handleVisibility);
      window.removeEventListener("auth:permissions-changed", handlePermissionsChanged);
    };
  }, [refreshProfile]);

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

  const clearAccessChanged = useCallback(() => setAccessChanged(false), []);

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
    refreshProfile,
    accessChanged,
    clearAccessChanged,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
