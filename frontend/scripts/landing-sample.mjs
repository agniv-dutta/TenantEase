import { writeFile } from "node:fs/promises";

const base = process.env.API_BASE ?? "http://127.0.0.1:8000";
const response = await fetch(`${base}/api/ledger?months=5`);
if (!response.ok) throw new Error(`Could not fetch the live ledger (${response.status}). Start the API and try again.`);
const ledger = await response.json();
const rows = ledger.rows.slice(0, 4).map((row) => ({
  ...row,
  cycles: row.cycles.slice(-4),
}));
await writeFile(new URL("../src/data/landing-sample.json", import.meta.url), `${JSON.stringify({ cycle_month: ledger.cycle_month, rows }, null, 2)}\n`);
