import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, type Mock } from "vitest";

import { CourseMaterialsTable } from "../components/CourseMaterialsTable";
import { presentationsApi } from "../features/courses/api";

vi.mock("../features/courses/api", () => ({
  presentationsApi: {
    list: vi.fn(),
    listStatuses: vi.fn(),
    delete: vi.fn(),
    deleteAll: vi.fn(),
  },
}));

describe("CourseMaterialsTable", () => {
  const courseId = 1;

  beforeEach(() => {
    vi.clearAllMocks();
    (presentationsApi.listStatuses as Mock).mockResolvedValue([]);
  });

  it("renders empty state when no files", async () => {
    (presentationsApi.list as Mock).mockResolvedValue([]);
    const onFilesChange = vi.fn();

    render(<CourseMaterialsTable courseId={courseId} onFilesChange={onFilesChange} />);

    await waitFor(() => {
      expect(screen.getByText("No presentations uploaded yet.")).toBeInTheDocument();
    });

    expect(onFilesChange).toHaveBeenCalledWith([]);
  });

  it("renders rows from both list + statuses (union)", async () => {
    (presentationsApi.list as Mock).mockResolvedValue(["lecture1.pdf"]);
    (presentationsApi.listStatuses as Mock).mockResolvedValue([
      {
        id: 10,
        course_id: courseId,
        filename: "status-only.pdf",
        blob_path: "blob",
        content_hash: null,
        uploaded_at: "2023-01-01T00:00:00Z",
        status: "processed",
        last_error: null,
        processed_at: "2023-01-02T00:00:00Z",
      },
    ]);

    render(<CourseMaterialsTable courseId={courseId} />);

    await waitFor(() => {
      expect(screen.getByText("lecture1.pdf")).toBeInTheDocument();
      expect(screen.getByText("status-only.pdf")).toBeInTheDocument();
    });

    // The status-only file should show a processed badge.
    expect(screen.getByText("Processed")).toBeInTheDocument();
  });

  it("deletes a file via confirmation dialog", async () => {
    (presentationsApi.list as Mock).mockResolvedValue(["lecture1.pdf"]);
    (presentationsApi.listStatuses as Mock).mockResolvedValue([
      {
        id: 10,
        course_id: courseId,
        filename: "lecture1.pdf",
        blob_path: "blob",
        content_hash: null,
        uploaded_at: "2023-01-01T00:00:00Z",
        status: "pending",
        last_error: null,
        processed_at: null,
      },
    ]);
    (presentationsApi.delete as Mock).mockResolvedValue(undefined);

    const onFilesChange = vi.fn();
    render(<CourseMaterialsTable courseId={courseId} onFilesChange={onFilesChange} />);

    await waitFor(() => {
      expect(screen.getByText("lecture1.pdf")).toBeInTheDocument();
    });

    const deleteTrigger = screen.getByLabelText("Delete lecture1.pdf");
    fireEvent.click(deleteTrigger);

    const confirmButton = await screen.findByText("Delete", { selector: "button" });
    fireEvent.click(confirmButton);

    await waitFor(() => {
      expect(presentationsApi.delete).toHaveBeenCalledWith(courseId, "lecture1.pdf");
    });

    await waitFor(() => {
      expect(screen.queryByText("lecture1.pdf")).not.toBeInTheDocument();
    });

    expect(onFilesChange).toHaveBeenCalledWith(["lecture1.pdf"]);
    expect(onFilesChange).toHaveBeenCalledWith([]);
  });

  it("shows a View button for failed rows and opens a dialog with full error", async () => {
    (presentationsApi.list as Mock).mockResolvedValue(["bad.pdf"]);
    (presentationsApi.listStatuses as Mock).mockResolvedValue([
      {
        id: 11,
        course_id: courseId,
        filename: "bad.pdf",
        blob_path: "blob",
        content_hash: null,
        uploaded_at: "2023-01-01T00:00:00Z",
        status: "failed",
        last_error: "Very long error message: something went wrong deep inside the extractor stacktrace...",
        processed_at: "2023-01-02T00:00:00Z",
      },
    ]);

    render(<CourseMaterialsTable courseId={courseId} />);

    await waitFor(() => {
      expect(screen.getByText("bad.pdf")).toBeInTheDocument();
    });

    const viewBtn = screen.getByLabelText("View error for bad.pdf");
    fireEvent.click(viewBtn);

    // Dialog content should include the full error.
    expect(await screen.findByText("Error details")).toBeInTheDocument();
    expect(
      await screen.findByText(
        "Very long error message: something went wrong deep inside the extractor stacktrace..."
      )
    ).toBeInTheDocument();
  });

  it("deletes all files via confirmation dialog", async () => {
    (presentationsApi.list as Mock).mockResolvedValue(["a.pdf", "b.pdf"]);
    (presentationsApi.listStatuses as Mock).mockResolvedValue([]);
    (presentationsApi.deleteAll as Mock).mockResolvedValue(undefined);

    const onFilesChange = vi.fn();
    render(<CourseMaterialsTable courseId={courseId} onFilesChange={onFilesChange} />);

    await waitFor(() => {
      expect(screen.getByText("a.pdf")).toBeInTheDocument();
      expect(screen.getByText("b.pdf")).toBeInTheDocument();
    });

    const deleteAllTrigger = screen.getByLabelText("Delete all files");
    fireEvent.click(deleteAllTrigger);

    const confirmButton = await screen.findByText("Delete all files", { selector: "button" });
    fireEvent.click(confirmButton);

    await waitFor(() => {
      expect(presentationsApi.deleteAll).toHaveBeenCalledWith(courseId);
    });

    await waitFor(() => {
      expect(screen.getByText("No presentations uploaded yet.")).toBeInTheDocument();
    });

    expect(onFilesChange).toHaveBeenCalledWith(["a.pdf", "b.pdf"]);
    expect(onFilesChange).toHaveBeenCalledWith([]);
  });
});


