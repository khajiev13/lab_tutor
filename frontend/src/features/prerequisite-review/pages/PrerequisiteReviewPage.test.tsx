import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { coursesApi } from "@/features/courses/api";
import type { PrerequisiteReview } from "@/features/courses/types";
import { PrerequisiteReviewPage } from "./PrerequisiteReviewPage";

vi.mock("@/features/courses/api", () => ({
  coursesApi: {
    approvePrerequisiteReview: vi.fn(),
    getPrerequisiteReview: vi.fn(),
    regeneratePrerequisites: vi.fn(),
    savePrerequisiteReview: vi.fn(),
  },
}));

const mockCoursesApi = vi.mocked(coursesApi);

function makeReview(overrides: Partial<PrerequisiteReview> = {}): PrerequisiteReview {
  return {
    course_id: 7,
    status: "needs_review",
    is_rebuilding: false,
    skills: [
      { name: "Intro to Python", source: "book", chapter_title: "Week 1" },
      { name: "Data Frames", source: "book", chapter_title: "Week 2" },
      { name: "Model Validation", source: "market", chapter_title: null },
    ],
    draft_edges: [
      {
        prerequisite_name: "Intro to Python",
        dependent_name: "Data Frames",
        confidence: "high",
        reasoning: "Students need Python syntax before manipulating tabular data.",
        source: "ai",
      },
    ],
    isolated_skills: ["Model Validation"],
    validation: {
      is_valid: true,
      errors: [],
      cycle_path: [],
    },
    metadata: {
      edge_count: 1,
      generated_edge_count: 1,
      added_edge_count: 0,
      removed_edge_count: 0,
      isolated_skill_count: 1,
      last_generated_at: "2026-05-01T00:00:00Z",
      last_invalidated_at: null,
      approved_at: null,
    },
    ...overrides,
  };
}

function renderRoute() {
  return render(
    <MemoryRouter initialEntries={["/courses/7/prerequisites"]}>
      <Routes>
        <Route path="/courses/:id/prerequisites" element={<PrerequisiteReviewPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("PrerequisiteReviewPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockCoursesApi.getPrerequisiteReview.mockResolvedValue(makeReview());
    mockCoursesApi.savePrerequisiteReview.mockResolvedValue(makeReview({ isolated_skills: [] }));
    mockCoursesApi.approvePrerequisiteReview.mockResolvedValue(
      makeReview({ status: "approved", isolated_skills: [] }),
    );
    mockCoursesApi.regeneratePrerequisites.mockResolvedValue(undefined);
  });

  it("loads review details from the route and shows the graph preview", async () => {
    renderRoute();

    expect(await screen.findByRole("heading", { name: "Prerequisite Review" })).toBeInTheDocument();
    expect(mockCoursesApi.getPrerequisiteReview).toHaveBeenCalledWith(7);
    expect(screen.getAllByText("Intro to Python").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Data Frames").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Model Validation").length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Graph preview" })).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: "Prerequisite graph preview" }),
    ).toBeInTheDocument();
  });

  it("saves the draft when a teacher removes an edge", async () => {
    const user = userEvent.setup();
    renderRoute();

    await screen.findByRole("heading", { name: "Prerequisite Review" });
    await user.click(screen.getByRole("button", { name: /Remove Intro to Python prerequisite/i }));

    await waitFor(() =>
      expect(mockCoursesApi.savePrerequisiteReview).toHaveBeenCalledWith(7, {
        draft_edges: [],
        isolated_skills_viewed: false,
      }),
    );
  });

  it("requires a fresh isolated-skill review when removing an edge creates isolated skills", async () => {
    const user = userEvent.setup();
    mockCoursesApi.getPrerequisiteReview.mockResolvedValue(
      makeReview({
        isolated_skills: [],
      }),
    );
    mockCoursesApi.savePrerequisiteReview.mockResolvedValue(
      makeReview({
        draft_edges: [],
        isolated_skills: ["Intro to Python", "Data Frames", "Model Validation"],
      }),
    );

    renderRoute();

    await screen.findByRole("heading", { name: "Prerequisite Review" });
    expect(screen.getByRole("button", { name: "Approve graph" })).not.toBeDisabled();

    await user.click(screen.getByRole("button", { name: /Remove Intro to Python prerequisite/i }));

    await waitFor(() =>
      expect(mockCoursesApi.savePrerequisiteReview).toHaveBeenCalledWith(7, {
        draft_edges: [],
        isolated_skills_viewed: false,
      }),
    );
    await waitFor(() => expect(screen.getByRole("button", { name: "Approve graph" })).toBeDisabled());
    expect(screen.getByRole("button", { name: "Mark reviewed" })).toBeEnabled();
  });

  it("disables approval when validation reports a cycle", async () => {
    mockCoursesApi.getPrerequisiteReview.mockResolvedValue(
      makeReview({
        isolated_skills: [],
        validation: {
          is_valid: false,
          errors: ["Cycle detected in prerequisite graph."],
          cycle_path: ["Intro to Python", "Data Frames", "Intro to Python"],
        },
      }),
    );

    renderRoute();

    expect(await screen.findByText("Cycle detected in prerequisite graph.")).toBeInTheDocument();
    expect(screen.getByText("Intro to Python -> Data Frames -> Intro to Python")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve graph" })).toBeDisabled();
  });

  it("shows a clear approved state after approval succeeds", async () => {
    const user = userEvent.setup();
    mockCoursesApi.getPrerequisiteReview.mockResolvedValue(
      makeReview({ isolated_skills: [] }),
    );
    mockCoursesApi.approvePrerequisiteReview.mockResolvedValue(
      makeReview({ status: "approved", isolated_skills: [] }),
    );

    renderRoute();

    await screen.findByRole("heading", { name: "Prerequisite Review" });
    await user.click(screen.getByRole("button", { name: "Approve graph" }));

    expect(await screen.findByText("Prerequisite graph approved")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approved" })).toBeDisabled();
  });
});
