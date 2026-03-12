#!/usr/bin/env node
/**
 * MCP wrapper for RapidAPI ADSBexchange.
 * Reads ADSBEXCHANGE_RAPIDAPI_KEY and ADSBEXCHANGE_RAPIDAPI_HOST from backend/.env
 * and runs npx mcp-remote with those headers (key never in repo).
 */
import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const envPath = join(__dirname, "..", "backend", ".env");

let apiKey = process.env.ADSBEXCHANGE_RAPIDAPI_KEY || process.env.RAPIDAPI_KEY;
let apiHost = process.env.ADSBEXCHANGE_RAPIDAPI_HOST || "adsbexchange-com1.p.rapidapi.com";

try {
  const envContent = readFileSync(envPath, "utf8");
  for (const line of envContent.split("\n")) {
    const m = line.match(/^\s*ADSBEXCHANGE_RAPIDAPI_KEY\s*=\s*(.+)/);
    if (m) apiKey = m[1].replace(/^["']|["']$/g, "").trim();
    const m2 = line.match(/^\s*ADSBEXCHANGE_RAPIDAPI_HOST\s*=\s*(.+)/);
    if (m2) apiHost = m2[1].replace(/^["']|["']$/g, "").trim();
  }
} catch (_) {}

if (!apiKey) {
  console.error("ADSBEXCHANGE_RAPIDAPI_KEY not set in backend/.env or environment.");
  process.exit(1);
}

const child = spawn(
  "npx",
  [
    "mcp-remote",
    "https://mcp.rapidapi.com",
    "--header",
    `x-api-host: ${apiHost}`,
    "--header",
    `x-api-key: ${apiKey}`,
  ],
  { stdio: "inherit", shell: true }
);
child.on("exit", (code) => process.exit(code ?? 0));
