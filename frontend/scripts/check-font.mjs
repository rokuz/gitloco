import { chromium } from "playwright-core";
import { findChrome } from "./find-chrome.mjs";

const browser = await chromium.launch({ executablePath: findChrome() });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
await page.goto("http://127.0.0.1:5173/", { waitUntil: "networkidle" });
await page.waitForSelector("aside button");
// Click the first real commit (skip the working-tree pseudo-entry if present).
const buttons = page.locator("aside button");
const count = await buttons.count();
await buttons.nth(count > 1 ? 1 : 0).click();
await page.waitForTimeout(1500);
await page.evaluate(() => document.fonts.ready);

const result = await page.evaluate(async () => {
  const loaded = [...document.fonts].map((f) => `${f.family} ${f.status}`);
  // A code cell in the diff + a font-mono SHA in the header.
  const codeCell = document.querySelector(".diff-code, .diff-code-insert, .diff-code-delete");
  const shaEl = document.querySelector("h2.font-mono, code.font-mono, .font-mono");
  const fam = (el) => (el ? getComputedStyle(el).fontFamily : null);
  return {
    fontsLoaded: loaded.filter((f) => f.includes("JetBrains")),
    diffFontFamily: fam(codeCell),
    monoUtilFontFamily: fam(shaEl),
    jetbrainsCheck: document.fonts.check('12px "JetBrains Mono Variable"'),
  };
});
console.log(JSON.stringify(result, null, 2));
await browser.close();
