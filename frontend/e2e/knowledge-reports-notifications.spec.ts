// Browser E2E for the knowledge, report, notification and dashboard screens (Prompts 24, 31-34): a grounded answer
// with citations, document upload with processing status and search provenance, an incident report download whose
// bytes match the audited SHA-256, in-app notifications with mark read, the administrator's delivery outbox, and the
// dashboard filters. Needs the API with demo data (rules provider) and the web app running (frontend/README.md).
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";

const PASSWORD = process.env.E2E_PASSWORD || "siteguard-demo";
const HSE = "hse@demo.siteguard.local";
const PM = "pm@demo.siteguard.local";
const ADMIN = "admin@demo.siteguard.local";

async function signIn(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Project dashboard" })).toBeVisible();
}

/** Writes through the BFF need a same-origin Origin header, exactly as the browser sends it. */
function origin(page: Page) {
  return { origin: new URL(page.url()).origin };
}

async function firstProject(page: Page): Promise<{ id: string; organization_id: string }> {
  const res = await page.request.get("/api/backend/projects");
  expect(res.ok()).toBeTruthy();
  const body = (await res.json()) as { data: { id: string; organization_id: string }[] };
  return body.data[0]!;
}

/** Report a CRITICAL incident through the BFF as the signed-in user; returns its id. */
async function reportCriticalIncident(page: Page, title: string): Promise<string> {
  const project = await firstProject(page);
  const res = await page.request.post(`/api/backend/projects/${project.id}/incidents`, {
    headers: origin(page),
    data: {
      title,
      description: "Trench wall collapsed next to an open excavation while two workers were inside. No injury.",
      domain: "SAFETY",
      severity: "CRITICAL",
      occurred_at: new Date().toISOString(),
      location: "Basement grid C4",
    },
  });
  expect(res.status()).toBe(201);
  return ((await res.json()) as { data: { id: string } }).data.id;
}

test("grounded answer with citations, document upload and search provenance", async ({ page }) => {
  await signIn(page, HSE);
  await page.getByRole("link", { name: "Knowledge", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Knowledge" })).toBeVisible();

  // Ask: the answer is labelled AI decision support and cites title, version and section.
  const ask = page.getByRole("form", { name: "Ask a question" });
  await ask.getByLabel("Question").fill("How deep can an excavation be before shoring or a trench box is required?");
  await ask.getByRole("button", { name: "Get grounded answer" }).click();
  const answer = page.getByRole("region", { name: "AI output: Grounded answer" });
  await expect(answer).toBeVisible();
  await expect(answer).toHaveAttribute("data-status", "ANSWERED");
  await expect(answer.getByText("AI decision support, needs human review", { exact: true })).toBeVisible();
  await expect(answer.getByText("Answered from cited sources", { exact: true })).toBeVisible();
  await expect(answer.getByRole("list", { name: "Answer statements" })).toContainText("1.2 metres");
  const citation = answer.getByTestId("answer-citation").first();
  await expect(citation).toContainText("Excavation and Trenching Procedure (HSE-PRO-007) · v2");
  await expect(citation).toContainText("section Protective systems");

  // An unanswerable question says so instead of inventing an answer.
  await ask.getByLabel("Question").fill("What is the canteen menu on Fridays?");
  await ask.getByRole("button", { name: "Get grounded answer" }).click();
  await expect(answer).toHaveAttribute("data-status", "INSUFFICIENT_EVIDENCE");
  await expect(answer.getByText("Insufficient evidence", { exact: true })).toBeVisible();

  // Upload a Markdown procedure: the API parses and indexes it in the request and reports its status.
  const stamp = Date.now();
  const title = `E2E Hoarding Inspection Procedure ${stamp}`;
  await page.getByRole("button", { name: "Upload a file" }).click();
  const upload = page.getByRole("form", { name: "Upload a document" });
  await upload.getByLabel("Document file").setInputFiles({
    name: "hoarding-inspection.md",
    mimeType: "text/markdown",
    buffer: Buffer.from(
      `# Hoarding inspection\n\n## Daily checks\nInspect every hoarding panel zx${stamp} for loose clamps each morning and record it.\n`,
      "utf-8",
    ),
  });
  await upload.getByLabel("Title").fill(title);
  await upload.getByLabel("Source (where the official copy lives)").fill("E2E test");
  await upload.getByLabel("Version").fill("7");
  await upload.getByRole("button", { name: "Upload document" }).click();
  const result = upload.getByTestId("upload-result");
  await expect(result).toContainText("Ready");
  await expect(result).toContainText(title);
  await expect(page.getByRole("table", { name: "Documents" }).getByRole("row").filter({ hasText: title })).toContainText("Ready");

  // Search finds it and shows version, page and section.
  const search = page.getByRole("search");
  await search.getByLabel("Search text").fill(`zx${stamp}`);
  await search.getByRole("button", { name: "Search", exact: true }).click();
  const hit = page.getByTestId("search-hit").filter({ hasText: title });
  await expect(hit).toHaveCount(1);
  const details = hit.getByLabel("Source details");
  await expect(details).toContainText("Versionv7");
  await expect(details).toContainText("Page—");
  await expect(details).toContainText("Daily checks");
  await expect(details).toContainText("This project");
});

test("incident report downloads with the audited SHA-256", async ({ page }) => {
  await signIn(page, HSE);
  const id = await reportCriticalIncident(page, `E2E report download ${Date.now()}`);
  await page.goto(`/incidents/${id}#report`);
  const report = page.getByRole("form", { name: "Download incident report" });
  await expect(report).toBeVisible();
  await report.getByLabel("Format").selectOption("md");
  await expect(report.getByRole("checkbox", { name: /Include the AI analysis/ })).toBeChecked();

  const [download] = await Promise.all([page.waitForEvent("download"), report.getByRole("button", { name: "Download report" }).click()]);
  expect(download.suggestedFilename()).toMatch(/^SG-\d{4}-\d{4}-report\.md$/);
  const path = await download.path();
  const bytes = await readFile(path);
  expect(bytes.toString("utf-8")).toContain("# Incident report SG-");
  expect(bytes.toString("utf-8")).toContain("decision support");

  await expect(report.getByTestId("report-result")).toContainText(`Downloaded ${download.suggestedFilename()}`);
  const shown = (await report.getByTestId("report-sha256").innerText()).trim();
  expect(shown).toMatch(/^[0-9a-f]{64}$/);
  expect(createHash("sha256").update(bytes).digest("hex")).toBe(shown);
});

test("notifications: a critical incident reaches the HSE manager, who marks it read", async ({ page, browser }) => {
  const title = `E2E trench collapse ${Date.now()}`;
  // The project manager reports a CRITICAL incident; HSE managers (APPROVE_CRITICAL) are notified.
  const pmContext = await browser.newContext();
  const pmPage = await pmContext.newPage();
  await signIn(pmPage, PM);
  await reportCriticalIncident(pmPage, title);
  // The project manager cannot see the email outbox (no organization-wide VIEW_AUDIT).
  await pmPage.goto("/notifications");
  await expect(pmPage.getByRole("heading", { level: 1, name: "Notifications" })).toBeVisible();
  await expect(pmPage.getByRole("heading", { name: /^Your notifications/ })).toBeVisible();
  await expect(pmPage.getByTestId("delivery-outbox")).toHaveCount(0);
  await pmContext.close();

  await signIn(page, HSE);
  const bell = page.getByTestId("notification-bell");
  await expect(bell).toHaveAccessibleName(/^Notifications, \d+ unread$/);
  await bell.click();
  await expect(page.getByRole("heading", { level: 1, name: "Notifications" })).toBeVisible();
  const item = page.getByTestId("notification").filter({ hasText: title });
  await expect(item).toHaveCount(1);
  await expect(item).toContainText("CRITICAL");
  await expect(item.getByText("Unread", { exact: true })).toBeVisible();
  await expect(item.getByRole("link", { name: "Open incident" })).toBeVisible();

  await item.getByRole("button", { name: "Mark as read" }).click();
  await expect(page.getByText("Marked as read.", { exact: true })).toBeVisible();
  await expect(item.getByRole("button", { name: "Mark as read" })).toHaveCount(0);

  await page.getByRole("button", { name: "Mark all as read" }).click();
  await expect(page.getByText("All notifications marked as read.", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Your notifications (0 unread)" })).toBeVisible();
  await expect(bell).toHaveAccessibleName("Notifications, none unread");
});

test("administrator sees the delivery outbox and retries a skipped delivery", async ({ page }) => {
  await signIn(page, ADMIN);
  const project = await firstProject(page);
  // Run the scheduled job once: with external email turned off (the default), due deliveries become SKIPPED.
  const run = await page.request.post(`/api/backend/notifications/run?organization_id=${project.organization_id}`, {
    headers: origin(page),
  });
  expect(run.ok()).toBeTruthy();

  await page.goto("/notifications");
  const outbox = page.getByTestId("delivery-outbox");
  await expect(outbox).toBeVisible();
  await outbox.getByLabel("Delivery status").selectOption("SKIPPED");
  const skipped = outbox.getByTestId("delivery").first();
  await expect(skipped).toContainText("Skipped (delivery off)");
  await skipped.getByRole("button", { name: /^Retry delivery of / }).click();
  await expect(outbox.getByText(/queued again\.$/)).toBeVisible();
});

test("dashboard filters validate the range and update every metric", async ({ page }) => {
  await signIn(page, HSE);
  const filters = page.getByRole("form", { name: "Dashboard filters" });
  await expect(page.getByTestId("dashboard-scope")).toContainText("on any date");
  await expect(page.getByRole("heading", { name: /^Response and closure trend/ })).toBeVisible();

  await filters.getByLabel("From").fill("2026-05-01");
  await filters.getByLabel("To").fill("2026-04-30");
  await filters.getByRole("button", { name: "Apply filters" }).click();
  await expect(filters.getByRole("alert")).toHaveText("From must be on or before To.");
  await expect(page.getByTestId("dashboard-scope")).toContainText("on any date");

  await filters.getByLabel("From").fill("2020-01-01");
  await filters.getByLabel("To").fill("2030-12-31");
  await filters.getByLabel("Trend by").selectOption("week");
  await filters.getByRole("button", { name: "Apply filters" }).click();
  await expect(filters.getByRole("alert")).toHaveCount(0);
  await expect(page.getByTestId("dashboard-scope")).toContainText(/2020 – .*2030/);
  await expect(page.getByTestId("dashboard-scope")).toContainText("trend by ISO week");
  await expect(page.getByRole("heading", { name: "Response and closure trend (by ISO week occurred)" })).toBeVisible();
  await expect(page.getByRole("term").filter({ hasText: /^Median first response$/ })).toBeVisible();
});
