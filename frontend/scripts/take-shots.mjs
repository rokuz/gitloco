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
  // Use the first *visible* matching button — avoids picking up the hidden
  // desktop sidebar button when we're actually in the mobile drawer.
  await page
    .locator("button:visible")
    .filter({ hasText: substr })
    .first()
    .click();
  await page.waitForTimeout(900);
}

const browser = await chromium.launch({ executablePath: CHROME });
try {
  // ── Desktop ───────────────────────────────────────────────────────────
  const desktop = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
  });
  // Force light theme before the page loads so the toggle's initial state
  // doesn't depend on the host's prefers-color-scheme.
  await desktop.addInitScript(() => {
    try {
      window.localStorage.setItem("gitloco-theme", "light");
    } catch (_) {
      /* ignore */
    }
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

  // ── Mobile ────────────────────────────────────────────────────────────
  const mobile = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
  });
  await mobile.addInitScript(() => {
    try {
      window.localStorage.setItem("gitloco-theme", "light");
    } catch (_) {
      /* ignore */
    }
  });

  const m = await mobile.newPage();
  await m.goto(URL, { waitUntil: "networkidle" });
  await m.waitForTimeout(800);

  // 05: drawer open with the commit list
  await m.locator('button[aria-label="Open commit list"]').click();
  await m.waitForTimeout(600);
  await snap(m, "05-mobile-drawer.png");

  // Select the Frontend commit (visible button is inside the drawer)
  await selectCommitBySubject(m, "Frontend:");

  // 06: inline thread on mobile
  const mthread = m.locator("text=Thread #1").first();
  await mthread.scrollIntoViewIfNeeded();
  const mmain = await m.$("main");
  if (mmain) await mmain.evaluate((el) => el.scrollBy({ top: -120 }));
  await m.waitForTimeout(500);
  await snap(m, "06-mobile-thread.png");

  await mobile.close();
} finally {
  await browser.close();
}
