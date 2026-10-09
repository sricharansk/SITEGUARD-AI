// Document upload: the browser checks type and size as a courtesy, posts multipart to /documents/upload with the
// project scope, and shows the processing status the API returns (ready, failed with reason, or duplicate).
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MAX_DOCUMENT_BYTES, ProcessingResult, UploadDocumentForm, checkDocumentFile } from "@/components/knowledge/upload-form";
import type { KnowledgeDocument, Project } from "@/lib/types";
import { envelopeResponse, errorEnvelopeResponse } from "../fixtures";

const PROJECT: Project = {
  id: "p1",
  organization_id: "o1",
  code: "TWR-A",
  name: "Tower A",
  client: null,
  location: null,
  sites: [],
  permissions: ["READ", "MANAGE_DOCUMENTS"],
};

function makeDocument(overrides: Partial<KnowledgeDocument> = {}): KnowledgeDocument {
  return {
    id: "doc-1",
    organization_id: "o1",
    project_id: "p1",
    scope: "project",
    title: "Lifting plan",
    doc_type: "PROCEDURE",
    source: "Site QMS",
    version: "3",
    effective_date: null,
    tags: [],
    domain: "SAFETY",
    status: "READY",
    error: null,
    file_name: "lifting-plan.md",
    content_type: "text/markdown",
    size_bytes: 120,
    page_count: null,
    parser: "markdown",
    chunks: 4,
    suspicious_chunks: 0,
    sha256: "d".repeat(64),
    processed_at: "2026-10-09T08:00:00",
    created_at: "2026-10-09T08:00:00",
    ...overrides,
  };
}

let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

function chooseFile(file: File) {
  fireEvent.change(screen.getByLabelText("Document file"), { target: { files: [file] } });
}

describe("checkDocumentFile", () => {
  it("accepts the supported types and rejects others, empty and oversized files", () => {
    expect(checkDocumentFile({ name: "Plan.PDF", size: 10 })).toBeNull();
    expect(checkDocumentFile({ name: "notes.md", size: 10 })).toBeNull();
    expect(checkDocumentFile({ name: "virus.exe", size: 10 })).toMatch(/Allowed file types/);
    expect(checkDocumentFile({ name: "noext", size: 10 })).toMatch(/Allowed file types/);
    expect(checkDocumentFile({ name: "a.txt", size: 0 })).toBe("The file is empty.");
    expect(checkDocumentFile({ name: "a.txt", size: MAX_DOCUMENT_BYTES + 1 })).toMatch(/larger than/);
  });
});

describe("UploadDocumentForm", () => {
  it("posts the file as multipart with the project scope and shows the ready status", async () => {
    const onUploaded = vi.fn();
    fetchMock.mockResolvedValue(envelopeResponse(makeDocument()));
    render(<UploadDocumentForm project={PROJECT} canUseOrganizationScope={false} onUploaded={onUploaded} />);
    expect(screen.queryByRole("option", { name: "Whole organization" })).toBeNull();
    chooseFile(new File(["# Lifting plan\n\nUse tag lines."], "lifting-plan.md", { type: "text/markdown" }));
    expect(screen.getByLabelText("Title")).toHaveValue("lifting plan");
    fireEvent.change(screen.getByLabelText("Source (where the official copy lives)"), { target: { value: "Site QMS" } });
    fireEvent.change(screen.getByLabelText("Version"), { target: { value: "3" } });
    fireEvent.click(screen.getByRole("button", { name: "Upload document" }));

    const result = await screen.findByTestId("upload-result");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/backend/documents/upload");
    expect(init.method).toBe("POST");
    const body = init.body as FormData;
    expect(body).toBeInstanceOf(FormData);
    expect((body.get("file") as File).name).toBe("lifting-plan.md");
    expect(body.get("organization_id")).toBe("o1");
    expect(body.get("project_id")).toBe("p1");
    expect(body.get("version")).toBe("3");
    expect(result).toHaveTextContent("Processing status: Ready");
    expect(result).toHaveTextContent("indexed 4 section chunk(s)");
    expect(onUploaded).toHaveBeenCalledWith(expect.objectContaining({ id: "doc-1" }));
  });

  it("offers the organization scope only when allowed and then omits the project", async () => {
    fetchMock.mockResolvedValue(envelopeResponse(makeDocument({ project_id: null, scope: "organization" })));
    render(<UploadDocumentForm project={PROJECT} canUseOrganizationScope onUploaded={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Visible to"), { target: { value: "organization" } });
    chooseFile(new File(["text"], "policy.txt", { type: "text/plain" }));
    fireEvent.change(screen.getByLabelText("Source (where the official copy lives)"), { target: { value: "HQ" } });
    fireEvent.click(screen.getByRole("button", { name: "Upload document" }));
    await screen.findByTestId("upload-result");
    const body = (fetchMock.mock.calls[0] as [string, RequestInit])[1].body as FormData;
    expect(body.get("project_id")).toBeNull();
  });

  it("stops before the API when the file or fields are missing or the type is not allowed", () => {
    render(<UploadDocumentForm project={PROJECT} canUseOrganizationScope={false} onUploaded={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Upload document" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Choose a file to upload.");
    chooseFile(new File(["MZ"], "tool.exe"));
    fireEvent.click(screen.getByRole("button", { name: "Upload document" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/Allowed file types/);
    chooseFile(new File(["text"], "note.txt"));
    fireEvent.click(screen.getByRole("button", { name: "Upload document" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Title, document type and source are required.");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows the API's refusal", async () => {
    fetchMock.mockResolvedValue(errorEnvelopeResponse(415, "UNSUPPORTED_MEDIA_TYPE", "The file content does not match its type.", "cid-up-415"));
    render(<UploadDocumentForm project={PROJECT} canUseOrganizationScope={false} onUploaded={vi.fn()} />);
    chooseFile(new File(["text"], "note.txt"));
    fireEvent.change(screen.getByLabelText("Source (where the official copy lives)"), { target: { value: "QMS" } });
    fireEvent.click(screen.getByRole("button", { name: "Upload document" }));
    expect(await screen.findByText(/does not match its type/)).toBeVisible();
    expect(screen.queryByTestId("upload-result")).toBeNull();
  });
});

describe("ProcessingResult", () => {
  it("explains a failed parse and that the original is kept", () => {
    render(<ProcessingResult doc={makeDocument({ status: "FAILED", error: "No text layer (scanned PDF?)", chunks: 0 })} />);
    const result = screen.getByTestId("upload-result");
    expect(result).toHaveTextContent("Processing status: Failed");
    expect(result).toHaveTextContent("Processing failed: No text layer (scanned PDF?). The original file is kept");
  });

  it("says a duplicate added nothing", () => {
    render(<ProcessingResult doc={makeDocument({ duplicate: true })} />);
    expect(screen.getByTestId("upload-result")).toHaveTextContent("Already in the library with the same content, version and scope.");
  });

  it("warns about instruction-like chunks", () => {
    render(<ProcessingResult doc={makeDocument({ suspicious_chunks: 2, page_count: 3 })} />);
    expect(screen.getByTestId("upload-result")).toHaveTextContent("Parsed 3 page(s)");
    expect(screen.getByTestId("upload-result")).toHaveTextContent("2 chunk(s) contain instruction-like text and are never cited.");
  });
});
