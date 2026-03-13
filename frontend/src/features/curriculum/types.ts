export type SkillSource = "book" | "market_demand";

export interface JobPostingRead {
  url: string;
  title: string | null;
  company: string | null;
  site: string | null;
}

export interface ConceptRead {
  name: string;
  description: string | null;
}

export interface SkillRead {
  name: string;
  source: SkillSource;
  description: string | null;
  concepts: ConceptRead[];

  // Market-demand-only fields
  category: string | null;
  frequency: number | null;
  demand_pct: number | null;
  priority: string | null;
  status: string | null;
  reasoning: string | null;
  rationale: string | null;
  created_at: string | null;
  job_postings: JobPostingRead[];
}

export interface SectionRead {
  section_index: number;
  title: string;
  concepts: ConceptRead[];
}

export interface ChapterRead {
  chapter_index: number;
  title: string;
  summary: string | null;
  sections: SectionRead[];
  skills: SkillRead[];
}

export interface CurriculumResponse {
  course_id: number;
  book_title: string | null;
  book_authors: string | null;
  chapters: ChapterRead[];
}

export interface ChangelogEntry {
  timestamp: string;
  agent: string;
  action: string;
  details: string;
  chapter: string | null;
  skill_name: string | null;
}

export interface CurriculumWithChangelog {
  curriculum: CurriculumResponse;
  changelog: ChangelogEntry[];
}
