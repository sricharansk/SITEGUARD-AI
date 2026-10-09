// End-to-end acceptance in a real browser (Playwright Prompt 48): an HSE manager reports an incident, attaches
// evidence, runs the AI investigation and approves a proposed action; an auditor then sees the same incident
// read-only, with no approve control. Needs the API with demo data and the web app running (README).
import { expect, test, type Page } from "@playwright/test";

const PASSWORD = process.env.E2E_PASSWORD || "siteguard-demo";
const HSE = "hse@demo.siteguard.local";
const AUDITOR = "auditor@demo.siteguard.local";

async function signIn(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Project dashboard" })).toBeVisible();
}

test("incident to AI investigation to human approval, and auditor is read-only", async ({ page }) => {
  const title = `E2E guardrail removed at slab edge ${Date.now()}`;

  // 1. Sign in as the HSE manager and report an incident.
  await signIn(page, HSE);
  await page.getByRole("link", { name: "Report incident" }).click();
  await expect(page.getByRole("heading", { level: 1, name: /Report an incident/ })).toBeVisible();
  await page.getByLabel("Title (required)").fill(title);
  await page
    .getByLabel("What happened (required)")
    .fill(
      "A section of guardrail at the level 9 slab edge was removed for crane access and not reinstated. " +
        "A worker stepped near the open edge without a harness. Near miss, no injury.",
    );
  await page.getByLabel("Domain").selectOption("SAFETY");
  await page.getByLabel("Reported severity").selectOption("HIGH");
  await page.getByLabel("Location on site").fill("Level 9, north edge");
  await page.getByLabel("Activity under way").fill("Formwork stripping");
  await page.getByRole("button", { name: "Save incident" }).click();

  await page.waitForURL(/\/incidents\/[0-9a-f-]{36}$/);
  const incidentUrl = page.url();
  await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
  await expect(page.getByRole("list", { name: "Incident lifecycle" })).toContainText("Reported");

  // 2. Upload a small text evidence file.
  const evidence = page.locator("#evidence");
  await evidence.getByLabel("Evidence file").setInputFiles({
    name: "supervisor-note.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("Supervisor note: guardrail removed at 09:40 for crane access; not reinstated.\n", "utf-8"),
  });
  await evidence.getByLabel("Description (optional)").fill("Supervisor statement");
  await evidence.getByRole("button", { name: "Upload evidence" }).click();
  await expect(evidence.getByRole("link", { name: "supervisor-note.txt", exact: true })).toBeVisible();
  await expect(evidence.getByText("SHA-256", { exact: true })).toBeVisible();

  // 3. Run the AI investigation: staged progress, then labelled AI panels.
  await page.getByRole("button", { name: "Run AI investigation" }).click();
  await expect(page.getByTestId("investigation-progress")).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: /AI investigation finished: \d+ agent run/ })).toBeVisible({
    timeout: 120_000,
  });

  const triage = page.getByRole("region", { name: "AI output: Triage" });
  await expect(triage).toBeVisible();
  await expect(triage.getByText("AI decision support, needs human review")).toBeVisible();
  await expect(triage.getByText(/Provider: /)).toBeVisible();
  await expect(triage.getByText(/Confidence \d+%/)).toBeVisible();
  await expect(page.getByRole("region", { name: "AI output: Safety investigation" })).toBeVisible();
  await expect(page.getByRole("region", { name: /AI output: Corrective and preventive action proposals/ })).toBeVisible();
  await expect(page.getByRole("list", { name: "Incident lifecycle" }).locator('[aria-current="step"]')).toContainText(
    "Pending approval",
  );

  // 4. Approve the first proposed action with a reason.
  const pending = page
    .getByTestId("capa-action")
    .filter({ has: page.getByRole("button", { name: "Approve", exact: true }) })
    .first();
  const actionTitle = (await pending.getByRole("heading", { level: 3 }).innerText()).trim();
  await pending.getByLabel("Review reason (required)").fill("Control is appropriate for the hazard; approved.");
  await pending.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(page.getByText(`“${actionTitle}” approved.`)).toBeVisible();
  const approved = page
    .getByTestId("capa-action")
    .filter({ has: page.getByRole("heading", { level: 3, name: actionTitle, exact: true }) });
  await expect(approved.getByText("Approved", { exact: true })).toBeVisible();
  await expect(approved.getByText(/Approved by Hana Safety/)).toBeVisible();

  // 5. Sign out and sign in as the auditor: read-only, no approve button.
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login/);
  await signIn(page, AUDITOR);
  await page.goto(incidentUrl);
  await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
  await expect(page.getByRole("region", { name: "AI output: Triage" })).toBeVisible();
  await expect(page.getByTestId("capa-action").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Run AI investigation/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Upload evidence" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Audit log" })).toBeVisible();

  // The server stays the authority: a page the auditor cannot use shows the unauthorized state.
  await page.goto("/incidents/new");
  await expect(page.getByText("Not authorized")).toBeVisible();
});
