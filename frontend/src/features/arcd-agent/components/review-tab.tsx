
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, PieChart, Pie, Cell,
} from "recharts";
import {
  Card, CardHeader, CardTitle, CardContent, CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { MathText } from "@/features/arcd-agent/components/math-text";
import type { StudentPortfolio, SkillInfo } from "@/features/arcd-agent/lib/types";
import { buildSubSkillNameMap } from "@/features/arcd-agent/lib/types";
import { SKILL_HEX } from "@/features/arcd-agent/lib/colors";

interface ReviewTabProps {
  student: StudentPortfolio;
  skills: SkillInfo[];
}

const MODE_COLORS = { fast: "#3498db", slow: "#9b59b6" };
const DEVIATION_COLORS = { improved: "#22c55e", declined: "#ef4444" };

export function ReviewSessionAnalytics({ student, skills }: ReviewTabProps) {
  const session = student.review_session;
  const subSkillNames = buildSubSkillNameMap(skills);

  if (!session) {
    return null;
  }

  const pcoCount = (session.pco_skills_detected ?? []).length;
  const fastCount = (session.fast_reviews ?? []).length;
  const slowCount = (session.slow_thinking_plans ?? []).length;
  const rewards = session.rewards ?? { session_points: 0, total_points: 0, current_streak: 0, events_count: 0 };

  const modeData = [
    { name: "Fast Review", value: fastCount, color: MODE_COLORS.fast },
    { name: "Slow Thinking", value: slowCount, color: MODE_COLORS.slow },
  ].filter((d) => d.value > 0);

  const masteryChangeData = (session.mastery_updates ?? [])
    .reduce<Record<number, { old: number; final: number; skill_name: string }>>((acc, u) => {
      if (!acc[u.skill_id]) {
        const name = subSkillNames[u.skill_id] ?? `Skill ${u.skill_id}`;
        acc[u.skill_id] = { old: u.old_mastery, final: u.new_mastery, skill_name: name };
      } else {
        acc[u.skill_id].final = u.new_mastery;
      }
      return acc;
    }, {});

  const changeChartData = Object.entries(masteryChangeData).map(([sid, v]) => ({
    name: v.skill_name.length > 20 ? v.skill_name.slice(0, 18) + "…" : v.skill_name,
    before: +(v.old * 100).toFixed(2),
    after: +(v.final * 100).toFixed(2),
    delta: +((v.final - v.old) * 100).toFixed(2),
    skill_id: Number(sid),
  }));

  return (
    <div className="space-y-6">
      {/* Summary cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>PCO Detected</CardDescription>
            <CardTitle className="text-2xl text-red-500">{pcoCount}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-muted-foreground">Persistent cognitive obstacles</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Fast Reviews</CardDescription>
            <CardTitle className="text-2xl text-blue-500">{fastCount}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-muted-foreground">Flashcard-style questions</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Slow Thinking</CardDescription>
            <CardTitle className="text-2xl text-purple-500">{slowCount}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-muted-foreground">Slow thinking diagnostic plans</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Reward Points</CardDescription>
            <CardTitle className="text-2xl text-amber-500">{rewards.session_points}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-muted-foreground">
              Total: {rewards.total_points} &middot; Streak: {rewards.current_streak}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Replan Needed</CardDescription>
            <CardTitle className={`text-2xl ${session.needs_replan ? "text-orange-500" : "text-emerald-500"}`}>
              {session.needs_replan ? "Yes" : "No"}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-muted-foreground">
              {session.deviations.length} skill(s) deviated
            </p>
          </CardContent>
        </Card>
      </div>

      {/* PCO Skills */}
      {pcoCount > 0 && (
        <Card className="border-red-200">
          <CardHeader>
            <CardTitle className="text-red-600">Persistent Cognitive Obstacles</CardTitle>
            <CardDescription>Skills where the student shows consecutive failure streaks</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {session.pco_skills_detected.map((sid) => {
                const name = subSkillNames[sid] ?? `Skill ${sid}`;
                const color = SKILL_HEX[sid % SKILL_HEX.length];
                return (
                  <Badge
                    key={sid}
                    variant="outline"
                    className="border-red-300 text-red-700"
                    style={{ borderLeftColor: color, borderLeftWidth: 3 }}
                  >
                    {name}
                  </Badge>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Slow Thinking Plans */}
      {session.slow_thinking_plans.length > 0 && (
        <Card className="border-purple-200">
          <CardHeader>
            <CardTitle className="text-purple-700">Slow Thinking Diagnostic Plans</CardTitle>
            <CardDescription>Slow thinking Socratic dialogue plans for PCO resolution</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {session.slow_thinking_plans.map((plan) => (
              <div key={plan.skill_id} className="border rounded-lg p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold">{plan.skill_name}</span>
                    <Badge variant="outline" className="text-[10px]">
                      P_comp: {(plan.comprehension_score * 100).toFixed(2)}%
                    </Badge>
                    <Badge className="bg-purple-100 text-purple-800 text-[10px] hover:bg-purple-100">
                      {plan.difficulty_level}
                    </Badge>
                  </div>
                  <span className="text-xs text-muted-foreground">
                    ~{plan.estimated_duration_minutes} min
                  </span>
                </div>
                <p className="text-sm text-muted-foreground">
                  Weakness: <span className="italic">{plan.identified_weakness}</span>
                </p>
                <div className="flex flex-wrap gap-1">
                  {(plan.concepts ?? []).map((ss, i) => (
                    <Badge key={i} variant="secondary" className="text-[10px]">
                      {ss}
                    </Badge>
                  ))}
                </div>
                <div className="space-y-2 pl-3 border-l-2 border-purple-200">
                  {plan.dialogue_steps.map((step) => (
                    <div key={step.step_num} className="text-sm">
                      <p className="font-medium text-purple-800">
                        Step {step.step_num}: <MathText text={step.prompt ?? ""} />
                      </p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        Expected: <MathText text={step.expected_insight ?? ""} />
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Fast Reviews */}
      {session.fast_reviews.length > 0 && (
        <Card className="border-blue-200">
          <CardHeader>
            <CardTitle className="text-blue-700">Fast Review Questions</CardTitle>
            <CardDescription>Flashcard-style spaced repetition reviews</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {session.fast_reviews.map((item, i) => {
                const color = SKILL_HEX[item.skill_id % SKILL_HEX.length];
                return (
                  <div key={i} className="flex gap-3 p-3 border rounded-lg">
                    <div
                      className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-bold"
                      style={{ backgroundColor: color }}
                    >
                      {i + 1}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-medium text-sm">{item.skill_name}</span>
                        <Badge variant="outline" className="text-[10px]">
                          {item.difficulty}
                        </Badge>
                        <Badge className="bg-blue-100 text-blue-800 text-[10px] hover:bg-blue-100">
                          urg: {typeof item.urgency === "number" ? item.urgency.toFixed(2) : "—"}
                        </Badge>
                      </div>
                      <p className="text-sm mt-1"><MathText text={item.question ?? ""} /></p>
                      {item.hint && (
                        <p className="text-xs text-muted-foreground mt-1 italic">
                          Hint: <MathText text={item.hint ?? ""} />
                        </p>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Mastery changes chart */}
        {changeChartData.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle>Mastery Changes from Review</CardTitle>
              <CardDescription>Before vs after the review session</CardDescription>
            </CardHeader>
            <CardContent className="h-[300px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={changeChartData} layout="vertical" margin={{ left: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.2} />
                  <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 11 }} />
                  <YAxis type="category" dataKey="name" width={130} tick={{ fontSize: 10 }} />
                  <Tooltip
                    formatter={(value: number, name: string) => [
                      `${value}%`,
                      name === "before" ? "Before" : "After",
                    ]}
                    contentStyle={{ borderRadius: "8px", fontSize: "12px" }}
                  />
                  <Legend />
                  <Bar dataKey="before" name="Before" fill="#94a3b8" radius={[0, 3, 3, 0]} />
                  <Bar dataKey="after" name="After" fill="#3b82f6" radius={[0, 3, 3, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        )}

        {/* Review mode distribution */}
        {modeData.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle>Review Mode Distribution</CardTitle>
              <CardDescription>Fast review vs slow thinking breakdown</CardDescription>
            </CardHeader>
            <CardContent className="h-[300px]">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={modeData}
                    cx="50%"
                    cy="50%"
                    labelLine={false}
                    label={({ name, value }) => `${name} (${value})`}
                    outerRadius={100}
                    dataKey="value"
                  >
                    {modeData.map((entry, i) => (
                      <Cell key={i} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        )}
      </div>

      {/* Deviations */}
      {session.deviations.length > 0 && (
        <Card className="border-orange-200">
          <CardHeader>
            <CardTitle className="text-orange-600">Mastery Deviations</CardTitle>
            <CardDescription>
              Skills with significant mastery change triggering PathGen replan
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {session.deviations.map((dev) => {
                const name = subSkillNames[dev.skill_id] ?? `Skill ${dev.skill_id}`;
                const isImproved = dev.direction === "improved";
                return (
                  <div key={dev.skill_id} className="flex items-center justify-between p-2 rounded border">
                    <span className="text-sm font-medium">{name}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-muted-foreground">
                        {(dev.original * 100).toFixed(2)}%
                      </span>
                      <span className="text-xs">&rarr;</span>
                      <span className={`text-xs font-medium ${isImproved ? "text-emerald-600" : "text-red-600"}`}>
                        {(dev.current * 100).toFixed(1)}%
                      </span>
                      <Badge
                        className="text-[10px]"
                        style={{
                          backgroundColor: isImproved ? DEVIATION_COLORS.improved + "20" : DEVIATION_COLORS.declined + "20",
                          color: isImproved ? DEVIATION_COLORS.improved : DEVIATION_COLORS.declined,
                        }}
                      >
                        {dev.delta > 0 ? "+" : ""}{(dev.delta * 100).toFixed(2)}%
                      </Badge>
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Session metadata */}
      <Card>
        <CardHeader>
          <CardTitle>Session Info</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
            <div>
              <p className="text-muted-foreground text-xs">Started</p>
              <p className="font-medium">{new Date(session.started_at).toLocaleString()}</p>
            </div>
            <div>
              <p className="text-muted-foreground text-xs">Completed</p>
              <p className="font-medium">{new Date(session.completed_at).toLocaleString()}</p>
            </div>
            <div>
              <p className="text-muted-foreground text-xs">Mastery Updates</p>
              <p className="font-medium">{session.mastery_updates.length}</p>
            </div>
            <div>
              <p className="text-muted-foreground text-xs">Reward Events</p>
              <p className="font-medium">{rewards.events_count}</p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
