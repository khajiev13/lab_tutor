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
  title: string | null;
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

export interface TeacherInsightTopSkill {
  name: string;
  student_count: number;
}

export interface TeacherInsightTopPosting {
  url: string;
  title: string | null;
  company: string | null;
  student_count: number;
}

export interface StudentInsightStudent {
  id: number;
  full_name: string;
  email: string;
  selected_skill_count: number;
  interested_posting_count: number;
  has_learning_path: boolean;
}

export interface StudentInsightsSummary {
  students_with_selections: number;
  students_with_learning_paths: number;
  avg_selected_skill_count: number;
  top_selected_skills: TeacherInsightTopSkill[];
  top_interested_postings: TeacherInsightTopPosting[];
}

export interface StudentInsightsOverview {
  summary: StudentInsightsSummary;
  students: StudentInsightStudent[];
}

export interface TeacherStudentSkillBankSkill {
  name: string;
  description?: string | null;
  category?: string | null;
  is_selected?: boolean;
  source?: string | null;
  peer_count?: number;
}

export interface TeacherStudentSkillBankChapter {
  chapter_id: string;
  title: string;
  chapter_index: number;
  skills: TeacherStudentSkillBankSkill[];
}

export interface TeacherStudentSkillBankBook {
  book_id: string;
  title: string;
  authors?: string | null;
  chapters: TeacherStudentSkillBankChapter[];
}

export interface TeacherStudentSkillBankJobPosting {
  url: string;
  title: string;
  company: string | null;
  site?: string | null;
  search_term?: string | null;
  is_interested: boolean;
  skills: TeacherStudentSkillBankSkill[];
}

export interface TeacherSkillBanksOverlay {
  book_skill_banks: TeacherStudentSkillBankBook[];
  market_skill_bank: TeacherStudentSkillBankJobPosting[];
  selected_skill_names: string[];
  interested_posting_urls: string[];
  peer_selection_counts: Record<string, number>;
  selection_range: SkillSelectionRange;
  prerequisite_edges: Array<{
    prerequisite_name: string;
    dependent_name: string;
    confidence: 'high' | 'medium' | 'low';
    reasoning: string;
  }>;
}

export interface LearningPathChapterStatusCounts {
  locked: number;
  quiz_required: number;
  learning: number;
  completed: number;
}

export interface LearningPathSummary {
  has_learning_path: boolean;
  total_selected_skills: number;
  skills_with_resources: number;
  chapter_status_counts: LearningPathChapterStatusCounts;
}

export interface TeacherStudentInsightDetail {
  student: Pick<StudentInsightStudent, 'id' | 'full_name' | 'email'>;
  skill_banks: TeacherSkillBanksOverlay;
  learning_path_summary: LearningPathSummary;
}

export interface SkillBankDisplaySkill {
  name: string;
  description: string | null;
  category?: string | null;
  priority?: string | null;
  demand_pct?: number | null;
  overlay?: {
    isSelected: boolean;
    peerCount: number;
  };
}

export interface SkillBankDisplayBookChapter {
  chapter_id: string;
  title: string;
  chapter_index: number;
  skills: SkillBankDisplaySkill[];
}

export interface SkillBankDisplayBook {
  book_id: string;
  title: string;
  authors: string | null;
  chapters: SkillBankDisplayBookChapter[];
}

export interface SkillBankDisplayJobPosting {
  url: string;
  title: string;
  company: string | null;
  site: string | null;
  search_term: string | null;
  skills: SkillBankDisplaySkill[];
  overlay?: {
    isInterested: boolean;
  };
}
