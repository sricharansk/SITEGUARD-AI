// Capture the deck's dashboard and audit screens from a running stack (make up / make run).
// Run from the repository root after `cd frontend && npm ci && npx playwright install chromium`:
//   node docs/presentation/source/capture_screens.cjs <out-dir> before   # dashboard before resolve_all
//   node docs/presentation/source/capture_screens.cjs <out-dir> after    # dashboard, incident list, workspace, audit
// BASE_URL (default http://localhost:8000) and CHROMIUM_PATH (optional, a local Chromium) are read from the
// environment. Demo logins use SITEGUARD_DEMO_PASSWORD (default siteguard-demo).
const path = require("path");
const { createRequire } = require("module");
const { chromium } = createRequire(path.resolve("frontend/package.json"))("playwright");

const BASE = process.env.BASE_URL || "http://localhost:8000";
const PASSWORD = process.env.SITEGUARD_DEMO_PASSWORD || "siteguard-demo";
const [OUT, PHASE] = process.argv.slice(2);
if (!OUT || !["before", "after"].includes(PHASE)) {
  console.error("usage: node capture_screens.cjs <out-dir> before|after");
  process.exit(2);
}

(async () => {
  const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  async function login(who) {
    await page.goto(BASE + "/app/login/");
    await page.evaluate(() => sessionStorage.clear());
    await page.getByLabel("Email").fill(`${who}@demo.siteguard.local`);
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();
    await page.waitForURL((u) => !u.pathname.includes("/login"));
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(800);
  }
  await login("pm");
  if (PHASE === "before") {
    await page.screenshot({ path: path.join(OUT, "1-dashboard-before.png"), fullPage: true });
  } else {
    await page.screenshot({ path: path.join(OUT, "2-dashboard-after.png"), fullPage: true });
    await page.getByRole("link", { name: "Incidents" }).first().click();
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(800);
    await page.screenshot({ path: path.join(OUT, "3-incidents-all-closed.png"), fullPage: true });
    await page.getByText("Worker fell from mobile scaffold tower").first().click();
    await page.waitForURL(/\/incident\/\?id=/);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1200);
    await page.screenshot({ path: path.join(OUT, "4-incident-ai-investigation-closed.png"), fullPage: true });
    await login("auditor");
    await page.getByRole("link", { name: "Audit", exact: true }).click();
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1200);
    await page.screenshot({ path: path.join(OUT, "10-audit-trail.png") });
  }
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
