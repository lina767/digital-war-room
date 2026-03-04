import { useEffect, useState, useCallback } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { supabase } from "@/integrations/supabase/client";

export interface UserProfile {
  id: string;
  display_name: string | null;
  role: "user" | "admin";
  organization: string | null;
  created_at: string;
  updated_at: string;
}

export function useUserProfile() {
  const { user } = useAuth();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const ensureProfile = useCallback(async () => {
    if (!user?.id) return false;
    setError(null);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { error: upsertErr } = await (supabase.from("profiles") as any).upsert(
      { id: user.id, display_name: user.email ?? null, updated_at: new Date().toISOString() },
      { onConflict: "id" }
    );
    if (upsertErr) {
      setError(upsertErr.message);
      return false;
    }
    const { data, error: fetchErr } = await supabase.from("profiles").select("*").eq("id", user.id).single();
    if (!fetchErr && data) {
      setProfile(data as UserProfile);
      return true;
    }
    if (fetchErr) setError(fetchErr.message);
    return false;
  }, [user?.id, user?.email]);

  useEffect(() => {
    if (!user?.id) {
      setProfile(null);
      setError(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);

    const loadOrCreate = async () => {
      const { data, error: fetchError } = await supabase
        .from("profiles")
        .select("*")
        .eq("id", user.id)
        .single();

      if (cancelled) return;

      if (!fetchError && data) {
        setProfile(data as UserProfile);
        setLoading(false);
        return;
      }

      await ensureProfile();
      if (cancelled) return;
      setLoading(false);
    };

    loadOrCreate();
    return () => { cancelled = true; };
  }, [user?.id, user?.email, ensureProfile]);

  const updateProfile = useCallback(
    async (updates: { display_name?: string; organization?: string }) => {
      if (!user?.id) return;
      setError(null);
      const payload = { id: user.id, ...updates, updated_at: new Date().toISOString() };
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { error: err } = await (supabase.from("profiles") as any).upsert(payload, { onConflict: "id" });
      if (err) {
        setError(err.message);
        return;
      }
      setProfile((p) => (p ? { ...p, ...updates } : { ...payload, role: "user", created_at: "", updated_at: payload.updated_at } as UserProfile));
    },
    [user?.id]
  );

  return { profile, loading, error, updateProfile, ensureProfile };
}
