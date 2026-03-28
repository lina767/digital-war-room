import { apiFetch, apiUrl } from "./client";

export type AlertRuleKind = "keyword" | "escalation_min" | "threat_level";

export interface AlertRule {
  id: string;
  name: string;
  enabled: boolean;
  conflict_substring: string;
  rule_kind: AlertRuleKind;
  keyword?: string | null;
  min_escalation?: number | null;
  threat_levels?: string | null;
  notify_email?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface AlertNotification {
  id: string;
  rule_id: string;
  conflict: string;
  title: string;
  body: string;
  payload: Record<string, unknown>;
  created_at: string;
  read_at?: string | null;
}

export async function fetchAlertRules(): Promise<AlertRule[]> {
  const res = await apiFetch(apiUrl("alerts/rules"), { method: "GET", timeoutMs: 15_000 });
  if (!res.ok) throw new Error(`alerts/rules ${res.status}`);
  const data = (await res.json()) as { rules?: AlertRule[] };
  return data.rules ?? [];
}

export async function createAlertRule(body: {
  name: string;
  rule_kind: AlertRuleKind;
  conflict_substring?: string;
  keyword?: string | null;
  min_escalation?: number | null;
  threat_levels?: string | null;
  notify_email?: string | null;
  enabled?: boolean;
}): Promise<AlertRule> {
  const res = await apiFetch(apiUrl("alerts/rules"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    timeoutMs: 15_000,
  });
  if (!res.ok) throw new Error(`alerts/rules POST ${res.status}`);
  const data = (await res.json()) as { rule: AlertRule };
  return data.rule;
}

export async function updateAlertRule(
  id: string,
  patch: Partial<{
    name: string;
    enabled: boolean;
    conflict_substring: string;
    rule_kind: AlertRuleKind;
    keyword: string | null;
    min_escalation: number | null;
    threat_levels: string | null;
    notify_email: string | null;
  }>,
): Promise<AlertRule> {
  const res = await apiFetch(apiUrl(`alerts/rules/${encodeURIComponent(id)}`), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
    timeoutMs: 15_000,
  });
  if (!res.ok) throw new Error(`alerts/rules PATCH ${res.status}`);
  const data = (await res.json()) as { rule: AlertRule };
  return data.rule;
}

export async function deleteAlertRule(id: string): Promise<void> {
  const res = await apiFetch(apiUrl(`alerts/rules/${encodeURIComponent(id)}`), {
    method: "DELETE",
    timeoutMs: 15_000,
  });
  if (!res.ok) throw new Error(`alerts/rules DELETE ${res.status}`);
}

export async function fetchNotifications(options?: { limit?: number; unreadOnly?: boolean }): Promise<{
  notifications: AlertNotification[];
  unread_count: number;
}> {
  const res = await apiFetch(
    apiUrl("alerts/notifications", {
      limit: options?.limit ?? 50,
      unread_only: options?.unreadOnly ? "true" : undefined,
    }),
    { method: "GET", timeoutMs: 15_000 },
  );
  if (!res.ok) throw new Error(`alerts/notifications ${res.status}`);
  return (await res.json()) as { notifications: AlertNotification[]; unread_count: number };
}

export async function markAllNotificationsRead(): Promise<void> {
  const res = await apiFetch(apiUrl("alerts/notifications/read-all"), {
    method: "POST",
    timeoutMs: 15_000,
  });
  if (!res.ok) throw new Error(`read-all ${res.status}`);
}

export async function markNotificationRead(id: string): Promise<void> {
  const res = await apiFetch(apiUrl(`alerts/notifications/${encodeURIComponent(id)}/read`), {
    method: "POST",
    timeoutMs: 15_000,
  });
  if (!res.ok) throw new Error(`read ${res.status}`);
}
