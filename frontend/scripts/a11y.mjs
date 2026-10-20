// Run axe-core against every page and print serious/critical violations.
// Usage: node scripts/a11y.mjs <baseUrl>
import { chromium } from "playwright";
import { AxeBuilder } from "@axe-core/playwright";

const baseUrl = process.argv[2] ?? "http://localhost:5173";
const PAGES = [
  "/",
  "/app/ledger",
  "/app/portfolio",
  "/app/payments",
  "/app/audit",
  "/app/outlook",
  "/app/outbox",
  "/app/model-notes",
  "/app/foundation",
];

const browser = await chromium.launch({ channel: "msedge" });
let failures = 0;
try {
  // reducedMotion avoids scanning mid-animation opacity dips (which are not the
  // steady-state colours) and also exercises the reduced-motion reset.
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    reducedMotion: "reduce",
  });
  const page = await context.newPage();
  for (const path of PAGES) {
    await page.goto(baseUrl + path, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(600);
    const results = await new AxeBuilder({ page }).analyze();
    const serious = results.violations.filter((v) => ["serious", "critical"].includes(v.impact));
    console.log(`${path}: ${serious.length} serious/critical`);
    for (const v of serious) {
      console.log(`  - ${v.id} (${v.impact}) x${v.nodes.length}: ${v.help}`);
      for (const node of v.nodes.slice(0, 3)) console.log(`      ${node.target.join(" ")}`);
    }
    failures += serious.length;
  }
} finally {
  await browser.close();
}
console.log(failures === 0 ? "axe: clean" : `axe: ${failures} serious/critical issues`);
process.exit(failures === 0 ? 0 : 1);
