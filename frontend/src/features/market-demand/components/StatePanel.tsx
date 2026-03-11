import { useState, useEffect } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { PipelineStepper } from "./PipelineStepper";
import type { AgentState, PipelineStageId, StageStatus } from "../types";

interface StatePanelProps {
  agentState: AgentState;
  pipelineStages: Record<PipelineStageId, StageStatus>;
}

export function StatePanel({ agentState, pipelineStages }: StatePanelProps) {
  const autoTab = getActiveTab(agentState);
  const [selectedTab, setSelectedTab] = useState(autoTab);

  // Auto-switch when pipeline advances to a new stage
  useEffect(() => {
    setSelectedTab(autoTab);
  }, [autoTab]);

  return (
    <div className="h-full flex flex-col bg-card border-l overflow-hidden">
      <div className="shrink-0">
        <PipelineStepper stages={pipelineStages} />
      </div>

      <Tabs value={selectedTab} onValueChange={setSelectedTab} className="flex-1 flex flex-col min-h-0 overflow-hidden">
        <TabsList className="w-full bg-muted/50 border-b rounded-none shrink-0">
          <TabsTrigger value="jobs" className="flex-1 text-xs">
            Jobs
          </TabsTrigger>
          <TabsTrigger value="skills" className="flex-1 text-xs">
            Skills
          </TabsTrigger>
          <TabsTrigger value="coverage" className="flex-1 text-xs">
            Coverage
          </TabsTrigger>
          <TabsTrigger value="mapping" className="flex-1 text-xs">
            Mapping
          </TabsTrigger>
          <TabsTrigger value="insert" className="flex-1 text-xs">
            To Insert
          </TabsTrigger>
        </TabsList>

        <TabsContent value="jobs" className="flex-1 mt-0 overflow-hidden data-[state=active]:flex data-[state=active]:flex-col min-h-0">
          <ScrollArea className="flex-1 min-h-0">
            <div className="p-3"><JobsTab agentState={agentState} /></div>
          </ScrollArea>
        </TabsContent>
        <TabsContent value="skills" className="flex-1 mt-0 overflow-hidden data-[state=active]:flex data-[state=active]:flex-col min-h-0">
          <ScrollArea className="flex-1 min-h-0">
            <div className="p-3"><SkillsTab agentState={agentState} /></div>
          </ScrollArea>
        </TabsContent>
        <TabsContent value="coverage" className="flex-1 mt-0 overflow-hidden data-[state=active]:flex data-[state=active]:flex-col min-h-0">
          <ScrollArea className="flex-1 min-h-0">
            <div className="p-3"><CoverageTab agentState={agentState} /></div>
          </ScrollArea>
        </TabsContent>
        <TabsContent value="mapping" className="flex-1 mt-0 overflow-hidden data-[state=active]:flex data-[state=active]:flex-col min-h-0">
          <ScrollArea className="flex-1 min-h-0">
            <div className="p-3"><MappingTab agentState={agentState} /></div>
          </ScrollArea>
        </TabsContent>
        <TabsContent value="insert" className="flex-1 mt-0 overflow-hidden data-[state=active]:flex data-[state=active]:flex-col min-h-0">
          <ScrollArea className="flex-1 min-h-0">
            <div className="p-3"><InsertTab agentState={agentState} /></div>
          </ScrollArea>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function getActiveTab(state: AgentState): string {
  if (state.insertion_results || state.skill_concepts) return "insert";
  if (state.curriculum_mapping) return "coverage";
  if (state.extracted_skills) return "skills";
  if (state.fetched_jobs || state.selected_jobs) return "jobs";
  return "jobs";
}

// ── Tab Content Components ──

function JobsTab({ agentState }: { agentState: AgentState }) {
  const groups = agentState.job_groups;
  const jobs = agentState.fetched_jobs;
  const selected = agentState.selected_jobs;

  if (!jobs || jobs.length === 0) {
    return <EmptyTab message="No jobs fetched yet" />;
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">
        {jobs.length} jobs fetched
        {selected ? ` · ${selected.length} selected` : ""}
      </p>
      {groups &&
        Object.entries(groups)
          .sort(([, a], [, b]) => (b as number[]).length - (a as number[]).length)
          .map(([name, indices]) => {
            const idxs = indices as number[];
            const companies = [...new Set(idxs.map((i) => (jobs[i] as Record<string, string>)?.company).filter(Boolean))].slice(0, 3);
            return (
              <div key={name} className="flex items-center gap-2">
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-foreground truncate">{name}</p>
                  <p className="text-xs text-muted-foreground/70 truncate">{companies.join(", ")}</p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <div className="w-16 h-1.5 bg-muted rounded-full overflow-hidden">
                    <div
                      className="h-full bg-blue-500 rounded-full"
                      style={{ width: `${Math.min(100, (idxs.length / Math.max(...Object.values(groups).map((v) => (v as number[]).length))) * 100)}%` }}
                    />
                  </div>
                  <span className="text-xs text-muted-foreground w-4 text-right">{idxs.length}</span>
                </div>
              </div>
            );
          })}
    </div>
  );
}

function SkillsTab({ agentState }: { agentState: AgentState }) {
  const skills = agentState.extracted_skills;

  if (!skills || skills.length === 0) {
    return <EmptyTab message="No skills extracted yet" />;
  }

  const maxFreq = Math.max(...skills.map((s) => s.frequency));

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">{skills.length} unique skills</p>
        <p className="text-[10px] text-muted-foreground/70">Freq in jobs →</p>
      </div>
      {skills.map((skill) => (
        <div key={skill.name} className="flex items-center gap-2">
          <div className="flex-1 min-w-0">
            <p className="text-sm text-foreground truncate">{skill.name}</p>
          </div>
          <Badge variant="outline" className="text-[10px] px-1.5 py-0 shrink-0">
            {skill.category}
          </Badge>
          <div className="w-12 h-1.5 bg-muted rounded-full overflow-hidden shrink-0" title={`${skill.pct}% of jobs mention this skill`}>
            <div
              className="h-full bg-purple-500 rounded-full"
              style={{ width: `${(skill.frequency / maxFreq) * 100}%` }}
            />
          </div>
          <span className="text-xs text-muted-foreground w-8 text-right shrink-0">{skill.pct}%</span>
        </div>
      ))}
    </div>
  );
}

function CoverageTab({ agentState }: { agentState: AgentState }) {
  const mapping = agentState.curriculum_mapping;

  if (!mapping || mapping.length === 0) {
    return <EmptyTab message="No coverage data yet" />;
  }

  const covered = mapping.filter((m) => m.status === "covered");
  const gaps = mapping.filter((m) => m.status === "gap");
  const newTopics = mapping.filter((m) => m.status === "new_topic_needed");

  return (
    <div className="space-y-4">
      <div className="flex gap-3">
        <StatBox label="Covered" count={covered.length} color="text-green-600" />
        <StatBox label="Gaps" count={gaps.length} color="text-amber-600" />
        <StatBox label="New" count={newTopics.length} color="text-red-600" />
      </div>

      {gaps.length > 0 && (
        <Section label="Gap Skills" items={gaps.map((g) => g.name)} color="bg-amber-500" />
      )}
      {covered.length > 0 && (
        <Section label="Covered" items={covered.map((c) => c.name)} color="bg-green-500" />
      )}
      {newTopics.length > 0 && (
        <Section label="New Topics" items={newTopics.map((n) => n.name)} color="bg-red-500" />
      )}
    </div>
  );
}

function MappingTab({ agentState }: { agentState: AgentState }) {
  const mapping = agentState.curriculum_mapping;

  if (!mapping || mapping.length === 0) {
    return <EmptyTab message="No mapping data yet" />;
  }

  // Group by target_chapter
  const byChapter: Record<string, typeof mapping> = {};
  for (const m of mapping) {
    const ch = m.target_chapter || "Unassigned";
    if (!byChapter[ch]) byChapter[ch] = [];
    byChapter[ch].push(m);
  }

  return (
    <div className="space-y-4">
      {Object.entries(byChapter).map(([chapter, skills]) => (
        <div key={chapter}>
          <p className="text-xs font-semibold text-muted-foreground mb-1">{chapter}</p>
          <div className="flex flex-wrap gap-1">
            {skills.map((s) => (
              <Badge
                key={s.name}
                variant="outline"
                className="text-[10px]"
              >
                {s.name}
              </Badge>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function InsertTab({ agentState }: { agentState: AgentState }) {
  const toInsert = agentState.selected_for_insertion;
  const results = agentState.insertion_results;

  if (results) {
    return (
      <div className="space-y-2">
        <p className="text-xs text-green-600 font-semibold">Insertion Complete</p>
        <div className="font-mono text-xs text-muted-foreground space-y-1">
          <p>MARKET_SKILL nodes: {results.skills}</p>
          <p>JOB_POSTING nodes: {results.job_postings}</p>
          <p>Chapter links: {results.chapter_links}</p>
          <p>Source links: {results.sourced_from}</p>
          <p>Concept links: {results.existing_concept_links}</p>
          <p>New concepts: {results.new_concepts}</p>
        </div>
      </div>
    );
  }

  if (!toInsert || toInsert.length === 0) {
    return <EmptyTab message="No skills staged for insertion" />;
  }

  return (
    <div className="space-y-2">
      <p className="text-xs text-muted-foreground">{toInsert.length} skills staged</p>
      {(toInsert as Record<string, string>[]).map((s) => (
        <div key={s.name} className="text-sm text-foreground">
          {s.name}
          {s.target_chapter && (
            <span className="text-xs text-muted-foreground/70 ml-2">→ {s.target_chapter}</span>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Shared UI helpers ──

function EmptyTab({ message }: { message: string }) {
  return <p className="text-xs text-muted-foreground py-4 text-center">{message}</p>;
}

const STAT_DESCRIPTIONS: Record<string, string> = {
  Covered: "Skills already taught in your course — matched to existing book skills or concepts in the knowledge graph.",
  Gaps: "Skills found in job postings that your course partially covers but doesn't explicitly teach yet.",
  New: "In-demand skills with no match in your curriculum. Consider adding these as new topics.",
};

function StatBox({ label, count, color }: { label: string; count: number; color: string }) {
  const description = STAT_DESCRIPTIONS[label];
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="flex-1 bg-muted rounded-lg border p-2 text-center cursor-help">
            <p className={`text-lg font-bold ${color}`}>{count}</p>
            <p className="text-[10px] text-muted-foreground">{label}</p>
          </div>
        </TooltipTrigger>
        {description && (
          <TooltipContent side="bottom" className="max-w-52 text-center">
            {description}
          </TooltipContent>
        )}
      </Tooltip>
    </TooltipProvider>
  );
}

function Section({ label, items, color }: { label: string; items: string[]; color: string }) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-1">
        <div className={`w-2 h-2 rounded-full ${color}`} />
        <span className="text-xs text-muted-foreground font-medium">{label}</span>
        <span className="text-xs text-muted-foreground/70">{items.length}</span>
      </div>
      <div className="flex flex-wrap gap-1">
        {items.slice(0, 10).map((name) => (
          <Badge
            key={name}
            variant="outline"
            className="text-[10px]"
          >
            {name}
          </Badge>
        ))}
        {items.length > 10 && (
          <span className="text-[10px] text-muted-foreground/70">+{items.length - 10}</span>
        )}
      </div>
    </div>
  );
}
