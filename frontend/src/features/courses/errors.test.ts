import { describe, expect, it } from "vitest";

import {
  tryExtractContentHashFromDetail,
  tryExtractExistingFilenameFromDetail,
} from "./errors";

describe("courses/errors detail extractors", () => {
  it("extracts existing filename from current FastAPI string detail format", () => {
    const detail =
      "This file was already uploaded for this course (existing filename: Lecture1.docx)";
    expect(tryExtractExistingFilenameFromDetail(detail)).toBe("Lecture1.docx");
  });

  it("extracts existing filename even if parentheses are missing", () => {
    const detail = "Duplicate upload. existing filename: Lecture2.pptx";
    expect(tryExtractExistingFilenameFromDetail(detail)).toBe("Lecture2.pptx");
  });

  it("extracts existing filename from structured detail object", () => {
    const detail = {
      code: "COURSE_FILE_DUPLICATE",
      message: "File already uploaded",
      existing_filename: "Lecture3.pdf",
      content_hash: "ab".repeat(32),
    };
    expect(tryExtractExistingFilenameFromDetail(detail)).toBe("Lecture3.pdf");
  });

  it("extracts content hash from structured detail object", () => {
    const detail = { content_hash: "ab".repeat(32) };
    expect(tryExtractContentHashFromDetail(detail)).toBe("ab".repeat(32));
  });

  it("returns undefined when no match", () => {
    expect(tryExtractExistingFilenameFromDetail("nope")).toBeUndefined();
    expect(tryExtractExistingFilenameFromDetail({})).toBeUndefined();
    expect(tryExtractContentHashFromDetail("nope")).toBeUndefined();
  });
});


