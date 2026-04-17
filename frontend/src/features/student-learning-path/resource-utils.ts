import type {
  LearningPathChapter,
  LearningPathReadingResource,
  LearningPathResponse,
  LearningPathVideoResource,
} from './api';

export type StudyResourceKind = 'reading' | 'video';

export type ActiveLearningPathResource =
  | {
      kind: 'reading';
      id: string;
      title: string;
      url: string;
      domain: string;
    }
  | {
      kind: 'video';
      id: string;
      title: string;
      url: string;
      domain: string;
      videoId: string;
    };

export function isStudyResourceKind(value: string | undefined): value is StudyResourceKind {
  return value === 'reading' || value === 'video';
}

export function buildLearningPathStudyRoute(
  courseId: number | string,
  resource: Pick<ActiveLearningPathResource, 'kind' | 'id'>,
): string {
  return `/courses/${courseId}/learning-path/study/${resource.kind}/${resource.id}`;
}

export function toActiveReadingResource(
  resource: LearningPathReadingResource,
): ActiveLearningPathResource {
  return {
    kind: 'reading',
    id: resource.id,
    title: resource.title,
    url: resource.url,
    domain: resource.domain,
  };
}

export function toActiveVideoResource(
  resource: LearningPathVideoResource,
): ActiveLearningPathResource {
  return {
    kind: 'video',
    id: resource.id,
    title: resource.title,
    url: resource.url,
    domain: resource.domain,
    videoId: resource.video_id,
  };
}

export function isPdfResourceUrl(url: string): boolean {
  return /\.pdf(?:$|[?#])/i.test(url);
}

export function getVisibleReadingResources(
  readings: LearningPathReadingResource[],
): LearningPathReadingResource[] {
  return readings.filter(
    (reading) =>
      !String(reading.resource_type || '').toLowerCase().includes('pdf') &&
      !isPdfResourceUrl(reading.url) &&
      !isPdfResourceUrl(reading.search_result_url),
  );
}

function isAccessibleChapter(chapter: LearningPathChapter): boolean {
  return chapter.quiz_status === 'learning' || chapter.quiz_status === 'completed';
}

export function findAccessibleLearningPathResource(
  learningPath: LearningPathResponse,
  resourceKind: StudyResourceKind,
  resourceId: string | undefined,
): ActiveLearningPathResource | null {
  if (!resourceId) {
    return null;
  }

  for (const chapter of learningPath.chapters) {
    if (!isAccessibleChapter(chapter)) {
      continue;
    }

    for (const skill of chapter.selected_skills) {
      if (resourceKind === 'reading') {
        const reading = getVisibleReadingResources(skill.readings).find(
          (candidate) => candidate.id === resourceId,
        );

        if (reading) {
          return toActiveReadingResource(reading);
        }

        continue;
      }

      const video = skill.videos.find((candidate) => candidate.id === resourceId);
      if (video) {
        return toActiveVideoResource(video);
      }
    }
  }

  return null;
}
