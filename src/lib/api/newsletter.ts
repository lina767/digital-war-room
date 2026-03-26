import { apiFetch, apiUrl } from "./client";

/** POST /api/newsletter/subscribe – subscribe to daily briefing (double opt-in). */
export async function newsletterSubscribe(body: { email: string; conflict?: string }): Promise<{ message: string; conflict: string }> {
  const res = await apiFetch(apiUrl("newsletter/subscribe"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: body.email, conflict: body.conflict ?? "Iran" }),
  });
  const data = (await res.json().catch(() => ({}))) as { message?: string; conflict?: string; error?: string };
  if (!res.ok) {
    if (res.status === 409) {
      throw new Error("This email is already pending confirmation or subscribed. Please check your inbox and spam folder.");
    }
    if (res.status === 503) {
      throw new Error("Confirmation email could not be sent right now. Please try again in a minute.");
    }
    throw new Error(data?.error ?? `HTTP ${res.status}`);
  }
  return { message: data.message ?? "Subscribed.", conflict: data.conflict ?? "Iran" };
}

/** GET /api/newsletter/confirm?token=... – confirm subscription (double opt-in). */
export async function newsletterConfirm(token: string): Promise<{ message: string }> {
  const res = await apiFetch(`${apiUrl("newsletter/confirm")}?${new URLSearchParams({ token })}`, { method: "GET" });
  const data = (await res.json().catch(() => ({}))) as { message?: string; error?: string };
  if (!res.ok) throw new Error(data?.error ?? `HTTP ${res.status}`);
  return { message: data.message ?? "Confirmed." };
}

/** GET /api/newsletter/unsubscribe?token=... – unsubscribe. */
export async function newsletterUnsubscribe(token: string): Promise<{ message: string }> {
  const res = await apiFetch(`${apiUrl("newsletter/unsubscribe")}?${new URLSearchParams({ token })}`, { method: "GET" });
  const data = (await res.json().catch(() => ({}))) as { message?: string; error?: string };
  if (!res.ok) throw new Error(data?.error ?? `HTTP ${res.status}`);
  return { message: data.message ?? "Unsubscribed." };
}
