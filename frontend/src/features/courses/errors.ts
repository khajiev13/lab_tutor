export class CourseFileDuplicateError extends Error {
  readonly existingFilename?: string;
  readonly contentHash?: string;

  constructor(message: string, opts?: { existingFilename?: string; contentHash?: string }) {
    super(message);
    this.name = "CourseFileDuplicateError";
    this.existingFilename = opts?.existingFilename;
    this.contentHash = opts?.contentHash;
  }
}

// Backend currently returns FastAPI default:
// { detail: "This file was already uploaded for this course (existing filename: <name>)" }
// We keep parsing minimal/robust; if it doesn't match, we just omit the hint.
export function tryExtractExistingFilenameFromDetail(detail: unknown): string | undefined {
  // Future-friendly: if backend switches to structured detail, support it without
  // forcing the UI to parse human strings.
  if (detail && typeof detail === "object") {
    const maybe = detail as Record<string, unknown>;
    const existing = maybe.existing_filename;
    if (typeof existing === "string" && existing.trim()) return existing.trim();
  }

  if (typeof detail !== "string") return undefined;

  // Common current format:
  // "... (existing filename: Lecture1.docx)"
  // but be tolerant to small differences (missing parens, extra suffix).
  const match = detail.match(/existing filename:\s*([^)]+?)(?:\s*\)|$)/i);
  const name = match?.[1]?.trim();
  return name ? name : undefined;
}

export function tryExtractContentHashFromDetail(detail: unknown): string | undefined {
  if (detail && typeof detail === "object") {
    const maybe = detail as Record<string, unknown>;
    const hash = maybe.content_hash;
    if (typeof hash === "string" && hash.trim()) return hash.trim();
  }
  return undefined;
}


