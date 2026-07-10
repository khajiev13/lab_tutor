import { describe, expect, it, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";

import {
  resetTeacherTwinUiState,
  useTeacherTwinUiState,
} from "./teacherTwinUiStore";

describe("teacherTwinUiStore", () => {
  beforeEach(() => {
    resetTeacherTwinUiState();
  });

  it("returns sensible defaults for an unseen course", () => {
    const { result } = renderHook(() => useTeacherTwinUiState(42));
    expect(result.current.state.activeTab).toBe("overview");
    expect(result.current.state.cohort.steps).toBe(10);
    expect(result.current.state.simulator.simMode).toBe("automatic");
    expect(result.current.state.whatIf.mode).toBe("automatic");
    expect(result.current.state.whatIf.automaticIntensity).toBeCloseTo(0.6);
  });

  it("survives an unmount/remount within the same session", () => {
    // Mount #1 — set custom values
    const first = renderHook(() => useTeacherTwinUiState(1));
    act(() => {
      first.result.current.setActiveTab("what-if");
      first.result.current.setCohort((prev) => ({ ...prev, steps: 25 }));
      first.result.current.setWhatIf((prev) => ({
        ...prev,
        manualSkills: [
          { skill_name: "algebra", current_avg_mastery: 0.4, hypothetical_mastery: 0.8 },
        ],
      }));
    });
    expect(first.result.current.state.activeTab).toBe("what-if");
    expect(first.result.current.state.cohort.steps).toBe(25);

    // Simulate page navigation away and back: unmount, then mount #2
    first.unmount();
    const second = renderHook(() => useTeacherTwinUiState(1));
    expect(second.result.current.state.activeTab).toBe("what-if");
    expect(second.result.current.state.cohort.steps).toBe(25);
    expect(second.result.current.state.whatIf.manualSkills).toHaveLength(1);
    expect(second.result.current.state.whatIf.manualSkills[0].skill_name).toBe(
      "algebra",
    );
  });

  it("keeps state isolated per courseId", () => {
    const courseA = renderHook(() => useTeacherTwinUiState(1));
    const courseB = renderHook(() => useTeacherTwinUiState(2));

    act(() => {
      courseA.result.current.setActiveTab("simulator");
      courseB.result.current.setActiveTab("cohort");
    });

    expect(courseA.result.current.state.activeTab).toBe("simulator");
    expect(courseB.result.current.state.activeTab).toBe("cohort");
  });

  it("resetTeacherTwinUiState() clears all courses (logout case)", () => {
    const courseA = renderHook(() => useTeacherTwinUiState(1));
    act(() => {
      courseA.result.current.setActiveTab("what-if");
    });
    expect(courseA.result.current.state.activeTab).toBe("what-if");

    act(() => {
      resetTeacherTwinUiState();
    });
    expect(courseA.result.current.state.activeTab).toBe("overview");
  });

  it("resetTeacherTwinUiState(courseId) clears a single course only", () => {
    const courseA = renderHook(() => useTeacherTwinUiState(1));
    const courseB = renderHook(() => useTeacherTwinUiState(2));

    act(() => {
      courseA.result.current.setActiveTab("simulator");
      courseB.result.current.setActiveTab("what-if");
    });

    act(() => {
      resetTeacherTwinUiState(1);
    });

    expect(courseA.result.current.state.activeTab).toBe("overview");
    expect(courseB.result.current.state.activeTab).toBe("what-if");
  });
});
