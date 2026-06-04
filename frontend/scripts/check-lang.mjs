import { chromium } from "playwright-core";
import { findChrome } from "./find-chrome.mjs";

const CHROME = findChrome();
const URL = "http://127.0.0.1:7777/";

const browser = await chromium.launch({ executablePath: CHROME });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
page.on("console", (m) => {
  if (m.type() === "warning" || m.type() === "error") {
    console.log("page:", m.type(), m.text());
  }
});
await page.goto(URL, { waitUntil: "networkidle" });
await page.waitForSelector("aside button");
// Backend commit — has .py files with python
await page.locator("aside button", { hasText: "Backend:" }).first().click();
await page.waitForTimeout(1500);

const result = await page.evaluate(() => {
  // Find a python file's diff section
  const headers = Array.from(document.querySelectorAll("section header code"));
  const targets = headers
    .filter((h) => h.textContent && h.textContent.endsWith(".py"))
    .slice(0, 5)
    .map((h) => h.textContent);

  function colorsForFile(fileBasename) {
    const header = Array.from(document.querySelectorAll("section header code"))
      .find((h) => h.textContent === fileBasename);
    if (!header) return null;
    const section = header.closest("section");
    if (!section) return null;
    const spans = section.querySelectorAll(".diff-code span.token, .diff-code-insert span.token, .diff-code-delete span.token");
    const byClass = {};
    for (const s of spans) {
      const key = (s.className || "").trim();
      const col = window.getComputedStyle(s).color;
      if (!byClass[key]) byClass[key] = { count: 0, color: col };
      byClass[key].count++;
    }
    return Object.entries(byClass)
      .sort((a, b) => b[1].count - a[1].count)
      .slice(0, 10)
      .map(([cls, v]) => ({ class: cls, count: v.count, color: v.color }));
  }
  // pick first available .py
  const sample = targets.length > 0 ? colorsForFile(targets[0]) : null;
  return { pythonFiles: targets, firstFileTokens: sample };
});
console.log(JSON.stringify(result, null, 2));
await browser.close();
