// Cross-platform Chrome/Chromium/Edge resolver for the dev screenshot scripts.
// Order:
//   1. CHROME_PATH env var (explicit override).
//   2. Common per-platform install locations.
//   3. PATH (`which chromium-browser` / `which google-chrome` …).
// Throws a helpful message if nothing usable is found.

import { existsSync } from "node:fs";
import { execSync } from "node:child_process";
import { platform } from "node:process";

const candidatesByPlatform = {
  darwin: [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
  ],
  linux: [
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/snap/bin/chromium",
    "/usr/bin/microsoft-edge",
    "/usr/bin/brave-browser",
  ],
  win32: [
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
  ],
};

const pathCommands = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge", "brave-browser"];

export function findChrome() {
  if (process.env.CHROME_PATH && existsSync(process.env.CHROME_PATH)) {
    return process.env.CHROME_PATH;
  }
  const candidates = candidatesByPlatform[platform] ?? [];
  for (const p of candidates) {
    if (existsSync(p)) return p;
  }
  if (platform !== "win32") {
    for (const cmd of pathCommands) {
      try {
        const out = execSync(`command -v ${cmd}`, { encoding: "utf8" }).trim();
        if (out && existsSync(out)) return out;
      } catch (_) {
        // not on PATH, keep trying
      }
    }
  }
  throw new Error(
    "Could not find Chrome/Chromium. Set CHROME_PATH or install Chrome/Chromium.",
  );
}
