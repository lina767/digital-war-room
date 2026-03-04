import { useEffect, useState, useCallback } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { supabase } from "@/integrations/supabase/client";
import type { Json, Database } from "@/integrations/supabase/types";

type UserSettingsRow = Database["public"]["Tables"]["user_settings"]["Row"];
type UserSettingsInsert = Database["public"]["Tables"]["user_settings"]["Insert"];
type ProfilesInsert = Database["public"]["Tables"]["profiles"]["Insert"];

export interface UserSettings {
  default_conflict: string;
  favorite_conflicts: string[];
  ui_state: Record<string, unknown>;
}

const DEFAULT_SETTINGS: UserSettings = {
  default_conflict: "US-Iran",
  favorite_conflicts: [],
  ui_state: {},
};

export function useUserSettings() {
  const { user } = useAuth();
  const [settings, setSettings] = useState<UserSettings>(DEFAULT_SETTINGS);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user?.id) {
      setSettings(DEFAULT_SETTINGS);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);

    const loadOrCreate = async () => {
      const { data, error: e } = await supabase
        .from("user_settings")
        .select("*")
        .eq("user_id", user.id)
        .single();

      if (cancelled) return;

      const row = data as UserSettingsRow | null;
      if (!e && row) {
        setSettings({
          default_conflict: (row.default_conflict as string) ?? DEFAULT_SETTINGS.default_conflict,
          favorite_conflicts: Array.isArray(row.favorite_conflicts) ? (row.favorite_conflicts as string[]) : [],
          ui_state: (row.ui_state as Record<string, unknown>) ?? {},
        });
        setLoading(false);
        return;
      }

      // No row (e.g. user created before trigger/backfill): create profile + settings then refetch
      await (supabase.from("profiles") as unknown as { upsert: (v: ProfilesInsert, o?: { onConflict?: string }) => Promise<unknown> }).upsert(
        { id: user.id, display_name: user.email ?? undefined },
        { onConflict: "id" }
      );
      const { error: insErr } = await (supabase.from("user_settings") as unknown as { upsert: (v: UserSettingsInsert, o?: { onConflict?: string }) => Promise<{ error: { message: string } | null }> }).upsert(
        { user_id: user.id },
        { onConflict: "user_id" }
      );
      if (cancelled) return;
      if (insErr) {
        setError(insErr.message);
        setSettings(DEFAULT_SETTINGS);
        setLoading(false);
        return;
      }
      const { data: retryData } = await supabase
        .from("user_settings")
        .select("*")
        .eq("user_id", user.id)
        .single();
      if (cancelled) return;
      const retryRow = retryData as UserSettingsRow | null;
      if (retryRow) {
        setSettings({
          default_conflict: (retryRow.default_conflict as string) ?? DEFAULT_SETTINGS.default_conflict,
          favorite_conflicts: Array.isArray(retryRow.favorite_conflicts) ? (retryRow.favorite_conflicts as string[]) : [],
          ui_state: (retryRow.ui_state as Record<string, unknown>) ?? {},
        });
      } else {
        setSettings(DEFAULT_SETTINGS);
      }
      setLoading(false);
    };

    loadOrCreate();
    return () => { cancelled = true; };
  }, [user?.id, user?.email]);

  const updateSettings = useCallback(
    async (partial: Partial<UserSettings>) => {
      if (!user?.id) return;
      const next = { ...settings, ...partial };
      setSettings(next);
      const { error: e } = await (supabase.from("user_settings") as unknown as { upsert: (v: UserSettingsInsert, o?: { onConflict?: string }) => Promise<{ error: { message: string } | null }> }).upsert(
        {
          user_id: user.id,
          updated_at: new Date().toISOString(),
          default_conflict: next.default_conflict,
          favorite_conflicts: next.favorite_conflicts as Json,
          ui_state: next.ui_state as Json,
        },
        { onConflict: "user_id" }
      );
      if (e) setError(e.message);
    },
    [user?.id, settings]
  );

  const setDefaultConflict = useCallback(
    (conflict: string) => updateSettings({ default_conflict: conflict }),
    [updateSettings]
  );

  const setFavoriteConflicts = useCallback(
    (favorites: string[]) => updateSettings({ favorite_conflicts: favorites }),
    [updateSettings]
  );

  const toggleFavorite = useCallback(
    (conflictId: string) => {
      const next = settings.favorite_conflicts.includes(conflictId)
        ? settings.favorite_conflicts.filter((f) => f !== conflictId)
        : [...settings.favorite_conflicts, conflictId];
      setFavoriteConflicts(next);
    },
    [settings.favorite_conflicts, setFavoriteConflicts]
  );

  const setUiState = useCallback(
    (state: Record<string, unknown>) => updateSettings({ ui_state: state }),
    [updateSettings]
  );

  return {
    settings,
    loading,
    error,
    updateSettings,
    setDefaultConflict,
    setFavoriteConflicts,
    toggleFavorite,
    setUiState,
  };
}
