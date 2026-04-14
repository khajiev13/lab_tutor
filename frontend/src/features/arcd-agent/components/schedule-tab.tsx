
import { useMemo, useState } from "react";
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

  // ── 7-day forecast ──────────────────────────────────────────────────────
  const nextSevenDays = useMemo(() => {
    if (!schedule?.schedule) return [];
    const result = [];
    for (let i = 0; i < 7; i++) {
      const d = new Date(today);
      d.setDate(today.getDate() + i);
      const dateStr = d.toISOString().slice(0, 10);
      const scheduled = schedule.schedule.find((s) => s.date === dateStr);
      result.push({
        date: dateStr,
        label: i === 0 ? "Today" : i === 1 ? "Tomorrow" : d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" }),
        sessions: scheduled?.sessions ?? [],
        minutes: scheduled?.total_minutes ?? 0,
        isToday: i === 0,
      });
    }
    return result;
  }, [schedule, today]);

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

  const { schedule: days, review_calendar, study_guide, study_minutes_per_day } = schedule;

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

      {/* ── Today's Plan hero ───────────────────────────────────────────── */}
      {todaySchedule && (
        <Card className="border-primary/30 bg-gradient-to-r from-primary/5 to-primary/10">
          <CardHeader className="pb-2">
            <div className="flex items-center gap-2">
              <div className="p-2 rounded-full bg-primary/15">
                <Zap className="h-4 w-4 text-primary" />
              </div>
              <div>
                <CardTitle className="text-base">Today's Plan</CardTitle>
                <CardDescription>
                  {todaySchedule.sessions.length} skill{todaySchedule.sessions.length !== 1 ? "s" : ""} · ~{todaySchedule.total_minutes} min
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-2">
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

      {/* ── 7-Day Forecast ──────────────────────────────────────────────── */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <CalendarDays className="h-4 w-4 text-muted-foreground" />
              <CardTitle className="text-base">7-Day Forecast</CardTitle>
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setShowEventForm((v) => !v)}
            >
              {showEventForm ? "Close" : "Add Event"}
            </Button>
          </div>
          <CardDescription>Upcoming sessions based on your learning path</CardDescription>
        </CardHeader>
        <CardContent>
          {showEventForm && (
            <div className="mb-4 rounded-lg border p-3 space-y-3 bg-muted/20">
              <div className="grid gap-2 sm:grid-cols-2">
                <input
                  type="date"
                  className="h-9 rounded border bg-background px-2 text-sm"
                  value={eventForm.date}
                  onChange={(e) => setEventForm((prev) => ({ ...prev, date: e.target.value }))}
                />
                <input
                  type="text"
                  className="h-9 rounded border bg-background px-2 text-sm"
                  placeholder="Event title"
                  value={eventForm.title}
                  onChange={(e) => setEventForm((prev) => ({ ...prev, title: e.target.value }))}
                />
                <select
                  className="h-9 rounded border bg-background px-2 text-sm"
                  value={eventForm.event_type}
                  onChange={(e) =>
                    setEventForm((prev) => ({ ...prev, event_type: e.target.value as StudentEvent["event_type"] }))
                  }
                >
                  {EVENT_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {type}
                    </option>
                  ))}
                </select>
                <input
                  type="number"
                  min={0}
                  max={1440}
                  className="h-9 rounded border bg-background px-2 text-sm"
                  placeholder="Duration (minutes)"
                  value={eventForm.duration_minutes}
                  onChange={(e) => setEventForm((prev) => ({ ...prev, duration_minutes: e.target.value }))}
                />
              </div>
              <input
                type="text"
                className="h-9 w-full rounded border bg-background px-2 text-sm"
                placeholder="Notes (optional)"
                value={eventForm.notes}
                onChange={(e) => setEventForm((prev) => ({ ...prev, notes: e.target.value }))}
              />
              {eventError && <p className="text-xs text-red-600">{eventError}</p>}
              <div className="flex justify-end">
                <Button size="sm" onClick={handleAddEvent} disabled={eventLoading}>
                  {eventLoading ? "Saving..." : "Save event"}
                </Button>
              </div>
            </div>
          )}
          <div className="grid gap-2 sm:grid-cols-7">
            {nextSevenDays.map((day) => (
              <div
                key={day.date}
                className={`rounded-lg border p-2 text-center transition-colors ${
                  day.isToday
                    ? "border-primary/40 bg-primary/5"
                    : day.sessions.length > 0
                    ? "border-border bg-card"
                    : "border-border/40 bg-muted/20 opacity-60"
                }`}
              >
                <p className={`text-[10px] font-medium mb-1 truncate ${day.isToday ? "text-primary" : "text-muted-foreground"}`}>
                  {day.label}
                </p>
                {day.sessions.length > 0 ? (
                  <>
                    <p className="text-sm font-bold tabular-nums">{day.sessions.length}</p>
                    <p className="text-[10px] text-muted-foreground">skill{day.sessions.length !== 1 ? "s" : ""}</p>
                    <p className="text-[10px] text-muted-foreground">{day.minutes}m</p>
                    {(eventMapByDate[day.date] ?? []).slice(0, 2).map((event) => (
                      <Badge key={event.id} className={`mt-1 text-[9px] ${eventBadgeClass(event.event_type)}`}>
                        {event.event_type}
                      </Badge>
                    ))}
                  </>
                ) : (
                  <div className="mt-2 space-y-1">
                    {(eventMapByDate[day.date] ?? []).length === 0 ? (
                      <p className="text-xs text-muted-foreground">—</p>
                    ) : (
                      (eventMapByDate[day.date] ?? []).slice(0, 2).map((event) => (
                        <Badge key={event.id} className={`text-[9px] ${eventBadgeClass(event.event_type)}`}>
                          {event.event_type}
                        </Badge>
                      ))
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Study Guide */}
      {study_guide && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <BookOpen className="h-4 w-4" />
              Study Guide
            </CardTitle>
            <CardDescription>
              Personalized guidance for your learning path ({study_minutes_per_day} min/day)
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm leading-relaxed whitespace-pre-wrap">{study_guide}</p>
          </CardContent>
        </Card>
      )}

      {/* Daily Schedule (full) */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Full Schedule</CardTitle>
          <CardDescription>
            Sessions packed by day (~{study_minutes_per_day} min per day)
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {days.map((day) => (
              <div key={day.date} className="rounded-lg border bg-card p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-sm">
                    {new Date(day.date).toLocaleDateString(undefined, {
                      weekday: "short",
                      month: "short",
                      day: "numeric",
                    })}
                    {day.date === todayStr && (
                      <Badge className="ml-2 bg-primary text-primary-foreground text-[10px]">Today</Badge>
                    )}
                  </span>
                  <Badge variant="secondary" className="text-xs">
                    {day.total_minutes} min
                  </Badge>
                </div>
                <ul className="space-y-2">
                  {day.sessions.map((step) => {
                    const displayName = resolveSkillName(step.skill_id, step.skill_name, skills, nameMap);
                    const color = SKILL_HEX[step.skill_id % SKILL_HEX.length];
                    const ap = step.action_plan;
                    return (
                      <li key={step.rank} className="flex items-start gap-2 text-sm">
                        <span
                          className="flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-white text-xs font-bold"
                          style={{ backgroundColor: color }}
                        >
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
                                <span className="ml-2 text-muted-foreground text-xs">
                                  ~{ap.estimated_minutes} min
                                </span>
                              )}
                              {ap.success_criteria && (
                                <p className="text-xs text-muted-foreground mt-0.5">
                                  {ap.success_criteria}
                                </p>
                              )}
                            </>
                          )}
                        </div>
                      </li>
                    );
                  })}
                </ul>
                {(eventMapByDate[day.date] ?? []).length > 0 && (
                  <div className="pt-1 border-t">
                    <p className="text-[11px] text-muted-foreground mb-1">Planned events</p>
                    <div className="flex flex-wrap gap-1.5">
                      {(eventMapByDate[day.date] ?? []).map((event) => (
                        <Badge key={event.id} className={`text-[10px] ${eventBadgeClass(event.event_type)}`}>
                          {event.title}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {review_calendar && review_calendar.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Review Calendar</CardTitle>
            <CardDescription>Suggested dates to revisit skills (spaced repetition)</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {review_calendar.slice(0, 14).map((d) => (
                <Badge key={d} variant="outline" className="text-xs">
                  {new Date(d).toLocaleDateString()}
                </Badge>
              ))}
              {review_calendar.length > 14 && (
                <span className="text-xs text-muted-foreground">
                  +{review_calendar.length - 14} more
                </span>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
