import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { coursesApi } from "../../api";
import { CourseReadinessRoad } from "./CourseReadinessRoad";
import type { Course, CourseReadiness } from "../../types";

vi.mock("../../api", () => ({
  coursesApi: {
    publish: vi.fn(),
  },
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

const mockPublish = vi.mocked(coursesApi.publish);

function makeReadiness(overrides: Partial<CourseReadiness> = {}): CourseReadiness {
  return {
    course_id: 7,
    publication_status: "draft",
    availability_status: "draft",
    can_publish: false,
    blockers: ["Review prerequisites."],
    next_action: {
      id: "prerequisites",
      label: "Review prerequisites",
      route: "/courses/7/prerequisites",
    },
    gates: [
      {
        id: "book",
        label: "Book skill bank",
        status: "complete",
        route: "/courses/7/architect",
        detail: "Book skill bank is complete.",
      },
      {
        id: "market",
        label: "Market skill bank",
        status: "complete",
        route: "/courses/7/market-analyst",
        detail: "Market skill bank is complete or waived.",
      },
      {
        id: "prerequisites",
        label: "Prerequisite review",
        status: "ready",
        route: "/courses/7/prerequisites",
        detail: "Review and approve prerequisites before publishing.",
      },
      {
        id: "publish",
        label: "Publish",
        status: "locked",
        route: null,
        detail: "Resolve readiness blockers before publishing.",
      },
    ],
    prerequisite_review: {
      status: "needs_review",
      edge_count: 4,
      isolated_skill_count: 1,
      last_generated_at: null,
    },
    ...overrides,
  };
}

function makePublishedCourse(): Course {
  return {
    id: 7,
    title: "Data Mining",
    description: null,
    level: "bachelor",
    teacher_id: 1,
    created_at: "2026-01-01T00:00:00Z",
    extraction_status: "finished",
    publication_status: "published",
    market_gate_status: "completed",
  };
}

function renderRoad(readiness: CourseReadiness, onRefresh = vi.fn()) {
  return {
    onRefresh,
    ...render(
      <MemoryRouter>
        <CourseReadinessRoad readiness={readiness} onRefresh={onRefresh} />
      </MemoryRouter>,
    ),
  };
}

describe("CourseReadinessRoad", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows prerequisite review as the next action and blocks publishing", () => {
    renderRoad(makeReadiness());

    expect(screen.getByText("Course readiness")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Review prerequisites/i })).toHaveAttribute(
      "href",
      "/courses/7/prerequisites",
    );
    expect(screen.getByText("Prerequisite review")).toBeInTheDocument();
    expect(screen.getByText("Review prerequisites.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Publish course/i })).toBeDisabled();
  });

  it("publishes when all gates pass", async () => {
    const user = userEvent.setup();
    const onRefresh = vi.fn();
    mockPublish.mockResolvedValue(makePublishedCourse());

    renderRoad(
      makeReadiness({
        can_publish: true,
        blockers: [],
        next_action: { id: "publish", label: "Publish course", route: null },
        gates: [
          {
            id: "book",
            label: "Book skill bank",
            status: "complete",
            route: "/courses/7/architect",
            detail: "Book skill bank is complete.",
          },
          {
            id: "market",
            label: "Market skill bank",
            status: "complete",
            route: "/courses/7/market-analyst",
            detail: "Market skill bank is complete or waived.",
          },
          {
            id: "prerequisites",
            label: "Prerequisite review",
            status: "complete",
            route: "/courses/7/prerequisites",
            detail: "Prerequisites are approved.",
          },
          {
            id: "publish",
            label: "Publish",
            status: "ready",
            route: null,
            detail: "Course is ready to publish.",
          },
        ],
        prerequisite_review: {
          status: "approved",
          edge_count: 4,
          isolated_skill_count: 0,
          last_generated_at: "2026-01-01T00:00:00Z",
        },
      }),
      onRefresh,
    );

    await user.click(screen.getByRole("button", { name: /Publish course/i }));

    await waitFor(() => expect(mockPublish).toHaveBeenCalledWith(7));
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });
});
