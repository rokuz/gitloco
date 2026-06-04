import { chromium } from "playwright-core";
import { findChrome } from "./find-chrome.mjs";

const CHROME = findChrome();
const browser = await chromium.launch({ executablePath: CHROME });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
await page.goto("http://127.0.0.1:5173/", { waitUntil: "networkidle" });
await page.waitForSelector("aside button");
await page.locator("aside button", { hasText: "Frontend:" }).first().click();
await page.waitForTimeout(1200);

const result = await page.evaluate(() => {
  const out = [];
  for (const cls of ["token.keyword", "token.string", "token.function"]) {
    const sel = "span." + cls.replace(/\./g, ".");
    const el = document.querySelector(sel);
    if (el) {
      const cs = window.getComputedStyle(el);
      out.push({
        selector: sel,
        textSample: el.textContent.slice(0, 30),
        color: cs.color,
        className: el.className,
        outerHTMLLen: el.outerHTML.length,
      });
    } else {
      out.push({ selector: sel, found: false });
    }
  }
  // Also check whether the diff.css rules made it into the document.
  const sheets = Array.from(document.styleSheets);
  let foundTokenRule = false;
  for (const s of sheets) {
    try {
      for (const r of s.cssRules) {
        if (r.cssText && r.cssText.includes(".token.keyword")) {
          foundTokenRule = true;
          break;
        }
      }
    } catch (_) {}
    if (foundTokenRule) break;
  }
  return { samples: out, foundTokenRule };
});
console.log(JSON.stringify(result, null, 2));
await browser.close();
