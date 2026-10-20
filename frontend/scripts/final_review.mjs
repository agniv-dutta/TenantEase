import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const baseUrl = process.argv[2] ?? "http://127.0.0.1:5173";
const outDir = resolve(dirname(fileURLToPath(import.meta.url)), "../../docs/screenshots");
const pages = [
  ["landing", "/"], ["ledger", "/app/ledger"], ["outlook", "/app/outlook"],
  ["outbox", "/app/outbox"], ["portfolio", "/app/portfolio"],
  ["payments", "/app/payments"], ["model-notes", "/app/model-notes"],
];
const sizes = [[390, 844], [768, 1024], [1440, 900]];
const browser = await chromium.launch({ channel: "msedge" });
const errors = [];
await mkdir(outDir, { recursive: true });
try {
  for (const [width, height] of sizes) {
    const context = await browser.newContext({ viewport: { width, height }, reducedMotion: "reduce" });
    const page = await context.newPage();
    page.on("pageerror", (error) => errors.push(`${width}px page error: ${error.message}`));
    page.on("console", (message) => { if (message.type() === "error") errors.push(`${width}px console error: ${message.text()}`); });
    for (const [name, path] of pages) {
      const response = await page.goto(`${baseUrl}${path}`, { waitUntil: "domcontentloaded" });
      if (!response?.ok()) errors.push(`${path} returned ${response?.status()}`);
      await page.locator("h1").first().waitFor();
      await page.waitForFunction(() => !/Loading (the|portfolio|forecast)/.test(document.body.innerText), null, { timeout: 20000 }).catch(() => undefined);
      const dims = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth, reduced: matchMedia("(prefers-reduced-motion: reduce)").matches }));
      if (!dims.reduced) errors.push(`${path} did not honor reduced motion at ${width}px`);
      if (dims.document > dims.viewport) errors.push(`${path} overflows horizontally at ${width}px (${dims.document}px)`);
      if (width !== 768) await page.screenshot({ path: `${outDir}/${name}-${width}.png`, fullPage: false });
    }
    if (width !== 768) {
      const data = await page.request.get("http://127.0.0.1:8000/api/ledger?months=6").then((r) => r.json());
      const high = data.rows.find((row) => row.current.tier === "high") ?? data.rows[0];
      await page.goto(`${baseUrl}/app/ledger?lease=${high.lease_id}`, { waitUntil: "domcontentloaded" });
      await page.locator(".drawer").waitFor();
      await page.waitForTimeout(500);
      await page.screenshot({ path: `${outDir}/drawer-${width}.png`, fullPage: false });
    }
    await context.close();
  }
} finally {
  await browser.close();
}
console.log(errors.length ? errors.join("\n") : "Viewport, reduced-motion, and console review passed at 390, 768, and 1440px.");
process.exit(errors.length ? 1 : 0);
