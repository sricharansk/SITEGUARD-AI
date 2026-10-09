// The report download asks the API for the chosen format and AI option, hands the file to the browser unchanged and
// shows the SHA-256 recorded in the audit log; errors keep the API's code and correlation ID.
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ReportDownload } from "@/components/incident/report-download";
import type { DownloadedFile } from "@/lib/api";
import { INCIDENT_ID, errorEnvelopeResponse } from "../fixtures";

const SHA = "c".repeat(64);

let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

function reportResponse(name: string, body = "%PDF-1.7") {
  return new Response(body, {
    headers: { "content-type": "application/pdf", "content-disposition": `attachment; filename="${name}"`, "x-report-sha256": SHA },
  });
}

describe("ReportDownload", () => {
  it("downloads a PDF with the AI analysis by default and shows the audited SHA-256", async () => {
    fetchMock.mockResolvedValue(reportResponse("SG-2026-0001-report.pdf"));
    const save = vi.fn<(file: DownloadedFile) => void>();
    render(<ReportDownload incidentId={INCIDENT_ID} save={save} />);
    expect(screen.getByRole("combobox", { name: "Format" })).toHaveValue("pdf");
    expect(screen.getByRole("checkbox", { name: /Include the AI analysis/ })).toBeChecked();
    expect(screen.getByText(/AI sections are decision support that needs human review/)).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Download report" }));
    const result = await screen.findByTestId("report-result");
    expect(fetchMock.mock.calls[0]![0]).toBe(`/api/backend/incidents/${INCIDENT_ID}/report?format=pdf&include_ai=true`);
    expect(save).toHaveBeenCalledTimes(1);
    const file = save.mock.calls[0]![0];
    expect(file.filename).toBe("SG-2026-0001-report.pdf");
    expect(await file.blob.text()).toBe("%PDF-1.7");
    expect(result).toHaveTextContent("Downloaded SG-2026-0001-report.pdf (with labelled AI analysis).");
    expect(screen.getByTestId("report-sha256")).toHaveTextContent(SHA);
  });

  it("sends the chosen format and leaves the AI analysis out when unticked", async () => {
    fetchMock.mockResolvedValue(reportResponse("SG-2026-0001-report.md", "# Report"));
    const save = vi.fn();
    render(<ReportDownload incidentId={INCIDENT_ID} save={save} />);
    fireEvent.change(screen.getByRole("combobox", { name: "Format" }), { target: { value: "md" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /Include the AI analysis/ }));
    expect(screen.queryByText(/AI sections are decision support/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Download report" }));
    expect(await screen.findByTestId("report-result")).toHaveTextContent("Downloaded SG-2026-0001-report.md (without AI analysis).");
    expect(fetchMock.mock.calls[0]![0]).toBe(`/api/backend/incidents/${INCIDENT_ID}/report?format=md&include_ai=false`);
  });

  it("shows the API's error and saves nothing", async () => {
    fetchMock.mockResolvedValue(errorEnvelopeResponse(404, "NOT_FOUND", "Incident not found.", "cid-report-nf"));
    const save = vi.fn();
    render(<ReportDownload incidentId="other-tenant" save={save} />);
    fireEvent.click(screen.getByRole("button", { name: "Download report" }));
    expect(await screen.findByText(/Incident not found\./)).toBeVisible();
    expect(screen.getByText(/cid-report-nf/)).toBeVisible();
    expect(save).not.toHaveBeenCalled();
    expect(screen.queryByTestId("report-result")).toBeNull();
  });
});
