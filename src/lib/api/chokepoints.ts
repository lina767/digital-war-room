import { apiFetch, apiUrl, DEFAULT_FETCH_TIMEOUT_MS, readOkJson } from "./client";

/** GET /api/chokepoints/overrides. */
export async function getChokepointOverrides(): Promise<Record<string, string>> {
  try {
    const res = await apiFetch(apiUrl("chokepoints/overrides"), {
      method: "GET",
      timeoutMs: DEFAULT_FETCH_TIMEOUT_MS,
    });
    if (!res.ok) return {};
    const next = (await res.json()) as Record<string, string> | null;
    return next ?? {};
  } catch {
    return {};
  }
}

/** POST /api/chokepoints/overrides. */
export async function postChokepointOverrides(overrides: Record<string, string>): Promise<Record<string, string>> {
  const res = await apiFetch(apiUrl("chokepoints/overrides"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(overrides),
    timeoutMs: DEFAULT_FETCH_TIMEOUT_MS,
  });
  const updated = await readOkJson<Record<string, string>>(res);
  return updated ?? {};
}
