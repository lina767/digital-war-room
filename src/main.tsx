import { createRoot } from "react-dom/client";
import { HelmetProvider } from "react-helmet-async";
import "./index.css";

const API_URL = import.meta.env.VITE_API_URL as string | undefined;

function DeploySetupMessage() {
  return (
    <div style={{
      padding: 24,
      fontFamily: "system-ui, sans-serif",
      maxWidth: 560,
      margin: "0 auto",
      color: "#e2e8f0",
      background: "#0f172a",
      minHeight: "100vh",
      boxSizing: "border-box",
    }}>
      <h1 style={{ fontSize: "1.25rem", marginBottom: 16 }}>Deploy configuration missing</h1>
      <p style={{ marginBottom: 12, lineHeight: 1.5 }}>
        In Vercel, set under <strong>Project → Settings → Environment Variables</strong>:
      </p>
      <ul style={{ marginBottom: 16, paddingLeft: 20 }}>
        <li><code style={{ background: "#334155", padding: "2px 6px", borderRadius: 4 }}>VITE_API_URL</code> (backend URL, e.g. Railway)</li>
      </ul>
      <p style={{ lineHeight: 1.5 }}>Then trigger a <strong>Redeploy</strong>.</p>
    </div>
  );
}

const root = document.getElementById("root")!;
if (!API_URL?.trim()) {
  createRoot(root).render(
    <HelmetProvider>
      <DeploySetupMessage />
    </HelmetProvider>,
  );
} else {
  import("./App.tsx").then(({ default: App }) => {
    createRoot(root).render(
      <HelmetProvider>
        <App />
      </HelmetProvider>,
    );
  });
}
