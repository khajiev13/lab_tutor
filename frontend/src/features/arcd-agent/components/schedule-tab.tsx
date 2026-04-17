
import { useMemo, useState } from "react";
import type React from "react";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type {
  StudentPortfolio,
  SkillInfo,
  LearningSchedule,
  LearningPath,
  LearningPathStep,
  StudentEvent,
} from "@/features/arcd-agent/lib/types";
import { buildSubSkillNameMap } from "@/features/arcd-agent/lib/types";
import { SKILL_HEX } from "@/features/arcd-agent/lib/colors";
import { masteryTierColor } from "@/features/arcd-agent/lib/colors";
import { CalendarDays, BookOpen, Zap, Flame } from "lucide-react";
import { Button } from "@/components/ui/button";

const DEFAULT_MINUTES_PER_STEP = 20;
const DEFAULT_MINUTES_PER_DAY = 30;
const EVENT_TYPES: StudentEvent["event_type"][] = ["exam", "assignment", "busy", "study", "other"];
const API_BASE =
  import.meta.env.VITE_API_URL ||
  (import.meta.env.PROD
    ? ""
    : `http://${typeof window !== "undefined" ? window.location.hostname : "localhost"}:8000`);

function buildFallbackSchedule(
  path: LearningPath | undefined,
  startDate: Date
): LearningSchedule | null {
  if (!path?.steps?.length) return null;
  const schedule: { date: string; sessions: LearningPathStep[]; total_minutes: number }[] = [];
  let currentDate = new Date(startDate);
  currentDate.setHours(0, 0, 0, 0);
  let daySessions: LearningPathStep[] = [];
  let dayMinutes = 0;

  for (const step of path.steps) {
    const stepMins = step.action_plan?.estimated_minutes ?? DEFAULT_MINUTES_PER_STEP;
    if (dayMinutes + stepMins > DEFAULT_MINUTES_PER_DAY && daySessions.length > 0) {
      schedule.push({ date: currentDate.toISOString().slice(0, 10), sessions: daySessions, total_minutes: dayMinutes });
      currentDate = new Date(currentDate);
      currentDate.setDate(currentDate.getDate() + 1);
      daySessions = [];
      dayMinutes = 0;
    }
    daySessions.push(step);
    dayMinutes += stepMins;
  }
  if (daySessions.length > 0) {
    schedule.push({ date: currentDate.toISOString().slice(0, 10), sessions: daySessions, total_minutes: dayMinutes });
  }
  return { schedule, review_calendar: [], study_guide: "", study_minutes_per_day: DEFAULT_MINUTES_PER_DAY };
}

const SESSION_TYPE_LABEL: Record<string, string> = {
  guided_learning: "Guided",
  deliberate_practice: "Practice",
  challenge: "Challenge",
  spaced_review: "Review",
  prerequisite_remediation: "Prereq",
  deep_diagnostic: "Diagnostic",
};

function resolveSkillName(
  skillId: number,
  rawName: string,
  skills: SkillInfo[],
  nameMap: Record<number, string>
): string {
  if (rawName && !rawName.match(/^Skill \d+$/)) return rawName;
  if (nameMap[skillId]) return nameMap[skillId];
  const domain = skills.find((s) => s.id === skillId);
  if (domain) return domain.name;
  return rawName || `Skill ${skillId}`;
}

interface ScheduleTabProps {
  student: StudentPortfolio;
  skills: SkillInfo[];
  onRefresh?: () => void;
}

export function ScheduleTab({ student, skills, onRefresh }: ScheduleTabProps) {
  const path = student.learning_path;
  const today = useMemo(() => new Date(), []);
  const schedule: LearningSchedule | null | undefined = useMemo(
    () => path?.learning_schedule ?? (path ? buildFallbackSchedule(path, today) : null),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [path, today.toDateString()]
  );
  const nameMap = buildSubSkillNameMap(skills);
  const isFallback = path && !path.learning_schedule && schedule != null;
  const [showEventForm, setShowEventForm] = useState(false);
  const [eventLoading, setEventLoading] = useState(false);
  const [eventError, setEventError] = useState<string | null>(null);
  const [eventForm, setEventForm] = useState({
    date: new Date().toISOString().slice(0, 10),
    title: "",
    event_type: "other" as StudentEvent["event_type"],
    duration_minutes: "",
    notes: "",
  });

  // ── Activity heatmap from timeline ──────────────────────────────────────
  const activityMap = useMemo(() => {
    const map: Record<string, number> = {};
    for (const e of student.timeline) {
      if (!e.timestamp) continue;
      const day = e.timestamp.slice(0, 10);
      map[day] = (map[day] ?? 0) + 1;
    }
    return map;
  }, [student.timeline]);

  // Build last 12 weeks of dates
  const heatmapWeeks = useMemo(() => {
    const weeks: string[][] = [];
    const end = new Date(today);
    end.setHours(0, 0, 0, 0);
    // Go back to last Sunday
    const startOfLastSun = new Date(end);
    startOfLastSun.setDate(end.getDate() - end.getDay());
    // 12 weeks = 84 days
    const start = new Date(startOfLastSun);
    start.setDate(start.getDate() - 11 * 7);

    const cur = new Date(start);
    let week: string[] = [];
    while (cur <= end) {
      week.push(cur.toISOString().slice(0, 10));
      if (week.length === 7) {
        weeks.push(week);
        week = [];
      }
      cur.setDate(cur.getDate() + 1);
    }
    if (week.length > 0) weeks.push(week);
    return weeks;
  }, [today]);

  const maxActivity = useMemo(
    () => Math.max(1, ...Object.values(activityMap)),
    [activityMap]
  );

  const activeDays = Object.keys(activityMap).length;
  const todayStr = today.toISOString().slice(0, 10);
  const todayActivity = activityMap[todayStr] ?? 0;

  // ── Today's plan from schedule ──────────────────────────────────────────
  const todaySchedule = schedule?.schedule?.find((d) => d.date === todayStr)
    ?? schedule?.schedule?.[0]; // fallback to first day

  const allStudentEvents = useMemo(() => {
    const byId = new Map<string, StudentEvent>();
    const rootEvents = schedule?.student_events ?? [];
    for (const event of rootEvents) {
      if (event?.id) byId.set(event.id, event);
    }
    for (const day of schedule?.schedule ?? []) {
      for (const event of day.student_events ?? []) {
        if (event?.id) byId.set(event.id, event);
      }
    }
    return [...byId.values()].sort((a, b) => a.date.localeCompare(b.date));
  }, [schedule]);

  const eventMapByDate = useMemo(() => {
    const map: Record<string, StudentEvent[]> = {};
    for (const event of allStudentEvents) {
      if (!map[event.date]) map[event.date] = [];
      map[event.date].push(event);
    }
    return map;
  }, [allStudentEvents]);

  const eventBadgeClass = (eventType: StudentEvent["event_type"]) => {
    if (eventType === "exam") return "bg-red-100 text-red-700 dark:bg-red-950/30 dark:text-red-300";
    if (eventType === "assignment") return "bg-amber-100 text-amber-700 dark:bg-amber-950/30 dark:text-amber-300";
    if (eventType === "busy") return "bg-slate-100 text-slate-700 dark:bg-slate-900/50 dark:text-slate-300";
    if (eventType === "study") return "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300";
    return "bg-blue-100 text-blue-700 dark:bg-blue-950/30 dark:text-blue-300";
  };

  const handleAddEvent = async () => {
    setEventError(null);
    if (!eventForm.title.trim()) {
      setEventError("Event title is required.");
      return;
    }
    setEventLoading(true);
    try {
      const token = localStorage.getItem("access_token");
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers.Authorization = `Bearer ${token}`;
      const durationRaw = eventForm.duration_minutes.trim();
      const payload = {
        date: eventForm.date,
        title: eventForm.title.trim(),
        event_type: eventForm.event_type,
        duration_minutes: durationRaw ? Number(durationRaw) : null,
        notes: eventForm.notes.trim(),
      };
      const resp = await fetch(`${API_BASE}/diagnosis/student-events`, {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
      });
      if (!resp.ok) throw new Error(`Failed to create event (${resp.status})`);
      setShowEventForm(false);
      setEventForm({
        date: new Date().toISOString().slice(0, 10),
        title: "",
        event_type: "other",
        duration_minutes: "",
        notes: "",
      });
      onRefresh?.();
    } catch (e: unknown) {
      setEventError(e instanceof Error ? e.message : "Failed to create event");
    } finally {
      setEventLoading(false);
    }
  };

  const [selectedDate, setSelectedDate] = useState(todayStr);
  const [calView, setCalView] = useState<"day" | "week" | "month">("day");
  const [calMonth, setCalMonth] = useState(() => {
    const d = new Date(today);
    d.setDate(1);
    return d;
  });

  // Derive the mini / full calendar month grid
  const calGrid = useMemo(() => {
    const year = calMonth.getFullYear();
    const month = calMonth.getMonth();
    const firstDay = new Date(year, month, 1).getDay(); // 0=Sun
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const days: (string | null)[] = Array(firstDay).fill(null);
    for (let d = 1; d <= daysInMonth; d++) {
      const dateStr = `${year}-${String(month + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      days.push(dateStr);
    }
    while (days.length % 7 !== 0) days.push(null);
    return days;
  }, [calMonth]);

  const calMonthLabel = calMonth.toLocaleDateString(undefined, { month: "long", year: "numeric" });

  const prevMonth = () => setCalMonth((m) => { const d = new Date(m); d.setMonth(d.getMonth() - 1); return d; });
  const nextMonth = () => setCalMonth((m) => { const d = new Date(m); d.setMonth(d.getMonth() + 1); return d; });

  // Week view — 7 days starting from the Monday of the selected date's week
  const weekDates = useMemo(() => {
    const base = new Date(selectedDate + "T00:00:00");
    const dow = base.getDay(); // 0=Sun
    const monday = new Date(base);
    monday.setDate(base.getDate() - ((dow + 6) % 7)); // shift to Mon
    return Array.from({ length: 7 }, (_, i) => {
      const d = new Date(monday);
      d.setDate(monday.getDate() + i);
      return d.toISOString().slice(0, 10);
    });
  }, [selectedDate]);

  const prevWeek = () => {
    setSelectedDate((sd) => {
      const d = new Date(sd + "T00:00:00");
      d.setDate(d.getDate() - 7);
      return d.toISOString().slice(0, 10);
    });
  };
  const nextWeek = () => {
    setSelectedDate((sd) => {
      const d = new Date(sd + "T00:00:00");
      d.setDate(d.getDate() + 7);
      return d.toISOString().slice(0, 10);
    });
  };

  // Build a set of scheduled session dates and review dates for dot display
  const sessionDateSet = useMemo(() => {
    const s = new Set<string>();
    for (const day of schedule?.schedule ?? []) s.add(day.date);
    return s;
  }, [schedule]);
  const reviewDateSet = useMemo(() => new Set((schedule?.review_calendar) ?? []), [schedule]);

  if (!schedule || !schedule.schedule?.length) {
    return (
      <div className="text-center py-16 text-muted-foreground">
        <p className="text-lg font-medium">No learning schedule yet</p>
        <p className="text-sm mt-2">
          We have not generated a personalized schedule yet. Generate or refresh your learning path,
          then come back to see an up-to-date day-by-day plan.
        </p>
        {onRefresh && (
          <Button size="sm" variant="outline" className="mt-4" onClick={onRefresh}>
            Refresh schedule
          </Button>
        )}
      </div>
    );
  }

  const { study_guide, study_minutes_per_day } = schedule;

  return (
    <div className="space-y-6">
      {isFallback && (
        <Card className="border-amber-200 bg-amber-50/50 dark:border-amber-900 dark:bg-amber-950/20">
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">
              This schedule is inferred from your current learning path and the latest mastery data.
              Some sessions may still use default timing while richer planning signals are generated.
            </p>
            {onRefresh && (
              <div className="mt-3">
                <Button size="sm" variant="outline" onClick={onRefresh}>
                  Sync with latest pipeline data
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* ── Merged Today's Plan + Study Guide ──────────────────────────── */}
      {(todaySchedule || study_guide) && (
        <Card className="border-primary/30 bg-gradient-to-r from-primary/5 to-primary/10">
          <CardHeader className="pb-2">
            <div className="flex items-center gap-2">
              <div className="p-2 rounded-full bg-primary/15">
                <Zap className="h-4 w-4 text-primary" />
              </div>
              <div>
                <CardTitle className="text-base">Today's Plan &amp; Study Guide</CardTitle>
                <CardDescription>
                  {todaySchedule
                    ? `${todaySchedule.sessions.length} skill${todaySchedule.sessions.length !== 1 ? "s" : ""} · ~${todaySchedule.total_minutes} min`
                    : "No sessions scheduled today"}
                  {study_minutes_per_day ? ` · ${study_minutes_per_day} min/day target` : ""}
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {/* Today's sessions */}
            {todaySchedule && (
              <div className="space-y-2">
                {todaySchedule.sessions.map((step) => {
                  const displayName = resolveSkillName(step.skill_id, step.skill_name, skills, nameMap);
                  const color = masteryTierColor(step.current_mastery ?? 0);
                  return (
                    <div key={step.rank} className="flex items-center gap-3 rounded-lg border border-border/60 bg-background p-3">
                      <div
                        className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-bold"
                        style={{ backgroundColor: color }}
                      >
                        {step.rank}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-sm truncate">{displayName}</p>
                        <p className="text-xs text-muted-foreground">
                          {step.action_plan?.session_type
                            ? SESSION_TYPE_LABEL[step.action_plan.session_type] ?? step.action_plan.session_type
                            : "Study"}
                          {step.action_plan?.estimated_minutes ? ` · ~${step.action_plan.estimated_minutes} min` : ""}
                        </p>
                      </div>
                      {step.current_mastery !== undefined && (
                        <span className="text-xs font-mono text-muted-foreground shrink-0">
                          {(step.current_mastery * 100).toFixed(0)}%
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
            {/* Study Guide linked below */}
            {study_guide && (
              <div className="rounded-lg border border-border/50 bg-background/60 p-3">
                <p className="text-xs font-semibold text-muted-foreground flex items-center gap-1.5 mb-1.5">
                  <BookOpen className="h-3.5 w-3.5" />
                  Study Guide
                </p>
                <p className="text-sm leading-relaxed whitespace-pre-wrap">{study_guide}</p>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* ── Activity Heatmap ────────────────────────────────────────────── */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Flame className={`h-4 w-4 ${activeDays > 0 ? "text-amber-500" : "text-muted-foreground"}`} />
              <CardTitle className="text-base">Study Activity</CardTitle>
            </div>
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <span>{activeDays} active days</span>
              {todayActivity > 0 && (
                <Badge className="bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300 text-[10px]">
                  {todayActivity} today
                </Badge>
              )}
            </div>
          </div>
          <CardDescription>Last 12 weeks — darker = more interactions</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex gap-1 overflow-x-auto pb-1">
            {heatmapWeeks.map((week, wi) => (
              <div key={wi} className="flex flex-col gap-1">
                {week.map((day) => {
                  const count = activityMap[day] ?? 0;
                  const intensity = count > 0 ? Math.min(1, count / maxActivity) : 0;
                  const isToday = day === todayStr;
                  const bg =
                    count === 0
                      ? "bg-muted/50"
                      : intensity < 0.25
                      ? "bg-emerald-200 dark:bg-emerald-900/50"
                      : intensity < 0.5
                      ? "bg-emerald-400 dark:bg-emerald-700/70"
                      : intensity < 0.75
                      ? "bg-emerald-500 dark:bg-emerald-600"
                      : "bg-emerald-600 dark:bg-emerald-500";
                  return (
                    <div
                      key={day}
                      title={`${day}: ${count} interactions`}
                      className={`w-3.5 h-3.5 rounded-sm transition-opacity ${bg} ${isToday ? "ring-2 ring-primary ring-offset-1" : ""}`}
                    />
                  );
                })}
              </div>
            ))}
          </div>
          <div className="flex items-center justify-end gap-1.5 mt-2 text-[10px] text-muted-foreground">
            <span>Less</span>
            {["bg-muted/50", "bg-emerald-200 dark:bg-emerald-900/50", "bg-emerald-400 dark:bg-emerald-700/70", "bg-emerald-600 dark:bg-emerald-500"].map((bg, i) => (
              <div key={i} className={`w-2.5 h-2.5 rounded-sm ${bg}`} />
            ))}
            <span>More</span>
          </div>
        </CardContent>
      </Card>

      {/* ── Calendar Views ──────────────────────────────────────────────── */}
      <div className="space-y-3">
        {/* View toggle */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1 rounded-lg border border-border/60 bg-muted/20 p-0.5">
            {(["day", "week", "month"] as const).map((v) => (
              <button
                key={v}
                onClick={() => setCalView(v)}
                className={`px-4 py-1.5 rounded-md text-xs font-medium transition-colors ${
                  calView === v
                    ? "bg-background text-foreground shadow-sm border border-border/40"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {v.charAt(0).toUpperCase() + v.slice(1)}
              </button>
            ))}
          </div>

          {/* Navigation */}
          <div className="flex items-center gap-1.5 text-sm font-medium">
            <button
              onClick={calView === "week" ? prevWeek : prevMonth}
              className="px-2 py-1 rounded hover:bg-muted/60 text-muted-foreground hover:text-foreground"
              aria-label="Previous"
            >‹</button>
            <span className="min-w-[160px] text-center text-sm font-semibold">
              {calView === "week"
                ? `${new Date(weekDates[0] + "T00:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" })} – ${new Date(weekDates[6] + "T00:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}`
                : calMonthLabel}
            </span>
            <button
              onClick={calView === "week" ? nextWeek : nextMonth}
              className="px-2 py-1 rounded hover:bg-muted/60 text-muted-foreground hover:text-foreground"
              aria-label="Next"
            >›</button>
          </div>
        </div>

        {/* ── DAY VIEW ── */}
        {calView === "day" && (
          <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
            {/* Mini calendar sidebar */}
            <Card className="h-fit">
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <button className="text-sm font-semibold hover:text-primary transition-colors" onClick={prevMonth} aria-label="Previous month">‹</button>
                  <span className="text-sm font-semibold">{calMonthLabel}</span>
                  <button className="text-sm font-semibold hover:text-primary transition-colors" onClick={nextMonth} aria-label="Next month">›</button>
                </div>
              </CardHeader>
              <CardContent className="p-2 pt-0">
                <div className="grid grid-cols-7 mb-1">
                  {["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"].map((d) => (
                    <div key={d} className="text-center text-[10px] font-medium text-muted-foreground py-1">{d}</div>
                  ))}
                </div>
                <div className="grid grid-cols-7 gap-y-0.5">
                  {calGrid.map((dateStr, i) => {
                    if (!dateStr) return <div key={`empty-${i}`} />;
                    const dayNum = parseInt(dateStr.split("-")[2], 10);
                    const isToday = dateStr === todayStr;
                    const isSelected = dateStr === selectedDate;
                    const hasSessions = sessionDateSet.has(dateStr);
                    const hasReview = reviewDateSet.has(dateStr);
                    const hasEvent = (eventMapByDate[dateStr]?.length ?? 0) > 0;
                    return (
                      <button
                        key={dateStr}
                        onClick={() => setSelectedDate(dateStr)}
                        className={`relative flex flex-col items-center justify-center py-1.5 rounded-lg text-xs transition-colors ${
                          isSelected ? "bg-primary text-primary-foreground font-bold"
                          : isToday ? "ring-2 ring-primary text-primary font-semibold"
                          : "hover:bg-muted/50 text-foreground"
                        }`}
                      >
                        <span>{dayNum}</span>
                        <div className="flex gap-0.5 mt-0.5 h-1.5">
                          {hasSessions && <span className={`w-1 h-1 rounded-full ${isSelected ? "bg-primary-foreground" : "bg-primary"}`} />}
                          {hasReview && <span className={`w-1 h-1 rounded-full ${isSelected ? "bg-primary-foreground/70" : "bg-violet-500"}`} />}
                          {hasEvent && <span className={`w-1 h-1 rounded-full ${isSelected ? "bg-primary-foreground/70" : "bg-red-500"}`} />}
                        </div>
                      </button>
                    );
                  })}
                </div>
                <div className="mt-3 pt-2 border-t border-border/40 space-y-1">
                  <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground"><span className="w-1.5 h-1.5 rounded-full bg-primary shrink-0" />Sessions</div>
                  <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground"><span className="w-1.5 h-1.5 rounded-full bg-violet-500 shrink-0" />Review</div>
                  <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground"><span className="w-1.5 h-1.5 rounded-full bg-red-500 shrink-0" />Event</div>
                </div>
              </CardContent>
            </Card>

            {/* Day detail */}
            <DayDetailCard
              date={selectedDate}
              todayStr={todayStr}
              reviewDateSet={reviewDateSet}
              schedule={schedule}
              skills={skills}
              nameMap={nameMap}
              eventMapByDate={eventMapByDate}
              eventBadgeClass={eventBadgeClass}
              showEventForm={showEventForm}
              setShowEventForm={setShowEventForm}
              eventForm={eventForm}
              setEventForm={setEventForm}
              eventError={eventError}
              eventLoading={eventLoading}
              handleAddEvent={handleAddEvent}
            />
          </div>
        )}

        {/* ── WEEK VIEW ── */}
        {calView === "week" && (
          <div className="grid grid-cols-7 gap-1.5">
            {weekDates.map((dateStr) => {
              const isToday = dateStr === todayStr;
              const isSelected = dateStr === selectedDate;
              const daySchedule = schedule.schedule?.find((d) => d.date === dateStr);
              const dayEvents = eventMapByDate[dateStr] ?? [];
              const dayLabel = new Date(dateStr + "T00:00:00").toLocaleDateString(undefined, { weekday: "short", day: "numeric" });
              return (
                <button
                  key={dateStr}
                  onClick={() => { setSelectedDate(dateStr); setCalView("day"); }}
                  className={`text-left rounded-xl border p-2 min-h-[120px] flex flex-col gap-1 transition-colors hover:bg-muted/40 ${
                    isSelected ? "border-primary bg-primary/5"
                    : isToday ? "border-primary/50 bg-primary/5"
                    : "border-border/50"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className={`text-xs font-semibold ${isToday ? "text-primary" : "text-muted-foreground"}`}>{dayLabel}</span>
                    {isToday && <span className="w-1.5 h-1.5 rounded-full bg-primary" />}
                  </div>
                  {daySchedule && (
                    <div className="space-y-0.5 flex-1">
                      {daySchedule.sessions.slice(0, 4).map((step) => {
                        const name = resolveSkillName(step.skill_id, step.skill_name, skills, nameMap);
                        const color = SKILL_HEX[step.skill_id % SKILL_HEX.length];
                        return (
                          <div key={step.rank} className="flex items-center gap-1">
                            <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: color }} />
                            <span className="text-[10px] truncate leading-tight">{name}</span>
                          </div>
                        );
                      })}
                      {daySchedule.sessions.length > 4 && (
                        <p className="text-[10px] text-muted-foreground">+{daySchedule.sessions.length - 4} more</p>
                      )}
                      <p className="text-[10px] text-muted-foreground mt-auto">~{daySchedule.total_minutes} min</p>
                    </div>
                  )}
                  {dayEvents.length > 0 && (
                    <div className="flex flex-wrap gap-0.5 mt-auto">
                      {dayEvents.slice(0, 2).map((ev) => (
                        <span key={ev.id} className={`text-[9px] px-1 rounded-sm ${eventBadgeClass(ev.event_type)}`}>{ev.title || ev.event_type}</span>
                      ))}
                    </div>
                  )}
                  {!daySchedule && dayEvents.length === 0 && (
                    <p className="text-[10px] text-muted-foreground/50 mt-1">—</p>
                  )}
                </button>
              );
            })}
          </div>
        )}

        {/* ── MONTH VIEW ── */}
        {calView === "month" && (
          <Card>
            <CardContent className="p-3">
              {/* Day-of-week headers */}
              <div className="grid grid-cols-7 mb-1 border-b border-border/40 pb-1">
                {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((d) => (
                  <div key={d} className="text-center text-[11px] font-medium text-muted-foreground py-1">{d}</div>
                ))}
              </div>
              {/* Day cells */}
              <div className="grid grid-cols-7 gap-px">
                {calGrid.map((dateStr, i) => {
                  if (!dateStr) return <div key={`empty-${i}`} className="min-h-[80px]" />;
                  const dayNum = parseInt(dateStr.split("-")[2], 10);
                  const isToday = dateStr === todayStr;
                  const isSelected = dateStr === selectedDate;
                  const daySchedule = schedule.schedule?.find((d) => d.date === dateStr);
                  const dayEvents = eventMapByDate[dateStr] ?? [];
                  const inCurrentMonth = dateStr.startsWith(
                    `${calMonth.getFullYear()}-${String(calMonth.getMonth() + 1).padStart(2, "0")}`
                  );
                  return (
                    <button
                      key={dateStr}
                      onClick={() => { setSelectedDate(dateStr); setCalView("day"); }}
                      className={`text-left rounded-lg p-1.5 min-h-[80px] flex flex-col gap-0.5 transition-colors hover:bg-muted/40 ${
                        isSelected ? "bg-primary/10 ring-1 ring-primary"
                        : isToday ? "ring-1 ring-primary/60"
                        : ""
                      } ${!inCurrentMonth ? "opacity-40" : ""}`}
                    >
                      <span className={`text-xs font-semibold w-5 h-5 flex items-center justify-center rounded-full ${
                        isToday ? "bg-primary text-primary-foreground" : "text-muted-foreground"
                      }`}>{dayNum}</span>
                      {daySchedule && daySchedule.sessions.slice(0, 2).map((step) => {
                        const name = resolveSkillName(step.skill_id, step.skill_name, skills, nameMap);
                        const color = SKILL_HEX[step.skill_id % SKILL_HEX.length];
                        return (
                          <div key={step.rank} className="flex items-center gap-1 w-full">
                            <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: color }} />
                            <span className="text-[9px] truncate">{name}</span>
                          </div>
                        );
                      })}
                      {(daySchedule?.sessions.length ?? 0) > 2 && (
                        <span className="text-[9px] text-muted-foreground">+{daySchedule!.sessions.length - 2} more</span>
                      )}
                      {dayEvents.slice(0, 1).map((ev) => (
                        <span key={ev.id} className={`text-[9px] px-1 rounded-sm truncate w-full ${eventBadgeClass(ev.event_type)}`}>{ev.title || ev.event_type}</span>
                      ))}
                    </button>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

// ── DayDetailCard ────────────────────────────────────────────────────────────
interface DayDetailCardProps {
  date: string;
  todayStr: string;
  reviewDateSet: Set<string>;
  schedule: LearningSchedule;
  skills: SkillInfo[];
  nameMap: Record<number, string>;
  eventMapByDate: Record<string, StudentEvent[]>;
  eventBadgeClass: (t: StudentEvent["event_type"]) => string;
  showEventForm: boolean;
  setShowEventForm: React.Dispatch<React.SetStateAction<boolean>>;
  eventForm: {
    date: string; title: string;
    event_type: StudentEvent["event_type"];
    duration_minutes: string; notes: string;
  };
  setEventForm: React.Dispatch<React.SetStateAction<DayDetailCardProps["eventForm"]>>;
  eventError: string | null;
  eventLoading: boolean;
  handleAddEvent: () => void;
}

function DayDetailCard({
  date, todayStr, reviewDateSet, schedule, skills, nameMap,
  eventMapByDate, eventBadgeClass,
  showEventForm, setShowEventForm, eventForm, setEventForm,
  eventError, eventLoading, handleAddEvent,
}: DayDetailCardProps) {
  const daySchedule = schedule.schedule?.find((d) => d.date === date) ?? null;
  const isToday = date === todayStr;

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <CalendarDays className="h-4 w-4 text-muted-foreground" />
            <CardTitle className="text-base">
              {isToday ? "Today" : new Date(date + "T00:00:00").toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })}
            </CardTitle>
            {isToday && <Badge className="text-[10px] bg-primary text-primary-foreground">Today</Badge>}
            {reviewDateSet.has(date) && (
              <Badge className="text-[10px] bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300">Review Day</Badge>
            )}
          </div>
          <Button size="sm" variant="outline" onClick={() => setShowEventForm((v) => !v)}>
            {showEventForm ? "Close" : "Add Event"}
          </Button>
        </div>
        <CardDescription>
          {daySchedule
            ? `${daySchedule.sessions.length} session${daySchedule.sessions.length !== 1 ? "s" : ""} · ~${daySchedule.total_minutes} min`
            : "No sessions scheduled"}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {showEventForm && (
          <div className="rounded-lg border p-3 space-y-3 bg-muted/20">
            <div className="grid gap-2 sm:grid-cols-2">
              <input type="date" className="h-9 rounded border bg-background px-2 text-sm"
                value={eventForm.date} onChange={(e) => setEventForm((p) => ({ ...p, date: e.target.value }))} />
              <input type="text" className="h-9 rounded border bg-background px-2 text-sm"
                placeholder="Event title" value={eventForm.title}
                onChange={(e) => setEventForm((p) => ({ ...p, title: e.target.value }))} />
              <select className="h-9 rounded border bg-background px-2 text-sm"
                value={eventForm.event_type}
                onChange={(e) => setEventForm((p) => ({ ...p, event_type: e.target.value as StudentEvent["event_type"] }))}>
                {EVENT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
              <input type="number" min={0} max={1440} className="h-9 rounded border bg-background px-2 text-sm"
                placeholder="Duration (minutes)" value={eventForm.duration_minutes}
                onChange={(e) => setEventForm((p) => ({ ...p, duration_minutes: e.target.value }))} />
            </div>
            <input type="text" className="h-9 w-full rounded border bg-background px-2 text-sm"
              placeholder="Notes (optional)" value={eventForm.notes}
              onChange={(e) => setEventForm((p) => ({ ...p, notes: e.target.value }))} />
            {eventError && <p className="text-xs text-red-600">{eventError}</p>}
            <div className="flex justify-end">
              <Button size="sm" onClick={handleAddEvent} disabled={eventLoading}>
                {eventLoading ? "Saving..." : "Save event"}
              </Button>
            </div>
          </div>
        )}

        {(eventMapByDate[date]?.length ?? 0) > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {(eventMapByDate[date] ?? []).map((event) => (
              <Badge key={event.id} className={`text-xs ${eventBadgeClass(event.event_type)}`}>
                {event.title || event.event_type}
              </Badge>
            ))}
          </div>
        )}

        {daySchedule ? (
          <ul className="space-y-2">
            {daySchedule.sessions.map((step) => {
              const displayName = resolveSkillName(step.skill_id, step.skill_name, skills, nameMap);
              const color = SKILL_HEX[step.skill_id % SKILL_HEX.length];
              const ap = step.action_plan;
              return (
                <li key={step.rank} className="flex items-start gap-2 text-sm rounded-lg border border-border/50 p-3">
                  <span className="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-white text-xs font-bold"
                    style={{ backgroundColor: color }}>
                    {step.rank}
                  </span>
                  <div className="min-w-0 flex-1">
                    <span className="font-medium">{displayName}</span>
                    {ap && (
                      <>
                        {ap.session_type && (
                          <Badge variant="outline" className="ml-2 text-[10px]">
                            {SESSION_TYPE_LABEL[ap.session_type] ?? ap.session_type}
                          </Badge>
                        )}
                        {ap.estimated_minutes != null && (
                          <span className="ml-2 text-muted-foreground text-xs">~{ap.estimated_minutes} min</span>
                        )}
                        {ap.success_criteria && (
                          <p className="text-xs text-muted-foreground mt-0.5">{ap.success_criteria}</p>
                        )}
                      </>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground py-6 text-center">No sessions scheduled for this day.</p>
        )}
      </CardContent>
    </Card>
  );
}
