/**
 * One-off Resend smoke test (Node 18+).
 *
 * Do NOT hardcode your API key. Replace `re_xxxxxxxxx` by setting env:
 *
 *   export RESEND_API_KEY=re_xxxxxxxx   # your real key from Resend
 *   export RESEND_TEST_TO=you@example.com
 *   export RESEND_TEST_FROM=onboarding@resend.dev   # or your verified domain address
 *
 *   node scripts/test-resend-send.mjs
 *
 * Or: from repo root, load backend/.env if you keep keys there:
 *   set -a && source backend/.env && set +a && node scripts/test-resend-send.mjs
 */

const apiKey = process.env.RESEND_API_KEY?.trim();
const to = process.env.RESEND_TEST_TO?.trim() || "social@linabraun.eu";
const from = process.env.RESEND_TEST_FROM?.trim() || "onboarding@resend.dev";

if (!apiKey || apiKey === "re_xxxxxxxxx") {
  console.error(
    "Set RESEND_API_KEY to your real Resend API key (not re_xxxxxxxxx).\n" +
      "Example: export RESEND_API_KEY=re_abc123..."
  );
  process.exit(1);
}

const body = {
  from,
  to: [to],
  subject: "Hello World",
  html: "<p>Congrats on sending your <strong>first email</strong>!</p>",
};

const res = await fetch("https://api.resend.com/emails", {
  method: "POST",
  headers: {
    Authorization: `Bearer ${apiKey}`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify(body),
});

const text = await res.text();
if (!res.ok) {
  console.error("Resend error", res.status, text);
  process.exit(1);
}
console.log("OK", res.status, text);
