import {act, render, screen, waitFor} from "@testing-library/react";
import {beforeEach, expect, it, vi} from "vitest";
import {EvidenceChart} from "@/features/market-demand/components/EvidenceChart";

const runtime = vi.hoisted(() => ({
  init: vi.fn(), use: vi.fn(), setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn(), on: vi.fn(), off: vi.fn(),
}));
vi.mock("echarts/core", () => ({init: runtime.init, use: runtime.use}));
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
  vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockImplementation(() => width);
  vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockImplementation(() => height);
  vi.stubGlobal("ResizeObserver", class {
    constructor(callback: ResizeObserverCallback) {resize = callback;}
    observe() {}
    disconnect() {disconnect();}
  });
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
  expect(await screen.findByRole("alert")).toHaveTextContent(/Chart unavailable/);
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
