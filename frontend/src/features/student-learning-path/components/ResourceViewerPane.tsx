import { useState } from 'react';
import { BookOpen, ExternalLink, Globe, Loader2, PlayCircle, TriangleAlert, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import type { ActiveLearningPathResource } from '../resource-utils';

export function ResourceViewerPane({
  resource,
  onClose,
}: {
  resource: ActiveLearningPathResource;
  onClose: () => void;
}) {
  return (
    <Card className="flex min-h-[70vh] flex-col overflow-hidden border-border/60 shadow-none">
      <div className="border-b border-border/60 px-5 py-4">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0 space-y-1">
            <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
              {resource.kind === 'video' ? 'Video resource' : 'Reading resource'}
            </p>
            <h2 className="text-xl font-semibold tracking-tight">{resource.title}</h2>
            <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
              <Globe className="h-3.5 w-3.5" />
              <span className="truncate">{resource.domain || 'External source'}</span>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button asChild variant="outline" size="sm" className="gap-2">
              <a href={resource.url} target="_blank" rel="noopener noreferrer">
                Open original source
                <ExternalLink className="h-4 w-4" />
              </a>
            </Button>
            <Button type="button" variant="ghost" size="icon" aria-label="Close viewer" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>

      <div className="min-h-0 flex-1">
        {resource.kind === 'video' ? (
          <VideoResourceBody resource={resource} />
        ) : (
          <ReadingResourceBody key={resource.id} resource={resource} />
        )}
      </div>
    </Card>
  );
}

function VideoResourceBody({
  resource,
}: {
  resource: Extract<ActiveLearningPathResource, { kind: 'video' }>;
}) {
  if (!resource.videoId) {
    return (
      <FallbackCard
        title="Video unavailable in-app"
        description="This video does not have an embeddable YouTube identifier yet."
        summary="Open the original source to continue watching this resource."
        url={resource.url}
      />
    );
  }

  return (
    <div className="h-full overflow-y-auto p-5">
      <div className="aspect-video w-full overflow-hidden rounded-3xl border border-border/60 bg-black shadow-sm">
        <iframe
          title={resource.title}
          src={`https://www.youtube.com/embed/${encodeURIComponent(resource.videoId)}?rel=0`}
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
          allowFullScreen
          className="h-full w-full border-0"
        />
      </div>
    </div>
  );
}

function ReadingResourceBody({
  resource,
}: {
  resource: Extract<ActiveLearningPathResource, { kind: 'reading' }>;
}) {
  const [iframeLoaded, setIframeLoaded] = useState(false);

  return (
    <div className="relative h-full bg-background">
      {!iframeLoaded && (
        <div
          role="status"
          aria-label="Loading reading"
          className="absolute inset-0 z-10 flex items-center justify-center bg-background/85"
        >
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          <span className="sr-only">Loading reading</span>
        </div>
      )}
      <iframe
        title={resource.title}
        src={resource.url}
        sandbox="allow-scripts allow-same-origin allow-popups"
        onLoad={() => setIframeLoaded(true)}
        className="h-full w-full border-0"
      />
    </div>
  );
}

function FallbackCard({
  title,
  description,
  summary,
  url,
}: {
  title: string;
  description: string;
  summary: string;
  url: string;
}) {
  return (
    <div className="flex h-full items-center justify-center p-5">
      <div className="w-full max-w-3xl rounded-3xl border border-border/60 bg-muted/20 p-6">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-background text-muted-foreground">
            {title.toLowerCase().includes('video') ? (
              <PlayCircle className="h-5 w-5" />
            ) : title.toLowerCase().includes('reading') ? (
              <BookOpen className="h-5 w-5" />
            ) : (
              <TriangleAlert className="h-5 w-5" />
            )}
          </div>
          <div className="space-y-4">
            <div className="space-y-1">
              <p className="font-medium">{title}</p>
              <p className="text-sm text-muted-foreground">{description}</p>
            </div>
            <p className="text-sm text-muted-foreground">{summary}</p>
            <Button asChild variant="outline" className="gap-2">
              <a href={url} target="_blank" rel="noopener noreferrer">
                Open original source
                <ExternalLink className="h-4 w-4" />
              </a>
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
