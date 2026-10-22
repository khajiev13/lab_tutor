import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CourseStepperHeader } from "@/features/courses/components/CourseStepperHeader";
import { useCourseDetail } from "@/features/courses/context/CourseDetailContext";

vi.mock("@/features/courses/context/CourseDetailContext", () => ({ useCourseDetail: vi.fn() }));
const setActiveStep = vi.fn();
const refreshStepStatuses = vi.fn();

function show(overrides: Partial<ReturnType<typeof useCourseDetail>> = {}) {
  vi.mocked(useCourseDetail).mockReturnValue({
    course: { id: 7, extraction_status: "finished" },
    activeStep: 3, nextPreparationStep: 3, setActiveStep, refreshStepStatuses,
    getStepStatus: (index: number) => index === 0 ? "completed" : index < 4 ? "pending" : "locked",
    canNavigateToStep: (index: number) => index < 4,
    booksSkipped: false, stepStatusesLoading: false, stepStatusesError: false,
    ...overrides,
  } as ReturnType<typeof useCourseDetail>);
  return render(<MemoryRouter><CourseStepperHeader /></MemoryRouter>);
}

beforeEach(() => vi.clearAllMocks());

describe("preparation guide", () => {
  it("shows five required steps, one next action, and the reason for each lock", () => {
    show();
    const steps = within(screen.getByRole("list", { name: "Course preparation steps" }));
    expect(steps.getAllByRole("listitem")).toHaveLength(5);
    expect(steps.getByRole("button", { name: /Step 4: Analysis/ })).toBeDisabled();
    expect(steps.getByRole("button", { name: /Step 5: Results/ })).toBeDisabled();
    expect(steps.getByText("Choose and download books first")).toBeInTheDocument();
    expect(steps.getByText("Complete analysis first")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Choose books" }));
    expect(setActiveStep).toHaveBeenCalledWith(3);
  });

  it("allows completed steps to be revisited and prevents locked navigation", () => {
    show();
    fireEvent.click(screen.getByRole("button", { name: /Step 1: Materials/ }));
    expect(setActiveStep).toHaveBeenCalledWith(0);
    setActiveStep.mockClear();
    fireEvent.click(screen.getByRole("button", { name: /Step 4: Analysis/ }));
    expect(setActiveStep).not.toHaveBeenCalled();
  });

  it("keeps optional tools collapsed and outside the required path", () => {
    show();
    expect(screen.queryByRole("button", { name: "Normalize concepts" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Optional preparation tools/ }));
    fireEvent.click(screen.getByRole("button", { name: "Normalize concepts" }));
    expect(setActiveStep).toHaveBeenCalledWith(1);
  });

  it("explains an analysis in progress without offering results", () => {
    show({ activeStep: 4, nextPreparationStep: 4, analysisRunStatus: "extracting" });
    expect(screen.getByRole("heading", { name: "Analyzing your books" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "View analysis progress" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Back to course setup" })).not.toBeInTheDocument();
  });

  it("preserves skipping books without pretending that analysis was completed", () => {
    show({ booksSkipped: true, nextPreparationStep: null });
    expect(screen.getByRole("heading", { name: "Continuing without books" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to course setup" })).toHaveAttribute("href", "/courses/7");
    expect(screen.getAllByText("Not needed")).toHaveLength(2);
  });

  it("asks for chapter approval when analysis is waiting on the teacher", () => {
    show({ activeStep: 4, nextPreparationStep: 4, analysisRunStatus: "chapter_extracted" });
    expect(screen.getByRole("heading", { name: "Review the extracted chapters" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Review extracted chapters" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Step 5: Results/ })).toBeDisabled();
  });

  it("provides a retry when progress cannot be loaded", () => {
    show({ stepStatusesError: true });
    expect(screen.getByRole("alert")).toHaveTextContent("Could not load course progress");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(refreshStepStatuses).toHaveBeenCalledOnce();
    expect(screen.queryByRole("button", { name: "Choose books" })).not.toBeInTheDocument();
  });

  it("waits for confirmed progress before offering a next action", () => {
    show({ stepStatusesLoading: true });
    expect(screen.getByRole("status")).toHaveTextContent("Checking course progress");
    expect(screen.queryByRole("button", { name: "Choose books" })).not.toBeInTheDocument();
  });
});


it("keeps chapter planning required even after books were skipped", () => {
  show({ booksSkipped: true, nextPreparationStep: 2, activeStep: 2 });
  expect(screen.getByRole("button", {name: /Step 2: Chapters/})).toBeEnabled();
  expect(screen.getByText("Your next step · Step 2 of 5")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", {name: "Build chapter plan"}));
  expect(setActiveStep).toHaveBeenCalledWith(2);
  expect(screen.queryByRole("link", {name: "Back to course setup"})).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", {name: /Optional preparation tools/}));
  expect(screen.getByRole("button", {name: "Normalize concepts"})).toBeEnabled();
  expect(screen.getAllByRole("button", {name: "Build chapter plan"})).toHaveLength(1);
});
