const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

// ── Refresh guard: prevents infinite 401 → refresh → 401 loops ──
let _isRefreshing = false;
let _refreshPromise: Promise<boolean> | null = null;

async function refreshAccessToken(): Promise<boolean> {
  // If a refresh is already in flight, wait for it (dedup concurrent calls)
  if (_isRefreshing && _refreshPromise) return _refreshPromise;

  const refreshToken = localStorage.getItem("refresh_token");
  if (!refreshToken) return false;

  _isRefreshing = true;
  _refreshPromise = (async () => {
    try {
      const res = await fetch(`${API_URL}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!res.ok) return false;
      const data = await res.json();
      localStorage.setItem("access_token", data.access_token);
      localStorage.setItem("refresh_token", data.refresh_token);
      return true;
    } catch {
      return false;
    } finally {
      _isRefreshing = false;
      _refreshPromise = null;
    }
  })();

  return _refreshPromise;
}

function clearAuthAndRedirect() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
  if (typeof window !== "undefined" && window.location.pathname !== "/login") {
    window.location.href = "/login";
  }
}

export async function apiFetch<T = unknown>(
  endpoint: string,
  options?: RequestInit & { noAuth?: boolean; _retried?: boolean }
): Promise<T> {
  const token = localStorage.getItem("access_token");

  const res = await fetch(`${API_URL}${endpoint}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token && !options?.noAuth
        ? { Authorization: `Bearer ${token}` }
        : {}),
      ...options?.headers,
    },
  });

  // ── 401 handling with single-retry guard ──
  if (res.status === 401 && !options?.noAuth && !options?._retried) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      // Retry ONCE with _retried flag — prevents infinite loop
      return apiFetch<T>(endpoint, { ...options, _retried: true });
    }
    clearAuthAndRedirect();
    throw new Error("Session expired");
  }

  // If the retried request ALSO 401s, don't recurse — just redirect
  if (res.status === 401 && options?._retried) {
    clearAuthAndRedirect();
    throw new Error("Session expired");
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    // FastAPI validation errors return detail as an array of objects
    let msg: string;
    if (typeof body.detail === "string") {
      msg = body.detail;
    } else if (Array.isArray(body.detail)) {
      msg = body.detail
        .map((e: { msg?: string }) => e.msg || JSON.stringify(e))
        .join(", ");
    } else {
      msg = res.statusText;
    }
    throw new Error(msg);
  }

  return res.json() as Promise<T>;
}

// ── Typed helpers ──

export const api = {
  get: <T = unknown>(url: string) => apiFetch<T>(url),

  post: <T = unknown>(url: string, body: unknown) =>
    apiFetch<T>(url, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  patch: <T = unknown>(url: string, body: unknown) =>
    apiFetch<T>(url, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  login: async (email: string, password: string) => {
    const data = await apiFetch<{
      access_token: string;
      refresh_token: string;
    }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
      noAuth: true,
    });
    localStorage.setItem("access_token", data.access_token);
    localStorage.setItem("refresh_token", data.refresh_token);
    return data;
  },

  logout: () => {
    clearAuthAndRedirect();
  },
};
