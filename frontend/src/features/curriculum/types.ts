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

export interface ReadingResourceRead {
  title: string;
  url: string;
  domain: string;
  snippet: string;
  search_content: string;
  search_result_url: string;
  search_result_domain: string;
  source_engine: string;
  source_engines: string[];
  search_metadata_json: string;
  final_score: number;
  resource_type: string;
  concepts_covered: string[];
}

export interface VideoResourceRead {
  title: string;
  url: string;
  video_id: string;
  domain: string;
  snippet: string;
  search_content: string;
  search_result_url: string;
  search_result_domain: string;
  source_engine: string;
  source_engines: string[];
  search_metadata_json: string;
  final_score: number;
  resource_type: string;
  concepts_covered: string[];
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

  // Resource discovery fields
  readings: ReadingResourceRead[];
  videos: VideoResourceRead[];
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

// ── Skill Banks types ──────────────────────────────────────────

export interface TranscriptDocument {
  topic: string;
  source_filename: string | null;
}

export interface CourseChapter {
  chapter_index: number;
  title: string;
  description: string | null;
  learning_objectives: string[];
  documents: TranscriptDocument[];
}

export interface BookSkillBankSkill {
  name: string;
  description: string | null;
}

export interface BookSkillBankChapter {
  chapter_index: number;
  chapter_id: string;
  skills: BookSkillBankSkill[];
}

export interface BookSkillBankBook {
  book_id: string;
  title: string;
  authors: string | null;
  chapters: BookSkillBankChapter[];
}

export interface MarketSkillBankSkill {
  name: string;
  category: string | null;
  status: string | null;
  priority: string | null;
  demand_pct: number | null;
}

export interface MarketSkillBankJobPosting {
  title: string;
  company: string | null;
  site: string | null;
  url: string;
  search_term: string | null;
  skills: MarketSkillBankSkill[];
}

export interface SkillSelectionRange {
  min_skills: number;
  max_skills: number;
  is_default: boolean;
}

export interface SkillBanksResponse {
  course_chapters: CourseChapter[];
  book_skill_bank: BookSkillBankBook[];
  market_skill_bank: MarketSkillBankJobPosting[];
  selection_range: SkillSelectionRange;
}
