import { fireEvent, render, screen } from '@testing-library/react';

import { BookSkillBank } from '@/features/curriculum/components/BookSkillBank';
import { MarketSkillBank } from '@/features/curriculum/components/MarketSkillBank';
import {
  adaptStudentOverlayMarketSkillBank,
  adaptTeacherMarketSkillBankWithOverlay,
} from '@/features/curriculum/skill-bank-display';
import type { TeacherStudentInsightDetail } from '@/features/curriculum/types';

const overlayDetail: TeacherStudentInsightDetail = {
  student: {
    id: 11,
    full_name: 'Dana Demostudent',
    email: 'dana@example.com',
  },
  skill_banks: {
    book_skill_banks: [
      {
        book_id: 'book-1',
        title: 'Distributed Systems',
        authors: 'T. Author',
        chapters: [
          {
            chapter_id: 'chapter-1',
            title: 'Foundations',
            chapter_index: 1,
            skills: [
              {
                name: 'Batch Processing',
                description: 'Learn batch systems.',
                is_selected: true,
                peer_count: 2,
              },
            ],
          },
        ],
      },
    ],
    market_skill_bank: [
      {
        url: 'https://jobs.example/platform',
        title: 'Platform Engineer',
        company: 'Acme',
        site: 'LinkedIn',
        search_term: 'platform engineer',
        is_interested: true,
        skills: [
          {
            name: 'Kafka',
            description: 'Event streaming',
            category: 'data',
            is_selected: true,
            peer_count: 3,
          },
        ],
      },
      {
        url: 'https://jobs.example/backend',
        title: 'Backend Engineer',
        company: 'Beta',
        site: 'Indeed',
        search_term: 'backend engineer',
        is_interested: false,
        skills: [
          {
            name: 'PostgreSQL',
            description: 'Query optimization',
            category: 'database',
            is_selected: false,
            peer_count: 1,
          },
        ],
      },
    ],
    selected_skill_names: ['Batch Processing', 'Kafka'],
    interested_posting_urls: ['https://jobs.example/platform'],
    peer_selection_counts: {
      'Batch Processing': 2,
      Kafka: 3,
      PostgreSQL: 1,
    },
    selection_range: {
      min_skills: 20,
      max_skills: 35,
      is_default: true,
    },
    prerequisite_edges: [],
  },
  learning_path_summary: {
    has_learning_path: true,
    total_selected_skills: 2,
    skills_with_resources: 1,
    chapter_status_counts: {
      locked: 0,
      quiz_required: 1,
      learning: 0,
      completed: 1,
    },
  },
};

describe('read-only skill bank overlays', () => {
  it('sorts interested job postings before the rest in the teacher overlay view', () => {
    const postings = adaptStudentOverlayMarketSkillBank(overlayDetail);

    expect(postings.map((posting) => posting.title)).toEqual([
      'Platform Engineer',
      'Backend Engineer',
    ]);
    expect(postings[0]?.overlay?.isInterested).toBe(true);
    expect(postings[1]?.overlay?.isInterested).toBe(false);
  });

  it('renders interested and selected badges for market overlays', () => {
    const postings = adaptStudentOverlayMarketSkillBank(overlayDetail);

    render(
      <MarketSkillBank
        jobPostings={postings}
        selectedStudentName={overlayDetail.student.full_name}
      />,
    );

    expect(screen.getByText('Interested by Dana Demostudent')).toBeInTheDocument();
    expect(screen.getByText('Selected by Dana Demostudent')).toBeInTheDocument();
  });

  it('renders selected badges for book-skill overlays', () => {
    render(
      <BookSkillBank
        books={[
          {
            book_id: 'book-1',
            title: 'Distributed Systems',
            authors: 'T. Author',
            chapters: [
              {
                chapter_id: 'chapter-1',
                title: 'Foundations',
                chapter_index: 1,
                skills: [
                  {
                    name: 'Batch Processing',
                    description: 'Learn batch systems.',
                    overlay: {
                      isSelected: true,
                      peerCount: 2,
                    },
                  },
                ],
              },
            ],
          },
        ]}
        selectedStudentName="Alex Example"
      />,
    );

    fireEvent.click(screen.getByText('Chapter 1: Foundations'));

    expect(screen.getByText('Selected by Alex Example')).toBeInTheDocument();
  });

  it('keeps teacher market postings visible when the selected student has no posting overlays', () => {
    const teacherPostings = [
      {
        title: 'Platform Engineer',
        company: 'Acme',
        site: 'LinkedIn',
        url: 'https://jobs.example/platform',
        search_term: 'platform engineer',
        skills: [
          {
            name: 'Kafka',
            category: 'data',
            status: 'gap',
            priority: 'high',
            demand_pct: 83,
          },
        ],
      },
    ];

    const emptyOverlayDetail: TeacherStudentInsightDetail = {
      ...overlayDetail,
      skill_banks: {
        ...overlayDetail.skill_banks,
        market_skill_bank: [],
      },
    };

    const postings = adaptTeacherMarketSkillBankWithOverlay(
      teacherPostings,
      emptyOverlayDetail,
    );

    expect(postings).toHaveLength(1);
    expect(postings[0]?.title).toBe('Platform Engineer');
    expect(postings[0]?.skills[0]?.name).toBe('Kafka');
    expect(postings[0]?.overlay?.isInterested).toBeUndefined();
    expect(postings[0]?.skills[0]?.overlay?.isSelected).toBeUndefined();
  });
});
