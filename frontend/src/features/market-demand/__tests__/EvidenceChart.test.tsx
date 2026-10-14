import {act, render, screen, waitFor} from "@testing-library/react";
import {beforeEach, expect, it, vi} from "vitest";
import {format} from "echarts/core";
import {EvidenceChart} from "@/features/market-demand/components/EvidenceChart";

const runtime = vi.hoisted(() => ({
  init: vi.fn(), use: vi.fn(), setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn(), on: vi.fn(), off: vi.fn(),
}));
vi.mock("echarts/core", async (importOriginal) => {
  const core = await importOriginal<typeof import("echarts/core")>();
  return {init: runtime.init, use: runtime.use, format: core.format};
});
vi.mock("echarts/charts", () => ({BarChart: {}, ScatterChart: {}, HeatmapChart: {}}));
vi.mock("echarts/components", () => ({GridComponent: {}, DatasetComponent: {}, TooltipComponent: {}, VisualMapComponent: {}, AriaComponent: {}}));
vi.mock("echarts/renderers", () => ({SVGRenderer: {}}));
let resize: ResizeObserverCallback;
const disconnect = vi.fn();
let width = 600;
let height = 400;
beforeEach(() => {
  vi.clearAllMocks();
  width = 600; height = 400;
  document.documentElement.classList.remove("dark");
  runtime.init.mockReturnValue(runtime);
  // jsdom has no canvas. Keep ECharts' real text measurement and its platform
  // fallback rather than replacing the width calculation with a test formula.
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
  vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockImplementation(() => width);
  vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockImplementation(() => height);
  vi.stubGlobal("ResizeObserver", class {
    constructor(callback: ResizeObserverCallback) {resize = callback;}
    observe() {}
    disconnect() {disconnect();}
  });
});

it.each([
  "Synthetic competency 24: 70% · 7 / 10 supporting / assessed",
  "VeryLongUnbrokenCompetencyDescriptorWithoutSpacesOrBreaksAtAll · Software Developers: 4.25 / 5 · Importance · 30.3 · 2.A.1.a",
  "数据分析能力与跨团队沟通技能及软件开发职业 · {source|原始标签} 🧪: 83.33% · 20 / 24 supporting / assessed",
])("wraps complete source tooltip text within a narrow chart: %s", async (source) => {
  width = 288;
  const onFocus = vi.fn();
  render(<EvidenceChart label="Demand" option={{}} onFocus={onFocus}/>);
  await waitFor(() => expect(runtime.setOption).toHaveBeenCalled());
  const tooltip = runtime.setOption.mock.calls.at(-1)![0].tooltip;
  const text = tooltip.formatter({data: {tooltipText: source}});
  expect(text).toContain("\n");
  expect(text.replaceAll("\n", "")).toBe(source.replaceAll("{", "｛").replaceAll("}", "｝"));
  expect(text).not.toMatch(/[{}]/);
  // Content plus actual ECharts rich-text padding/border must fit the frame.
  expect(format.getTextRect(text).width + 22).toBeLessThanOrEqual(288);
  expect(tooltip.renderMode).toBe("richText");
  expect(onFocus).not.toHaveBeenCalled();
});

it("recomputes tooltip wrapping from restored and resized width through theme changes", async () => {
  width = 0;
  render(<EvidenceChart label="Demand" option={{}} onFocus={vi.fn()}/>);
  width = 180;
  act(() => resize([], {} as ResizeObserver));
  await waitFor(() => expect(runtime.setOption).toHaveBeenCalled());
  const source = "Synthetic competency 24: 70% · 7 / 10 supporting / assessed";
  const currentText = () => runtime.setOption.mock.calls.at(-1)![0].tooltip.formatter({data: {tooltipText: source}});
  const narrow = currentText();
  expect(format.getTextRect(narrow).width + 22).toBeLessThanOrEqual(180);
  width = 720;
  act(() => resize([], {} as ResizeObserver));
  expect(currentText()).toBe(source);
  width = 288;
  act(() => resize([], {} as ResizeObserver));
  act(() => document.documentElement.classList.add("dark"));
  await waitFor(() => expect(runtime.setOption.mock.calls.at(-1)![0].tooltip.textStyle.color).toBe("#f4f4f5"));
  expect(format.getTextRect(currentText()).width + 22).toBeLessThanOrEqual(288);
  expect(currentText().replaceAll("\n", "")).toBe(source);
});

it("owns resize, option replacement, focus identity and disposal", async () => {
  const onFocus = vi.fn();
  const option = {series: [{type: "bar", data: [{value: 50, focus: {candidateId: "python"}}]}]};
  const {rerender, unmount} = render(<EvidenceChart label="Demand" option={option} onFocus={onFocus}/>);
  await waitFor(() => expect(runtime.setOption).toHaveBeenCalled());
  const click = runtime.on.mock.calls.find(([event]) => event === "click")![1];
  act(() => click({data: {value: 50, focus: {candidateId: "python"}}}));
  expect(onFocus).toHaveBeenCalledWith({candidateId: "python"});
  act(() => click({dataIndex: 0, data: {value: 50}}));
  expect(onFocus).toHaveBeenCalledTimes(1);
  act(() => resize([], {} as ResizeObserver));
  expect(runtime.resize).toHaveBeenCalled();
  const next = {...option, xAxis: {max: 100}};
  rerender(<EvidenceChart label="Demand" option={next} onFocus={onFocus}/>);
  await waitFor(() => expect(runtime.setOption).toHaveBeenLastCalledWith(expect.objectContaining({xAxis: expect.objectContaining({max: 100})}), {notMerge: true}));
  unmount();
  expect(runtime.off).toHaveBeenCalledWith("click", click);
  expect(runtime.dispose).toHaveBeenCalledTimes(1);
  expect(disconnect).toHaveBeenCalledTimes(1);
});

it("waits for a nonzero size and refreshes colors when the root theme changes", async () => {
  width = 0; height = 0;
  const {unmount} = render(<EvidenceChart label="Demand" option={{}} onFocus={vi.fn()}/>);
  await act(async () => {});
  expect(runtime.init).not.toHaveBeenCalled();
  width = 600; height = 400;
  act(() => resize([], {} as ResizeObserver));
  await waitFor(() => expect(runtime.init).toHaveBeenCalledTimes(1));
  const initial = runtime.setOption.mock.calls.at(-1)![0].textStyle.color;
  act(() => document.documentElement.classList.add("dark"));
  await waitFor(() => expect(runtime.setOption.mock.calls.at(-1)![0].textStyle.color).not.toBe(initial));
  unmount();
});

it("reports initialization errors without removing the accessible fallback", async () => {
  runtime.init.mockImplementationOnce(() => {throw new Error("renderer unavailable");});
  const onError = vi.fn();
  render(<><EvidenceChart label="Demand" option={{}} onFocus={vi.fn()} onError={onError}/><button>Inspect Python</button></>);
  expect(await screen.findByRole("alert")).toHaveTextContent(/chart unavailable/i);
  expect(onError).toHaveBeenCalledWith(expect.any(Error));
  expect(screen.getByRole("button", {name: "Inspect Python"})).toBeEnabled();
});

it("uses text-only tooltips and ignores late async loading after removal", async () => {
  const {unmount} = render(<EvidenceChart label="Demand" option={{tooltip: {formatter: "<img>"}}} onFocus={vi.fn()}/>);
  await waitFor(() => expect(runtime.setOption).toHaveBeenCalled());
  const tooltip = runtime.setOption.mock.calls.at(-1)![0].tooltip;
  expect(tooltip.renderMode).toBe("richText");
  expect(tooltip.formatter({data: {tooltipText: "<script>alert(1)</script>"}})).toContain("<script>");
  unmount();
  vi.clearAllMocks();
  const removed = render(<EvidenceChart label="Removed" option={{}} onFocus={vi.fn()}/>);
  removed.unmount();
  await act(async () => {});
  expect(runtime.init).not.toHaveBeenCalled();
});

it("disposes a failing instance once and keeps render failures from taking down siblings", async () => {
  runtime.setOption.mockImplementationOnce(() => {throw new Error("bad option");});
  const onError = vi.fn();
  const {unmount} = render(<><EvidenceChart label="Demand" option={{}} onFocus={vi.fn()} onError={onError}/><button>Select Python</button></>);
  expect(await screen.findByRole("alert")).toHaveTextContent("Chart unavailable. Use the values below to inspect evidence.");
  expect(runtime.dispose).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("button", {name: "Select Python"})).toBeEnabled();
  act(() => resize([], {} as ResizeObserver));
  expect(onError).toHaveBeenCalledTimes(1);
  unmount();
  expect(runtime.dispose).toHaveBeenCalledTimes(1);
});

it("retains the latest option while hidden and applies it when the container is restored", async () => {
  width = 0;
  const {rerender} = render(<EvidenceChart label="Demand" option={{xAxis: {max: 1}}} onFocus={vi.fn()}/>);
  rerender(<EvidenceChart label="Demand" option={{xAxis: {max: 100}}} onFocus={vi.fn()}/>);
  width = 600;
  act(() => resize([], {} as ResizeObserver));
  await waitFor(() => expect(runtime.setOption).toHaveBeenCalledWith(expect.objectContaining({xAxis: expect.objectContaining({max: 100})}), {notMerge: true}));
});

it("resolves width-dependent options after hidden restore, resize, replacement and theme change", async () => {
  width = 0;
  const option = (currentWidth: number) => ({grid: {left: currentWidth / 4}, yAxis: {name: "Importance (1–5)", nameTextStyle: {align: "left"}}});
  const {rerender} = render(<EvidenceChart label="Comparison" option={option} onFocus={vi.fn()}/>);
  width = 288;
  act(() => resize([], {} as ResizeObserver));
  await waitFor(() => expect(runtime.setOption).toHaveBeenCalled());
  expect(runtime.setOption.mock.calls.at(-1)![0]).toMatchObject({grid: {left: 72}});
  width = 736;
  act(() => resize([], {} as ResizeObserver));
  expect(runtime.setOption.mock.calls.at(-1)![0].grid.left).toBe(184);
  width = 0;
  rerender(<EvidenceChart label="Comparison" option={currentWidth => ({...option(currentWidth), grid: {left: currentWidth / 2}})} onFocus={vi.fn()}/>);
  width = 358;
  act(() => resize([], {} as ResizeObserver));
  expect(runtime.setOption.mock.calls.at(-1)![0].grid.left).toBe(179);
  act(() => document.documentElement.classList.add("dark"));
  await waitFor(() => expect(runtime.setOption.mock.calls.at(-1)![0].yAxis.nameTextStyle).toMatchObject({align: "left", color: "#f4f4f5"}));
  expect(runtime.setOption.mock.calls.at(-1)![0].grid.left).toBe(179);
});
