// Confirm the first-load stamp sequence does not replay after ledger changes.
import assert from "node:assert/strict";

import { chromium } from "playwright";

const baseUrl = process.argv[2] ?? "http://127.0.0.1:5173";
const browser = await chromium.launch({ channel: "msedge" });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await page.locator(".ledger tbody tr").first().waitFor({ timeout: 60000 });
  const initialAnimations = page.locator('.ledger .stamp-cell[style*="animation"]');
  assert.ok((await initialAnimations.count()) > 0, "open and overdue stamps should animate on first load");

  await page.getByLabel("Highest risk first").uncheck();
  await page.waitForTimeout(200);
  assert.equal(await initialAnimations.count(), 0, "sorting should not replay stamps");

  await page.getByLabel("Only leases that need a call").check();
  await page.waitForTimeout(200);
  assert.equal(await initialAnimations.count(), 0, "filtering should not replay stamps");

  await page.getByRole("link", { name: "Outbox" }).click();
  await page.getByRole("heading", { name: "Outbox" }).waitFor();
  await page.getByRole("link", { name: "Ledger" }).click();
  await page.locator(".ledger tbody tr").first().waitFor({ timeout: 60000 });
  assert.equal(await initialAnimations.count(), 0, "returning to the ledger should not replay stamps");
} finally {
  await browser.close();
}
