/**
 * Shared REST client: base URL, WebSocket URL, auth headers, timeout + fetch wrapper.
 */

export const DEFAULT_FETCH_TIMEOUT_MS = 15_000;

/** Optional Supabase session token or DWR API key (multi-tenant backend). */
export function getAuthHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const token = localStorage.getItem("dwr_supabase_access_token");
  if (token) return { Authorization: `Bearer ${token}` };
  const key = localStorage.getItem("dwr_api_key");
  if (key) return { "X-Api-Key": key };
  const tid = localStorage.getItem("dwr_tenant_id");
  if (tid) return { "X-Tenant-Id": tid };
  return {};
}

function mergeAuthHeaders(init: RequestInit): RequestInit {
  const auth = getAuthHeaders();
  if (Object.keys(auth).length === 0) return init;
  const h = new Headers(init.headers);
  for (const [k, v] of Object.entries(auth)) {
    if (!h.has(k)) h.set(k, v);
  }
  return { ...init, headers: h };
}

export class HttpError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly bodyText?: string,
  ) {
    super(message);
    this.name = "HttpError";
  }
}

/**
 * Backend API base URL for REST and WebSocket.
 * Set VITE_API_URL in .env (e.g. http://localhost:8000) for local backend.
 */
export function getApiBase(): string {
  const env = import.meta.env.VITE_API_URL as string | undefined;
  if (env) return env.replace(/\/$/, "");
  if (typeof window !== "undefined") return window.location.origin;
  return "http://localhost:8000";
}

export function getWsUrl(path: string): string {
  const base = getApiBase();
  return base.replace(/^http/, "ws") + path;
}

/** Absolute REST URL under `/api/…`. Omits `search` entries whose value is `undefined`. */
export function apiUrl(path: string, search?: Record<string, string | number | undefined>): string {
  const base = getApiBase();
  const normalized = path.startsWith("/api/") ? path : `/api/${path.replace(/^\//, "")}`;
  const url = new URL(normalized, base);
  if (search) {
    for (const [k, v] of Object.entries(search)) {
      if (v !== undefined) url.searchParams.set(k, String(v));
    }
  }
  return url.toString();
}

export type ApiFetchInit = Omit<RequestInit, "signal"> & { timeoutMs?: number };

/** Central fetch: injects auth headers, AbortController timeout. */
export async function apiFetch(url: string, init: ApiFetchInit = {}): Promise<Response> {
  const { timeoutMs = DEFAULT_FETCH_TIMEOUT_MS, ...rest } = init;
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, mergeAuthHeaders({ ...rest, signal: controller.signal }));
  } finally {
    clearTimeout(id);
  }
}

/** Parse JSON after a successful response. */
export async function readJson<T>(res: Response): Promise<T> {
  return (await res.json()) as T;
}

/**
 * Parse JSON body; if `!res.ok`, throws HttpError using `error` / `message` fields when present.
 */
export async function readJsonOrThrow<T>(res: Response): Promise<T> {
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown> & { error?: string; message?: string };
  if (!res.ok) {
    const msg =
      typeof data.error === "string"
        ? data.error
        : typeof data.message === "string"
          ? data.message
          : `HTTP ${res.status}`;
    throw new HttpError(msg, res.status);
  }
  return data as T;
}

/** Successful JSON body; on `!ok` throws with response text (e.g. proxy / validation errors). */
export async function readOkJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    throw new HttpError(text || `HTTP ${res.status}`, res.status, text);
  }
  return (await res.json()) as T;
}
