/**
 * Central API utility with automatic Authorization token attachment and 401 handling.
 */

const API_BASE = import.meta.env.VITE_API_BASE || "";

let _unauthorizedFired = false;

export function resetUnauthorizedFlag() {
  _unauthorizedFired = false;
}

// A permission denial is the one signal that the caller's cached profile is
// stale — a company admin just revoked a permission or turned Usage off. The
// backend tags these with code "permission_denied"; a bare 403 is not enough,
// because the API also returns 403 for account/company suspension and for
// business-rule locks such as "Technical round unlocks after the HR deadline
// passes", neither of which implies a profile change.
//
// Throttled because a single user action can fan out into parallel requests
// (UsageView fires billing + usage via Promise.all), each of which would
// otherwise dispatch its own event and trigger a redundant revalidation.
const PERMISSION_CHANGE_THROTTLE_MS = 2000;
let _lastPermissionChangeAt = 0;

export function resetPermissionChangeFlag() {
  _lastPermissionChangeAt = 0;
}

function abortError() {
  if (typeof DOMException === "function") {
    return new DOMException("The operation was aborted.", "AbortError");
  }
  const err = new Error("The operation was aborted.");
  err.name = "AbortError";
  return err;
}

export async function apiFetch(path, options = {}) {
  // `timeout` (ms) and `signal` are consumed here and never forwarded to fetch.
  // Timeout is opt-in: large multipart uploads legitimately run long, so
  // applying a blanket default here would abort working requests.
  const { timeout = 0, signal: externalSignal, ...fetchOptions } = options;
  if (externalSignal?.aborted) throw abortError();

  const token = localStorage.getItem("ai_hiring_access_token");

  const headers = {
    ...(fetchOptions.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
    ...(fetchOptions.headers || {}),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const controller = new AbortController();
  const forwardAbort = () => controller.abort();
  if (externalSignal) {
    externalSignal.addEventListener("abort", forwardAbort, { once: true });
  }

  let timedOut = false;
  const timer =
    timeout > 0
      ? setTimeout(() => {
          timedOut = true;
          controller.abort();
        }, timeout)
      : null;

  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...fetchOptions,
      headers,
      signal: controller.signal,
    });
  } catch (err) {
    if (timedOut) {
      throw new Error("The request timed out. Please check your connection and try again.");
    }
    throw err;
  } finally {
    if (timer) clearTimeout(timer);
    if (externalSignal) externalSignal.removeEventListener("abort", forwardAbort);
  }

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
    let errorCode = data.code || null;
    if (Array.isArray(errorMsg)) {
      errorMsg = errorMsg.map((e) => e.msg || e.message || JSON.stringify(e)).join("\n");
    } else if (errorMsg && typeof errorMsg === "object") {
      // Structured detail: { code, message }
      errorCode = errorMsg.code || errorCode;
      errorMsg = errorMsg.message || JSON.stringify(errorMsg);
    }
    const error = new Error(errorMsg);
    // Preserve the HTTP status: callers need to tell a 403 (access changed)
    // from a 404/500, which the message string alone cannot convey.
    error.status = response.status;
    if (errorCode) error.code = errorCode;

    if (
      response.status === 403 &&
      errorCode === "permission_denied" &&
      // An auth endpoint returning permission_denied would not imply that the
      // caller's own profile changed.
      !path.includes("/api/auth/")
    ) {
      const now = Date.now();
      if (now - _lastPermissionChangeAt > PERMISSION_CHANGE_THROTTLE_MS) {
        _lastPermissionChangeAt = now;
        window.dispatchEvent(new CustomEvent("auth:permissions-changed"));
      }
    }

    throw error;
  }
  return data;
}

export { API_BASE };
