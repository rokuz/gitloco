import { chromium } from "playwright-core";

const OUT = "/Users/romankuznetsov/Dev/Projects/GitLoco/docs/img";
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
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
  // Desktop ---------------------------------------------------------------
  const desktop = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
  });
  const page = await desktop.newPage();
  await page.goto(URL, { waitUntil: "networkidle" });
  await page.waitForSelector("aside button");
  await page.waitForTimeout(600);

  // 1. Overview
  await snap(page, "01-overview.png");

  // Select the Frontend commit (seeded threads + 2 versions)
  await selectCommitBySubject(page, "Frontend:");

  // 2. Diff + syntax highlighting — VersionPicker.tsx top
  await page
    .locator("section header code", { hasText: "VersionPicker.tsx" })
    .first()
    .scrollIntoViewIfNeeded();
  await page.waitForTimeout(500);
  await snap(page, "02-diff-syntax-highlight.png");

  // 3. Inline thread — scroll to the "Thread #1" badge in the diff
  const threadHeader = page.locator("text=Thread #1").first();
  await threadHeader.scrollIntoViewIfNeeded();
  // Shift up so the diff lines above the thread are visible too
  const main = await page.$("main");
  await main.evaluate((el) => el.scrollBy({ top: -180 }));
  await page.waitForTimeout(400);
  await snap(page, "03-inline-thread.png");

  // 4. Compare picker — scroll the main pane to the top
  await main.evaluate((el) => el.scrollTo({ top: 0 }));
  await page.waitForTimeout(400);
  await snap(page, "04-version-compare.png");

  await desktop.close();

  // Mobile ----------------------------------------------------------------
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
  await m.locator('button:has-text("Frontend:")').first().click();
  await m.waitForTimeout(900);
  await snap(m, "06-mobile-diff.png");
  await mobile.close();
} finally {
  await browser.close();
}
