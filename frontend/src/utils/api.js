/**
 * Central API utility with automatic Authorization token attachment and 401 handling.
 */

const API_BASE = import.meta.env.VITE_API_BASE || "";

// BUG 26: Module-level dedup — only the FIRST 401 triggers logout
let _unauthorizedFired = false;

export function resetUnauthorizedFlag() {
  _unauthorizedFired = false;
}

export async function apiFetch(path, options = {}) {
  const token = localStorage.getItem("ai_hiring_access_token");

  const headers = {
    ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
    ...(options.headers || {}),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (response.status === 401) {
    // BUG 26: Exclude login, interview, logout, and refresh from triggering global logout
    if (
      !path.includes("/api/auth/login") &&
      !path.includes("/api/interview/session") &&
      !path.includes("/api/auth/logout") &&
      !path.includes("/api/auth/refresh") &&
      !_unauthorizedFired
    ) {
      _unauthorizedFired = true;
      window.dispatchEvent(new CustomEvent("auth:unauthorized"));
    }
  }

  return response;
}

export async function apiFetchJson(path, options = {}) {
  const response = await apiFetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    let errorMsg = data.detail || data.message || `Request failed with status ${response.status}`;
    if (Array.isArray(errorMsg)) {
      errorMsg = errorMsg.map((e) => e.msg || e.message || JSON.stringify(e)).join("\n");
    }
    throw new Error(errorMsg);
  }
  return data;
}

export { API_BASE };
