import { createRoot } from "react-dom/client";
import { HelmetProvider } from "react-helmet-async";
import { DeploySetupMessage } from "@/components/DeploySetupMessage";
import "./index.css";
import "./styles/briefing.css";

const API_URL = import.meta.env.VITE_API_URL as string | undefined;

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
