import { chromium } from "playwright-core";
import { findChrome } from "./find-chrome.mjs";

const OUT = "/Users/romankuznetsov/Dev/Projects/GitLoco/docs/img";
const CHROME = findChrome();
const URL = "http://127.0.0.1:5173/";

async function snap(page, name) {
  await page.screenshot({ path: `${OUT}/${name}`, fullPage: false });
  console.log("wrote", name);
}

async function selectCommitBySubject(page, substr) {
  await page.locator("aside button", { hasText: substr }).first().click();
  await page.waitForTimeout(900);
}

const browser = await chromium.launch({ executablePath: CHROME });
try {
  const desktop = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
  });
  const page = await desktop.newPage();
  await page.goto(URL, { waitUntil: "networkidle" });
  await page.waitForSelector("aside button");
  await page.waitForTimeout(600);

  await snap(page, "01-overview.png");

  await selectCommitBySubject(page, "Frontend:");

  await page
    .locator("section header code", { hasText: "VersionPicker.tsx" })
    .first()
    .scrollIntoViewIfNeeded();
  const main = await page.$("main");
  await main.evaluate((el) => el.scrollBy({ top: 60 }));
  await page.waitForTimeout(500);
  await snap(page, "02-diff-syntax-highlight.png");

  const threadHeader = page.locator("text=Thread #1").first();
  await threadHeader.scrollIntoViewIfNeeded();
  await main.evaluate((el) => el.scrollBy({ top: -160 }));
  await page.waitForTimeout(400);
  await snap(page, "03-inline-thread.png");

  await main.evaluate((el) => el.scrollTo({ top: 0 }));
  await page.waitForTimeout(400);
  await snap(page, "04-version-compare.png");

  await desktop.close();

  const mobile = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
  });
  const m = await mobile.newPage();
  await m.goto(URL, { waitUntil: "networkidle" });
  await m.waitForTimeout(800);
  await m.locator('button[aria-label="Open commit list"]').click();
  await m.waitForTimeout(600);
  await snap(m, "05-mobile-drawer.png");
  await mobile.close();
} finally {
  await browser.close();
}
