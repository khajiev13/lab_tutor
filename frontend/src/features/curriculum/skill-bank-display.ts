import type {
  BookSkillBankBook,
  MarketSkillBankJobPosting,
  SkillBankDisplayBook,
  SkillBankDisplayJobPosting,
  TeacherStudentInsightDetail,
} from '@/features/curriculum/types';

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
        name: skill.name,
        description: skill.description ?? null,
        overlay: {
          isSelected: Boolean(skill.is_selected),
          peerCount: skill.peer_count ?? 0,
        },
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
        name: skill.name,
        description: skill.description ?? null,
        category: skill.category ?? null,
        overlay: {
          isSelected: Boolean(skill.is_selected),
          peerCount: skill.peer_count ?? 0,
        },
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
          overlayChapter.skills.map((skill) => [skill.name, skill.overlay]),
        );

        return {
          ...chapter,
          skills: chapter.skills.map((skill) => ({
            ...skill,
            overlay: overlaySkills.get(skill.name) ?? skill.overlay,
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
      overlayPosting.skills.map((skill) => [skill.name, skill.overlay]),
    );

    return {
      ...posting,
      overlay: overlayPosting.overlay,
      skills: posting.skills.map((skill) => ({
        ...skill,
        overlay: overlaySkills.get(skill.name) ?? skill.overlay,
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
