import { useState } from "react";
import { Loader2, Send } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { coursesApi } from "../../api";
import type { CourseReadiness } from "../../types";

interface PublishCourseButtonProps {
  readiness: CourseReadiness;
  onRefresh: () => void | Promise<void>;
}

export function PublishCourseButton({ readiness, onRefresh }: PublishCourseButtonProps) {
  const [isPublishing, setIsPublishing] = useState(false);
  const isPublished = readiness.publication_status === "published";
  const disabled = !readiness.can_publish || isPublishing || isPublished;

  const handlePublish = async () => {
    setIsPublishing(true);
    try {
      await coursesApi.publish(readiness.course_id);
      toast.success("Course published.");
      await onRefresh();
    } catch {
      toast.error("Failed to publish course.");
    } finally {
      setIsPublishing(false);
    }
  };

  return (
    <Button onClick={() => void handlePublish()} disabled={disabled} size="sm">
      {isPublishing ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
      {isPublished ? "Published" : "Publish course"}
    </Button>
  );
}
