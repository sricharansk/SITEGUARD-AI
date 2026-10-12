import { expect, Page, test } from "@playwright/test";

const PASSWORD = process.env.DEMO_PASSWORD ?? "siteguard-demo";
const SHOTS = process.env.SCREENSHOT_DIR;

async function shot(page: Page, name: string) {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true });
}

async function open(page: Page, url: string, title: string) {
  await page.goto(url);
  await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
  await expect(page.getByText(/Corrective and preventive actions/)).toBeVisible();
}

async function loginAs(page: Page, who: string) {
  await page.goto("/app/login/");
  await page.evaluate(() => sessionStorage.clear());
  await page.getByLabel("Email").fill(`${who}@demo.siteguard.local`);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((u) => !u.pathname.includes("/login"));
  await expect(page.getByText("Incidents by status")).toBeVisible();
}

test("report, investigate, review, work, verify and close an incident in the browser", async ({ page }) => {
  const title = "Electrician fell from unsecured stepladder in plant room";

  // Site engineer reports the incident.
  await loginAs(page, "site");
  await page.getByRole("link", { name: "Report incident" }).first().click();
  await page.getByLabel("Title").fill(title);
  await page
    .getByLabel("What happened")
    .fill("An electrician fell about 1.8 m from a stepladder that was not secured. He was not using the platform guardrail and went to hospital with a suspected fracture.");
  await page.getByLabel("Severity (your assessment)").selectOption("HIGH");
  await page.getByLabel("Exact location").fill("Level 3 plant room");
  await page.getByLabel("People involved").fill("1");
  await page.getByLabel("Immediate actions taken").fill("First aid, area barricaded, ladder quarantined.");
  await page.getByRole("button", { name: "Report incident" }).click();
  await page.waitForURL(/\/incident\/\?id=/);
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  const url = page.url();

  // Site engineers cannot run the agents.
  await expect(page.getByRole("button", { name: /Run AI investigation/ })).toHaveCount(0);

  // Safety engineer runs the AI investigation.
  await loginAs(page, "safety");
  await open(page, url, title);
  await page.getByRole("button", { name: "Run AI investigation" }).click();
  await expect(page.getByLabel("Triage (AI-generated)")).toBeVisible();
  await expect(page.getByText("Fall from height").first()).toBeVisible();
  await expect(page.getByText("Risk (deterministic 5×5 matrix)")).toBeVisible();
  await expect(page.getByText("Pending approval").first()).toBeVisible();
  await shot(page, "02-incident-ai-investigation");

  // Project manager cannot approve critical (high-risk) actions.
  await loginAs(page, "pm");
  await open(page, url, title);
  await expect(page.getByText(/Awaiting review by the HSE manager/).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve" })).toHaveCount(0);

  // HSE manager approves every proposal with a reason.
  await loginAs(page, "hse");
  await open(page, url, title);
  while ((await page.getByRole("button", { name: "Approve", exact: true }).count()) > 0) {
    await page.getByRole("button", { name: "Approve", exact: true }).first().click();
    await page.getByLabel(/Reason for approve/).fill("Proportionate; matches site conditions.");
    const before = await page.getByRole("button", { name: "Approve", exact: true }).count();
    await page.getByRole("button", { name: "Confirm approve" }).click();
    await expect(page.getByRole("button", { name: "Approve", exact: true })).toHaveCount(before - 1);
  }
  await expect(page.getByText("Action in progress").first()).toBeVisible();

  // Site engineer completes the work.
  await loginAs(page, "site");
  await open(page, url, title);
  while ((await page.getByRole("button", { name: "Mark completed" }).count()) > 0) {
    const before = await page.getByRole("button", { name: "Mark completed" }).count();
    await page.getByRole("button", { name: "Mark completed" }).first().click();
    await expect(page.getByRole("button", { name: "Mark completed" })).toHaveCount(before - 1);
  }
  await expect(page.getByText("Pending verification").first()).toBeVisible();

  // Safety engineer verifies (someone other than the person who did the work).
  await loginAs(page, "safety");
  await open(page, url, title);
  while ((await page.getByRole("button", { name: "Verify", exact: true }).count()) > 0) {
    await page.getByRole("button", { name: "Verify", exact: true }).first().click();
    await page.getByLabel("What you checked").fill("Checked on site; ladder secured and platform guardrail in use.");
    const before = await page.getByRole("button", { name: "Verify", exact: true }).count();
    await page.getByRole("button", { name: "Record verification" }).click();
    await expect(page.getByRole("button", { name: "Verify", exact: true })).toHaveCount(before - 1);
  }

  // Project manager closes it.
  await loginAs(page, "pm");
  await open(page, url, title);
  await page.getByLabel("Closure note").fill("All actions verified effective; lessons shared.");
  await page.getByRole("button", { name: "Close incident" }).click();
  await expect(page.getByText(/Closed .* after every approved action was verified effective/)).toBeVisible();
  await shot(page, "03-incident-closed");
});

test("dashboard, incident list, action queue, knowledge and audit render", async ({ page }) => {
  await loginAs(page, "hse");
  await expect(page.getByText("Incidents by status")).toBeVisible();
  await expect(page.getByText("Top hazards and defects (AI triage)")).toBeVisible();
  await shot(page, "01-dashboard");
  await page.getByRole("link", { name: "Incidents", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Incidents" })).toBeVisible();
  await expect(page.locator("tbody tr").first()).toBeVisible();
  await shot(page, "04-incident-list");
  await page.getByRole("link", { name: "Actions", exact: true }).click();
  await page.getByRole("tab", { name: "Assigned to me" }).click();
  await page.getByRole("tab", { name: "Awaiting review" }).click();
  await expect(page.locator("tbody tr").first()).toBeVisible(); // the queue is not overwritten by the other tab
  await shot(page, "05-action-queue");
  await page.getByRole("link", { name: "Knowledge", exact: true }).click();
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.getByText(/Results \(\d+\)/)).toBeVisible();
  await shot(page, "06-knowledge-search");
  await loginAs(page, "auditor");
  await page.getByRole("link", { name: "Audit", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Audit trail" })).toBeVisible();
  await expect(page.locator("tbody tr").first()).toBeVisible();
});

test("a user from another tenant cannot open this tenant's incidents", async ({ page }) => {
  await loginAs(page, "hse");
  await page.getByRole("link", { name: "Incidents", exact: true }).click();
  await page.locator("tbody tr a").first().click();
  await page.waitForURL(/\/incident\/\?id=/);
  const url = page.url();
  await loginAs(page, "other");
  await page.goto(url);
  await expect(page.getByRole("alert").filter({ hasText: "NOT_FOUND" })).toBeVisible();
});
