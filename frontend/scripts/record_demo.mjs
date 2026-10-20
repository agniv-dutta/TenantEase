import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

const base = process.argv[2] ?? "http://127.0.0.1:5173";
const out = resolve("../docs/screen-recordings");
await mkdir(out, { recursive: true });
const browser = await chromium.launch({ channel: "msedge" });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce", recordVideo: { dir: out, size: { width: 1440, height: 900 } } });
const page = await context.newPage();
const started = Date.now();
async function tabTo(test, limit = 160, arg) {
  for (let i = 0; i < limit; i += 1) {
    const found = await page.evaluate(test, arg);
    if (found) return;
    await page.keyboard.press("Tab");
  }
  throw new Error("Could not reach the requested control using Tab.");
}
async function enterLink(label) {
  await tabTo((expected) => [...document.querySelectorAll("a")].some((a) => document.activeElement === a && a.textContent.trim() === expected), 160, label);
  await page.keyboard.press("Enter");
  await page.waitForTimeout(700);
}
try {
  await page.goto(base, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2000);
  await enterLink("Open the ledger");
  await page.locator(".ledger tbody tr").first().waitFor();
  const rows = await page.locator(".ledger tbody tr").evaluateAll((els) => els.map((el) => ({ id: Number(el.getAttribute("data-lease-id")), tier: el.querySelector(".cell-risk")?.textContent } )));
  const first = rows.find((r) => r.tier?.toLowerCase().includes("high")) ?? rows[0];
  await tabTo((id) => { const row = document.activeElement.closest("tr[data-lease-id]"); return !!row && Number(row.getAttribute("data-lease-id")) === id; }, 250, first.id);
  await page.keyboard.press("Enter");
  await page.locator(".drawer").waitFor();
  await page.waitForTimeout(3500);
  await tabTo(() => document.activeElement.tagName === "SELECT" && document.activeElement.labels?.[0]?.textContent?.includes("Language"));
  await page.keyboard.press("End");
  await page.keyboard.press("Tab");
  await page.keyboard.press("Enter"); // draft
  await page.getByRole("button", { name: "Approve" }).waitFor();
  await page.waitForTimeout(2500);
  await tabTo(() => document.activeElement.textContent.trim() === "Approve");
  await page.keyboard.press("Enter");
  await page.waitForTimeout(1200);
  await page.keyboard.press("Escape");
  await enterLink("Payments");
  const data = await page.request.get("http://127.0.0.1:8000/api/ledger?months=6").then((r) => r.json());
  const row = data.rows[0];
  await tabTo(() => document.activeElement.getAttribute("aria-label") === "Payment message");
  const msg = `${row.tenant_name} paid ${row.rent_inr} on 2026-10-20 by UPI reference DEMO42`;
  await page.keyboard.type(msg, { delay: 18 });
  await page.keyboard.press("Tab");
  await page.keyboard.press("Enter");
  await page.getByRole("heading", { name: "Review payment" }).waitFor({ timeout: 15000 });
  await page.waitForTimeout(2000);
  await tabTo(() => document.activeElement.textContent.trim() === "Confirm payment", 100);
  await page.keyboard.press("Enter");
  await page.waitForTimeout(1200);
  await enterLink("Portfolio");
  await page.waitForTimeout(3500);
  await enterLink("Outlook");
  await page.waitForTimeout(2500);
  for (let i = 0; i < 2; i += 1) {
    await tabTo(() => document.activeElement.type === "range");
    await page.keyboard.press("ArrowRight");
    await page.keyboard.press("Tab");
  }
  await page.waitForTimeout(2500);
  await enterLink("Model notes");
  await page.getByText("What this does not show", { exact: true }).waitFor();
  await page.waitForTimeout(5000);
} finally {
  const remaining = 120000 - (Date.now() - started);
  if (remaining > 0) await page.waitForTimeout(remaining);
  const video = page.video();
  await context.close();
  if (video) await video.saveAs(resolve(out, "tenantease-demo.webm"));
  await browser.close();
}
