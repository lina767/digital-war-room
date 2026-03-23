import { useState } from "react";
import { Helmet } from "react-helmet-async";
import { supabase } from "@/lib/supabase";

/**
 * Optional login: stores Supabase access token in localStorage as dwr_supabase_access_token
 * for multi-tenant API calls (see src/lib/api.ts getAuthHeaders).
 */
export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  const onSupabaseLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setMsg(null);
    if (!supabase) {
      setMsg("Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY in .env");
      return;
    }
    const { data, error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) {
      setMsg(error.message);
      return;
    }
    const token = data.session?.access_token;
    if (token) {
      localStorage.setItem("dwr_supabase_access_token", token);
      setMsg("Signed in. Token stored for API requests.");
    }
  };

  const onSaveApiKey = (e: React.FormEvent) => {
    e.preventDefault();
    const k = apiKey.trim();
    if (!k) {
      localStorage.removeItem("dwr_api_key");
      setMsg("API key cleared.");
      return;
    }
    localStorage.setItem("dwr_api_key", k);
    setMsg("API key saved for X-Api-Key requests.");
  };

  const onLogout = () => {
    localStorage.removeItem("dwr_supabase_access_token");
    localStorage.removeItem("dwr_api_key");
    localStorage.removeItem("dwr_tenant_id");
    void supabase?.auth.signOut();
    setMsg("Session cleared.");
  };

  return (
    <div className="min-h-screen bg-background text-foreground p-8 max-w-md mx-auto">
      <Helmet>
        <title>Login – Digital War Room</title>
      </Helmet>
      <h1 className="text-2xl font-semibold mb-6">API access</h1>
      <p className="text-sm text-muted-foreground mb-8">
        Use Supabase email login or a tenant API key from the backend. Tokens are stored only in this browser.
      </p>

      {supabase ? (
        <form onSubmit={onSupabaseLogin} className="space-y-4 mb-10">
          <h2 className="text-lg font-medium">Supabase</h2>
          <input
            type="email"
            className="w-full border rounded px-3 py-2 bg-background"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
          />
          <input
            type="password"
            className="w-full border rounded px-3 py-2 bg-background"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
          <button type="submit" className="w-full py-2 rounded bg-primary text-primary-foreground">
            Sign in
          </button>
        </form>
      ) : (
        <p className="text-sm text-muted-foreground mb-8">
          Supabase is not configured. Add VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY to use email login.
        </p>
      )}

      <form onSubmit={onSaveApiKey} className="space-y-4 mb-8">
        <h2 className="text-lg font-medium">Tenant API key</h2>
        <input
          type="password"
          className="w-full border rounded px-3 py-2 bg-background font-mono text-sm"
          placeholder="dwr_..."
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
        />
        <button type="submit" className="w-full py-2 rounded border">
          Save API key
        </button>
      </form>

      <button type="button" onClick={onLogout} className="text-sm text-muted-foreground underline">
        Clear stored credentials
      </button>

      {msg ? <p className="mt-6 text-sm">{msg}</p> : null}
    </div>
  );
}
