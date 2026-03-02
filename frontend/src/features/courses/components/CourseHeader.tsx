import { GitBranch } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { ExtractionStatus, EmbeddingStatus } from "../types";
import { useCourseDetail } from "../context/CourseDetailContext";

function getStatusBadge(status: ExtractionStatus) {
  switch (status) {
    case "not_started":
      return <Badge variant="secondary">Ready to Extract</Badge>;
    case "in_progress":
      return (
        <Badge variant="default" className="bg-blue-500 hover:bg-blue-600">
          Extracting Data...
        </Badge>
      );
    case "finished":
      return (
        <Badge variant="default" className="bg-green-500 hover:bg-green-600">
          Extraction Complete
        </Badge>
      );
    case "failed":
      return <Badge variant="destructive">Extraction Failed</Badge>;
    default:
      return <Badge variant="outline">Unknown</Badge>;
  }
}

function getEmbeddingBadge(status: EmbeddingStatus) {
  switch (status) {
    case "not_started":
      return <Badge variant="outline">Not embedded</Badge>;
    case "in_progress":
      return <Badge variant="secondary">Embedding…</Badge>;
    case "completed":
      return <Badge variant="default">Embedded</Badge>;
    case "failed":
      return <Badge variant="destructive">Embedding failed</Badge>;
    default:
      return <Badge variant="outline">Unknown</Badge>;
  }
}

export function CourseHeader() {
  const navigate = useNavigate();
  const { course, embeddingStatus } = useCourseDetail();

  if (!course) return null;

  return (
    <Card>
      <CardHeader>
        <div className="flex justify-between items-start">
          <div>
            <CardTitle className="text-2xl">{course.title}</CardTitle>
            <CardDescription className="text-base mt-2">
              {course.description || "No description provided."}
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">Status:</span>
            {getStatusBadge(course.extraction_status)}
            {course.extraction_status === "finished" && embeddingStatus && (
              <>
                <span className="text-sm text-muted-foreground">
                  Embeddings:
                </span>
                {getEmbeddingBadge(embeddingStatus.embedding_status)}
              </>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="flex items-center justify-between">
          <div className="flex items-center text-sm text-muted-foreground">
            <span className="font-medium text-foreground mr-2">Created:</span>
            {new Date(course.created_at).toLocaleDateString()}
          </div>
          {course.extraction_status === "finished" && (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => navigate(`/courses/${course.id}/graph`)}
            >
              <GitBranch className="mr-2 h-4 w-4" />
              View knowledge graph
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
