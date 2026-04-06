/**
 * Shared REST client: base URL, WebSocket URL, auth headers, timeout + fetch wrapper.
 */

export const DEFAULT_FETCH_TIMEOUT_MS = 15_000;

/** Optional Supabase session token or DWR API key (multi-tenant backend). */
export function getAuthHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const headers: Record<string, string> = {};
  const token = localStorage.getItem("dwr_supabase_access_token")?.trim();
  const key = localStorage.getItem("dwr_api_key")?.trim();
  const tid = localStorage.getItem("dwr_tenant_id");
  if (token) headers.Authorization = `Bearer ${token}`;
  else if (key) headers["X-Api-Key"] = key;
  if (tid) headers["X-Tenant-Id"] = tid;
  return headers;
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
 * Multiple fallbacks are supported via comma-separated URLs.
 */
export function getApiBase(): string {
  const [primary] = getApiBaseCandidates();
  if (primary) return primary;
  if (typeof window !== "undefined") return window.location.origin;
  return "http://localhost:8000";
}

export function getApiBaseCandidates(): string[] {
  const env = import.meta.env.VITE_API_URL as string | undefined;
  const fromEnv = (env ?? "")
    .split(",")
    .map((s) => s.trim().replace(/\/$/, ""))
    .filter(Boolean);
  if (fromEnv.length > 0) return [...new Set(fromEnv)];
  if (typeof window !== "undefined") return [window.location.origin];
  return ["http://localhost:8000"];
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

function isRetriableBackendFailure(res: Response): boolean {
  const vercelErr = (res.headers.get("x-vercel-error") || "").toUpperCase();
  return vercelErr === "DEPLOYMENT_NOT_FOUND" || res.status === 502 || res.status === 503 || res.status === 504;
}

function withBase(url: string, base: string): string {
  const current = new URL(url);
  const target = new URL(base);
  current.protocol = target.protocol;
  current.host = target.host;
  return current.toString();
}

async function fetchWithTimeout(url: string, init: RequestInit, timeoutMs: number): Promise<Response> {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, mergeAuthHeaders({ ...init, signal: controller.signal }));
  } finally {
    clearTimeout(id);
  }
}

/** Central fetch: injects auth headers, AbortController timeout. */
export async function apiFetch(url: string, init: ApiFetchInit = {}): Promise<Response> {
  const { timeoutMs = DEFAULT_FETCH_TIMEOUT_MS, ...rest } = init;
  const candidates = getApiBaseCandidates();
  const attempted = new Set<string>();

  const first = new URL(url).origin;
  const orderedOrigins = [first, ...candidates].filter((origin, idx, arr) => arr.indexOf(origin) === idx);

  let lastError: unknown;
  for (const origin of orderedOrigins) {
    const attemptUrl = withBase(url, origin);
    attempted.add(origin);
    try {
      const res = await fetchWithTimeout(attemptUrl, rest, timeoutMs);
      if (isRetriableBackendFailure(res)) continue;
      return res;
    } catch (e) {
      lastError = e;
    }
  }
  if (lastError) {
    throw lastError;
  }
  throw new Error(`Backend unreachable for origins: ${[...attempted].join(", ")}`);
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
