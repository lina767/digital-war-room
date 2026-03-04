import { useEffect, useState, useCallback } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { supabase } from "@/integrations/supabase/client";
import type { Json } from "@/integrations/supabase/types";

export interface SavedAnalysis {
  id: string;
  user_id: string;
  created_at: string;
  conflict: string;
  label: string | null;
  note: string | null;
  payload: Record<string, unknown>;
}

export function useSavedAnalyses() {
  const { user } = useAuth();
  const [list, setList] = useState<SavedAnalysis[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchList = useCallback(() => {
    if (!user?.id) {
      setList([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    supabase
      .from("saved_analyses")
      .select("id, user_id, created_at, conflict, label, note, payload")
      .eq("user_id", user.id)
      .order("created_at", { ascending: false })
      .then(({ data, error: e }) => {
        setLoading(false);
        if (e) setError(e.message);
        else setList((data ?? []) as SavedAnalysis[]);
      });
  }, [user?.id]);

  useEffect(() => {
    fetchList();
  }, [fetchList]);

  const saveAnalysis = useCallback(
    async (params: { conflict: string; payload: Record<string, unknown>; label?: string; note?: string }) => {
      if (!user?.id) return null;
      const { data, error: e } = await supabase
        .from("saved_analyses")
        .insert({
          user_id: user.id,
          conflict: params.conflict,
          payload: params.payload as Json,
          label: params.label ?? null,
          note: params.note ?? null,
        })
        .select("id, created_at, conflict, label, note")
        .single();
      if (e) {
        setError(e.message);
        return null;
      }
      fetchList();
      return data;
    },
    [user?.id, fetchList]
  );

  const updateSaved = useCallback(
    async (id: string, updates: { label?: string; note?: string }) => {
      const { error: e } = await supabase.from("saved_analyses").update(updates).eq("id", id).eq("user_id", user?.id ?? "");
      if (e) setError(e.message);
      else fetchList();
    },
    [user?.id, fetchList]
  );

  const deleteSaved = useCallback(
    async (id: string) => {
      const { error: e } = await supabase.from("saved_analyses").delete().eq("id", id).eq("user_id", user?.id ?? "");
      if (e) setError(e.message);
      else fetchList();
    },
    [user?.id, fetchList]
  );

  return { list, loading, error, saveAnalysis, updateSaved, deleteSaved, refresh: fetchList };
}
