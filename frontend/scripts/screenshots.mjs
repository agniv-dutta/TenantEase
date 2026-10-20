// Capture screenshots of each page at desktop and phone widths.
// Usage: node scripts/screenshots.mjs <baseUrl> <outDir>
import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";

const baseUrl = process.argv[2] ?? "http://127.0.0.1:5173";
const outDir = process.argv[3] ?? "../docs/screenshots";

const PAGES = [
  ["ledger", "/"],
  ["outlook", "/outlook"],
  ["outbox", "/outbox"],
  ["model-notes", "/model-notes"],
  ["foundation", "/foundation"],
];

const VIEWPORTS = [
  ["1440", { width: 1440, height: 900 }],
  ["390", { width: 390, height: 844 }],
];

await mkdir(outDir, { recursive: true });

const browser = await chromium.launch({ channel: "msedge" });
try {
  for (const [width, viewport] of VIEWPORTS) {
    const context = await browser.newContext({ viewport, deviceScaleFactor: 1 });
    const page = await context.newPage();
    for (const [name, path] of PAGES) {
      await page.goto(baseUrl + path, { waitUntil: "domcontentloaded" });
      await page.locator(".page-title").first().waitFor();
      if (path === "/") await page.locator(".ledger tbody tr").first().waitFor({ timeout: 60000 });
      if (path === "/outlook") await page.locator(".chart-svg").waitFor();
      if (path === "/outbox") await page.locator("article").first().waitFor({ timeout: 10000 }).catch(() => undefined);
      if (path === "/model-notes") await page.locator(".chart-svg").waitFor();
      await page.waitForTimeout(1200); // let the stamps settle
      await page.screenshot({ path: `${outDir}/${name}-${width}.png`, fullPage: false });
      console.log(`shot ${name}-${width}`);
      if (name === "model-notes") {
        await page.locator(".chart-svg").scrollIntoViewIfNeeded();
        await page.waitForTimeout(200);
        await page.screenshot({ path: `${outDir}/model-notes-calibration-${width}.png`, fullPage: false });
        await page.evaluate(() => window.scrollTo(0, 0));
      }
      if (name === "ledger") {
        const row = page.locator(".ledger tbody tr").first();
        await row.click();
        await page.locator(".drawer").waitFor();
        await page.waitForTimeout(900);
        await page.screenshot({ path: `${outDir}/drawer-${width}.png`, fullPage: false });
        console.log(`shot drawer-${width}`);
        await page.getByRole("button", { name: "Close" }).click();
      }
    }
    await context.close();
  }
} finally {
  await browser.close();
}
