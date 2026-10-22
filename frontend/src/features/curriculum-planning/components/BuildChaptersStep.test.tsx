import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { BuildChaptersStep } from "@/features/curriculum-planning/components/BuildChaptersStep";
import { getChapterPlan, generateChapterPlan } from "@/features/curriculum-planning/api";

const context = vi.hoisted(() => ({ courseId: 1, course: {extraction_status: "finished"}, materialsReady: true, goToNext: vi.fn(), setHasChapters: vi.fn(), refreshChapterPlan: vi.fn() }));
vi.mock("@/features/courses/context/CourseDetailContext", () => ({ useCourseDetail: () => context }));
vi.mock("@/features/curriculum-planning/api", () => ({ getChapterPlan: vi.fn(), generateChapterPlan: vi.fn() }));
vi.mock("@/features/curriculum-planning/components/ChapterPlanBuilder", () => ({ ChapterPlanBuilder: () => <div>Saved chapters</div> }));
const emptyPlan = {course_id: 1, chapters: [], unassigned_documents: [], all_documents: []};
const plan = {...emptyPlan, chapters: [{number: 1, title: "Introduction", description: "", learning_objectives: [], prerequisites: [], assigned_documents: ["doc-1"]}]};
function show() { return render(<MemoryRouter><BuildChaptersStep/></MemoryRouter>); }
beforeEach(() => {context.courseId = 1; vi.clearAllMocks(); vi.mocked(getChapterPlan).mockReset().mockResolvedValue(emptyPlan);});

it("offers retry after a load failure instead of treating it as an empty plan", async () => {
  vi.mocked(getChapterPlan).mockRejectedValueOnce(new Error("Offline")).mockResolvedValueOnce(plan);
  show();
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not load your chapter plan");
  expect(screen.getByRole("button", {name: "Generate Plan"})).toBeDisabled();
  expect(screen.queryByRole("button", {name: "Continue to Select Books"})).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", {name: "Retry loading plan"}));
  expect(await screen.findByText("Saved chapters")).toBeInTheDocument();
  expect(context.setHasChapters).toHaveBeenCalledWith(true);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

it("unlocks continuation once generation has saved a nonempty plan", async () => {
  vi.mocked(generateChapterPlan).mockResolvedValue(plan);
  show();
  await waitFor(() => expect(screen.getByRole("button", {name: "Generate Plan"})).toBeEnabled());
  fireEvent.click(screen.getByRole("button", {name: "Generate Plan"}));
  expect(await screen.findByText("Saved chapters")).toBeInTheDocument();
  expect(context.setHasChapters).toHaveBeenCalledWith(true);
  fireEvent.click(screen.getByRole("button", {name: "Continue to Select Books"}));
  expect(context.goToNext).toHaveBeenCalledOnce();
  expect(generateChapterPlan).toHaveBeenCalledWith(1);
});


it("offers Return to Swarm only after generation saves chapters for this course", async () => {
  context.courseId = 42;
  let resolvePlan!: (saved: typeof plan) => void;
  vi.mocked(generateChapterPlan).mockImplementation(() => new Promise(resolve => {resolvePlan = resolve;}));
  show();
  await waitFor(() => expect(screen.getByRole("button", {name: "Generate Plan"})).toBeEnabled());
  expect(screen.queryByRole("link", {name: "Return to Swarm"})).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", {name: "Generate Plan"}));
  expect(screen.queryByRole("link", {name: "Return to Swarm"})).not.toBeInTheDocument();
  await act(async () => resolvePlan({...plan, course_id: 42}));
  expect(screen.getByRole("link", {name: "Return to Swarm"})).toHaveAttribute("href", "/courses/42/market-analyst");
  expect(screen.getByRole("button", {name: "Continue to Select Books"})).toBeEnabled();
});

it("offers Return to Swarm when a previously saved plan loads", async () => {
  vi.mocked(getChapterPlan).mockResolvedValue(plan);
  show();
  expect(await screen.findByRole("link", {name: "Return to Swarm"})).toHaveAttribute("href", "/courses/1/market-analyst");
});
