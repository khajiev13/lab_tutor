import {useEffect, useLayoutEffect, useRef, useState} from "react";
import type {EChartsCoreOption, EChartsType} from "echarts/core";
import {cn} from "@/lib/utils";
import type {ChartFocus} from "@/features/market-demand/types";

interface Props {
  option: EChartsCoreOption;
  label: string;
  className?: string;
  onFocus: (focus: ChartFocus) => void;
  onError?: (error: Error) => void;
}

function wrapTooltip(text: string, width: number, measure: (text: string) => number): string {
  return text.split("\n").map((paragraph) => {
    const lines: string[] = [];
    let line = "";
    for (const token of paragraph.match(/\s+|\S+/gu) ?? []) {
      if (measure(line + token) <= width) {line += token; continue;}
      if (line) {lines.push(line); line = "";}
      // Break oversized words by Unicode code point without dropping source text.
      for (const character of token) {
        if (line && measure(line + character) > width) {lines.push(line); line = "";}
        line += character;
      }
    }
    lines.push(line);
    return lines.join("\n");
  }).join("\n");
}

function themedOption(option: EChartsCoreOption, width: number, measure: (text: string) => number): EChartsCoreOption {
  const dark = document.documentElement.classList.contains("dark");
  const color = dark ? "#f4f4f5" : "#18181b";
  const line = dark ? "#71717a" : "#a1a1aa";
  const axes = (value: unknown) => {
    const style = (axis: Record<string, unknown>) => ({...axis,
      nameTextStyle: {...axis.nameTextStyle as object, color},
      axisLabel: {...axis.axisLabel as object, color}, axisLine: {lineStyle: {color: line}},
      splitLine: {lineStyle: {color: dark ? "#3f3f46" : "#e4e4e7"}},
    });
    if (!value) return undefined;
    return Array.isArray(value) ? value.map(style) : style(value as Record<string, unknown>);
  };
  const tooltipText = (params: unknown): string => {
    const item = (Array.isArray(params) ? params[0] : params) as {data?: {tooltipText?: string}} | undefined;
    // Rich text draws source text without an HTML DOM tooltip. Prevent rich-text
    // style tokens in source labels from masquerading as formatting directives.
    const text = String(item?.data?.tooltipText ?? "Inspect the values below the chart").replaceAll("{", "｛").replaceAll("}", "｝");
    // ECharts' rich-text tooltip does not forward width/overflow to its text
    // element. Reserve padding, border and a small inset, then insert line breaks
    // using the same default-font measurement as that renderer.
    return wrapTooltip(text, Math.max(1, width - 32), measure);
  };
  return {...option, backgroundColor: "transparent", textStyle: {...option.textStyle as object, color},
    xAxis: axes(option.xAxis), yAxis: axes(option.yAxis),
    aria: {enabled: true, decal: {show: true}},
    tooltip: {trigger: "item", renderMode: "richText", confine: true, formatter: tooltipText,
      padding: [8, 10], shadowBlur: 0, shadowOffsetX: 0, shadowOffsetY: 0,
      backgroundColor: dark ? "#18181b" : "#ffffff", borderColor: line, textStyle: {color}},
    ...(option.visualMap ? {visualMap: {...option.visualMap as object, textStyle: {color}}} : {}),
  };
}

export function EvidenceChart({option, label, className, onFocus, onError}: Props) {
  const container = useRef<HTMLDivElement>(null);
  const instance = useRef<EChartsType | null>(null);
  const latest = useRef({option, onFocus, onError});
  const redraw = useRef<(() => void) | null>(null);
  const [error, setError] = useState(false);
  useLayoutEffect(() => {
    latest.current = {option, onFocus, onError};
    redraw.current?.();
  }, [option, onFocus, onError]);

  useEffect(() => {
    const element = container.current!;
    let removed = false;
    let loading = false;
    let failed = false;
    let measureText: ((text: string) => number) | null = null;
    const click = (params: unknown) => {
      const focus = (params as {data?: {focus?: ChartFocus}})?.data?.focus;
      if (!focus || typeof focus.candidateId !== "string" || !focus.candidateId) return;
      latest.current.onFocus({candidateId: focus.candidateId,
        ...(typeof focus.occupationCode === "string" ? {occupationCode: focus.occupationCode} : {}),
        ...(typeof focus.evidenceId === "string" ? {evidenceId: focus.evidenceId} : {})});
    };
    const dispose = () => {
      instance.current?.off("click", click);
      instance.current?.dispose();
      instance.current = null;
    };
    const fail = (cause: unknown) => {
      if (removed) return;
      failed = true;
      dispose();
      setError(true);
      latest.current.onError?.(cause instanceof Error ? cause : new Error("Chart unavailable"));
    };
    const apply = () => {
      if (removed || failed || !instance.current || !measureText || !element.clientWidth || !element.clientHeight) return;
      try {instance.current.setOption(themedOption(latest.current.option, element.clientWidth, measureText), {notMerge: true});}
      catch (cause) {fail(cause);}
    };
    const size = async () => {
      if (removed || failed || !element.clientWidth || !element.clientHeight) return;
      if (instance.current) {
        try {instance.current.resize(); apply();} catch (cause) {fail(cause);}
        return;
      }
      if (loading) return;
      loading = true;
      try {
        const [core, charts, components, renderers] = await Promise.all([
          import("echarts/core"), import("echarts/charts"), import("echarts/components"), import("echarts/renderers"),
        ]);
        if (removed || !element.clientWidth || !element.clientHeight) return;
        measureText = (text) => core.format.getTextRect(text).width;
        core.use([charts.BarChart, charts.ScatterChart, charts.HeatmapChart, components.GridComponent,
          components.DatasetComponent, components.TooltipComponent, components.VisualMapComponent,
          components.AriaComponent, renderers.SVGRenderer]);
        instance.current = core.init(element, undefined, {renderer: "svg"});
        instance.current.on("click", click);
        apply();
      } catch (cause) {fail(cause);}
      finally {loading = false;}
    };
    redraw.current = apply;
    const observer = new ResizeObserver(() => {void size();});
    observer.observe(element);
    const theme = new MutationObserver(apply);
    theme.observe(document.documentElement, {attributes: true, attributeFilter: ["class", "data-theme"]});
    void size();
    return () => {
      removed = true;
      redraw.current = null;
      observer.disconnect();
      theme.disconnect();
      dispose();
    };
  }, []);

  return <div className="space-y-2">
    <div ref={container} role="img" aria-label={label} className={cn("h-96 min-w-0 w-full", className)}/>
    {error && <p role="alert" className="text-sm text-destructive">Chart unavailable. Use the values below, Data, or the shortlist to inspect evidence.</p>}
  </div>;
}
