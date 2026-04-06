import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiFetch, getAuthHeaders } from "./client";

describe("api/client", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("returns authorization and tenant headers together", () => {
    localStorage.setItem("dwr_supabase_access_token", "token-123");
    localStorage.setItem("dwr_tenant_id", "tenant-abc");

    expect(getAuthHeaders()).toEqual({
      Authorization: "Bearer token-123",
      "X-Tenant-Id": "tenant-abc",
    });
  });

  it("falls back to API key when no bearer token exists", () => {
    localStorage.setItem("dwr_api_key", "dwr_key");
    localStorage.setItem("dwr_tenant_id", "tenant-abc");

    expect(getAuthHeaders()).toEqual({
      "X-Api-Key": "dwr_key",
      "X-Tenant-Id": "tenant-abc",
    });
  });

  it("retries with fallback origin on retriable backend failure", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response("deployment missing", {
          status: 503,
          headers: { "x-vercel-error": "DEPLOYMENT_NOT_FOUND" },
        }),
      )
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const res = await apiFetch("http://primary.invalid/api/analyze/latest?conflict=Iran", { method: "GET" });
    expect(res.ok).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
