import { createClient, SupabaseClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const anon = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

/** Null when Supabase env is not configured (local dev without auth). */
export const supabase: SupabaseClient | null =
  url && anon ? createClient(url, anon, { auth: { persistSession: false } }) : null;
