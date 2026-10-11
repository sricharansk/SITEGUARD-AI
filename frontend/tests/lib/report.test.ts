// Report download through the BFF: the request carries the format and include_ai choice, the file keeps its bytes,
// name and audited SHA-256, and errors arrive as ApiError with the API's code and correlation ID.
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, downloadReport, filenameFromDisposition, reportPath, setUnauthenticatedHandler } from "@/lib/api";
import { errorEnvelopeResponse } from "../fixtures";

describe("filenameFromDisposition", () => {
  it.each([
    ['attachment; filename="SG-2026-0001-report.pdf"', "SG-2026-0001-report.pdf"],
    ["attachment; filename=SG-2026-0001-report.md", "SG-2026-0001-report.md"],
    ["attachment; filename*=UTF-8''SG%20report.docx", "SG report.docx"],
    ['attachment; filename="../../etc/passwd"', "passwd"],
    ['attachment; filename="C:\\temp\\x.pdf"', "x.pdf"],
  ])("reads %s", (header, expected) => {
    expect(filenameFromDisposition(header)).toBe(expected);
  });

  it("returns null when there is no usable name", () => {
    expect(filenameFromDisposition(null)).toBeNull();
    expect(filenameFromDisposition("inline")).toBeNull();
    expect(filenameFromDisposition('attachment; filename=""')).toBeNull();
  });
});

describe("downloadReport", () => {
  afterEach(() => {
    setUnauthenticatedHandler(() => undefined);
  });

  it("asks for the chosen format and AI option and keeps the bytes, name and SHA-256", async () => {
    const bytes = new Uint8Array([0x50, 0x4b, 0x03, 0x04, 0x00, 0xff, 0x10]);
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(bytes, {
        headers: {
          "content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
          "content-disposition": 'attachment; filename="SG-2026-0007-report.docx"',
          "x-report-sha256": "ab".repeat(32),
        },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const file = await downloadReport("inc/1", "docx", false);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/backend/incidents/inc%2F1/report?format=docx&include_ai=false");
    expect(init.credentials).toBe("same-origin");
    expect(file.filename).toBe("SG-2026-0007-report.docx");
    expect(file.sha256).toBe("ab".repeat(32));
    expect(new Uint8Array(await file.blob.arrayBuffer())).toEqual(bytes);
  });

  it("falls back to a generic name when the header is missing", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("# Report", { headers: { "content-type": "text/markdown" } })));
    const file = await downloadReport("i1", "md", true);
    expect(file.filename).toBe("incident-report.md");
    expect(file.sha256).toBeNull();
    expect(reportPath("i1", "md", true)).toBe("/incidents/i1/report?format=md&include_ai=true");
  });

  it("throws the API's error envelope as ApiError", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(errorEnvelopeResponse(404, "NOT_FOUND", "Incident not found", "cid-report-404")));
    const error = (await downloadReport("other-tenant", "pdf", true).catch((e: unknown) => e)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(404);
    expect(error.code).toBe("NOT_FOUND");
    expect(error.correlationId).toBe("cid-report-404");
  });

  it("sends a 401 to the sign-in handler", async () => {
    const handler = vi.fn();
    setUnauthenticatedHandler(handler);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(errorEnvelopeResponse(401, "UNAUTHENTICATED", "Sign in.")));
    await expect(downloadReport("i1", "pdf", true)).rejects.toBeInstanceOf(ApiError);
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("maps a network failure to NETWORK_ERROR", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const error = (await downloadReport("i1", "pdf", true).catch((e: unknown) => e)) as ApiError;
    expect(error.code).toBe("NETWORK_ERROR");
  });
});
