import type {
  BookSkillBankBook,
  CareerSkillBankSkill,
  MarketSkillBankJobPosting,
  SkillBankDisplayBook,
  SkillBankDisplayJobPosting,
  TeacherStudentInsightDetail,
  TeacherStudentSkillBankSkill,
} from '@/features/curriculum/types';

export function skillBankKey(skill: { name: string; skill_reference_id?: string | null; source?: string | null }, source: string) {
  return skill.skill_reference_id ? `reference:${skill.skill_reference_id}` : `legacy:${skill.source ?? source}:${skill.name}`;
}

function selectionOverlay(skill: TeacherStudentSkillBankSkill, detail: TeacherStudentInsightDetail) {
  if (skill.skill_reference_id) {
    return {
      isSelected: detail.skill_banks.selected_skill_reference_ids !== undefined
        ? detail.skill_banks.selected_skill_reference_ids.includes(skill.skill_reference_id)
        : Boolean(skill.is_selected),
      peerCount: detail.skill_banks.peer_selection_counts_by_reference?.[skill.skill_reference_id] ?? skill.peer_count ?? 0,
    };
  }
  return { isSelected: Boolean(skill.is_selected), peerCount: skill.peer_count ?? 0 };
}

export function adaptCareerSkillBank(skills: CareerSkillBankSkill[], detail: TeacherStudentInsightDetail | null = null): CareerSkillBankSkill[] {
  const overlay = new Map(detail?.skill_banks.career_skill_bank?.map((skill) => [skill.skill_reference_id, skill]));
  const all = new Map(skills.map((skill) => [skill.skill_reference_id, skill]));
  for (const [id, skill] of overlay) if (!all.has(id)) all.set(id, skill);
  return [...all.values()].map((skill) => ({...skill, ...(detail ? {overlay: selectionOverlay({...overlay.get(skill.skill_reference_id), ...skill, name: skill.label}, detail)} : {})}));
}

export function adaptTeacherBookSkillBanks(
  books: BookSkillBankBook[],
): SkillBankDisplayBook[] {
  return books.map((book) => ({
    book_id: book.book_id,
    title: book.title,
    authors: book.authors ?? null,
    chapters: book.chapters.map((chapter) => ({
      chapter_id: chapter.chapter_id,
      title: chapter.title ?? `Chapter ${chapter.chapter_index}`,
      chapter_index: chapter.chapter_index,
      skills: chapter.skills.map((skill) => ({
        ...skill,
        name: skill.name,
        description: skill.description ?? null,
      })),
    })),
  }));
}

export function adaptTeacherMarketSkillBank(
  jobPostings: MarketSkillBankJobPosting[],
): SkillBankDisplayJobPosting[] {
  return jobPostings.map((posting) => ({
    url: posting.url,
    title: posting.title,
    company: posting.company ?? null,
    site: posting.site ?? null,
    search_term: posting.search_term ?? null,
      skills: posting.skills.map((skill) => ({
        ...skill,
        name: skill.name,
        description: null,
        category: skill.category ?? null,
        priority: skill.priority ?? null,
        demand_pct: skill.demand_pct ?? null,
      })),
  }));
}

export function adaptStudentOverlayBookSkillBanks(
  detail: TeacherStudentInsightDetail | null,
): SkillBankDisplayBook[] {
  if (!detail) {
    return [];
  }

  return detail.skill_banks.book_skill_banks.map((book) => ({
    book_id: book.book_id,
    title: book.title,
    authors: book.authors ?? null,
    chapters: book.chapters.map((chapter) => ({
      chapter_id: chapter.chapter_id,
      title: chapter.title,
      chapter_index: chapter.chapter_index,
      skills: chapter.skills.map((skill) => ({
        ...skill,
        name: skill.name,
        description: skill.description ?? null,
        overlay: selectionOverlay(skill, detail),
      })),
    })),
  }));
}

export function adaptStudentOverlayMarketSkillBank(
  detail: TeacherStudentInsightDetail | null,
): SkillBankDisplayJobPosting[] {
  if (!detail) {
    return [];
  }

  return [...detail.skill_banks.market_skill_bank]
    .map((posting) => ({
      url: posting.url,
      title: posting.title,
      company: posting.company ?? null,
      site: posting.site ?? null,
      search_term: posting.search_term ?? null,
      overlay: {
        isInterested: posting.is_interested,
      },
      skills: posting.skills.map((skill) => ({
        ...skill,
        name: skill.name,
        description: skill.description ?? null,
        category: skill.category ?? null,
        overlay: selectionOverlay(skill, detail),
      })),
    }))
    .sort((left, right) => {
      const leftInterested = Boolean(left.overlay?.isInterested);
      const rightInterested = Boolean(right.overlay?.isInterested);
      if (leftInterested !== rightInterested) {
        return leftInterested ? -1 : 1;
      }
      return left.title.localeCompare(right.title);
    });
}

export function adaptTeacherBookSkillBanksWithOverlay(
  books: BookSkillBankBook[],
  detail: TeacherStudentInsightDetail | null,
): SkillBankDisplayBook[] {
  const teacherBooks = adaptTeacherBookSkillBanks(books);
  if (!detail) {
    return teacherBooks;
  }

  const overlayBooks = adaptStudentOverlayBookSkillBanks(detail);
  const overlayByBookId = new Map(overlayBooks.map((book) => [book.book_id, book]));

  const mergedBooks = teacherBooks.map((book) => {
    const overlayBook = overlayByBookId.get(book.book_id);
    if (!overlayBook) {
      return book;
    }

    const overlayChapters = new Map(
      overlayBook.chapters.map((chapter) => [chapter.chapter_id, chapter]),
    );

    return {
      ...book,
      chapters: book.chapters.map((chapter) => {
        const overlayChapter = overlayChapters.get(chapter.chapter_id);
        if (!overlayChapter) {
          return chapter;
        }

        const overlaySkills = new Map(
          overlayChapter.skills.map((skill) => [skillBankKey(skill, 'book'), skill.overlay]),
        );

        return {
          ...chapter,
          skills: chapter.skills.map((skill) => ({
            ...skill,
            overlay: overlaySkills.get(skillBankKey(skill, 'book')) ?? skill.overlay,
          })),
        };
      }),
    };
  });

  const teacherBookIds = new Set(teacherBooks.map((book) => book.book_id));
  const overlayOnlyBooks = overlayBooks.filter((book) => !teacherBookIds.has(book.book_id));

  return [...mergedBooks, ...overlayOnlyBooks];
}

export function adaptTeacherMarketSkillBankWithOverlay(
  jobPostings: MarketSkillBankJobPosting[],
  detail: TeacherStudentInsightDetail | null,
): SkillBankDisplayJobPosting[] {
  const teacherPostings = adaptTeacherMarketSkillBank(jobPostings);
  if (!detail) {
    return teacherPostings;
  }

  const overlayPostings = adaptStudentOverlayMarketSkillBank(detail);
  const overlayByUrl = new Map(overlayPostings.map((posting) => [posting.url, posting]));

  const mergedPostings = teacherPostings.map((posting) => {
    const overlayPosting = overlayByUrl.get(posting.url);
    if (!overlayPosting) {
      return posting;
    }

    const overlaySkills = new Map(
      overlayPosting.skills.map((skill) => [skillBankKey(skill, 'market'), skill.overlay]),
    );

    return {
      ...posting,
      overlay: overlayPosting.overlay,
      skills: posting.skills.map((skill) => ({
        ...skill,
        overlay: overlaySkills.get(skillBankKey(skill, 'market')) ?? skill.overlay,
      })),
    };
  });

  const teacherPostingUrls = new Set(teacherPostings.map((posting) => posting.url));
  const overlayOnlyPostings = overlayPostings.filter(
    (posting) => !teacherPostingUrls.has(posting.url),
  );

  return [...mergedPostings, ...overlayOnlyPostings].sort((left, right) => {
    const leftInterested = Boolean(left.overlay?.isInterested);
    const rightInterested = Boolean(right.overlay?.isInterested);
    if (leftInterested !== rightInterested) {
      return leftInterested ? -1 : 1;
    }
    return left.title.localeCompare(right.title);
  });
}
