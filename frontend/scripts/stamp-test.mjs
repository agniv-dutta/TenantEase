// Render every stamp kind on the foundation page and assert its visible text.
import assert from "node:assert/strict";

import { chromium } from "playwright";

const baseUrl = process.argv[2] ?? "http://localhost:5173";
const browser = await chromium.launch({ channel: "msedge" });
try {
  const page = await browser.newPage();
  await page.goto(`${baseUrl}/foundation`, { waitUntil: "networkidle" });
  const stamps = page.locator(".stamp-cell svg");
  await stamps.first().waitFor();
  assert.equal(await stamps.count(), 4, "foundation page should render all stamp kinds");

  const visibleText = [];
  for (let index = 0; index < (await stamps.count()); index += 1) {
    visibleText.push((await stamps.nth(index).locator("text").allTextContents()).map((text) => text.trim()).filter(Boolean));
  }

  assert.deepEqual(visibleText, [
    ["LATE", "+9 days"],
    ["OVERDUE", "बाकी"],
    ["DUE", "देय"],
    ["APPROVED", "मंज़ूर"],
  ]);
} finally {
  await browser.close();
}
