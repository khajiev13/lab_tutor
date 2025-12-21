import { useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { presentationsApi } from "@/features/courses/api";
import type { CourseFileRead, FileProcessingStatus } from "@/features/courses/types";

interface PresentationStatusTableProps {
  courseId: number;
  refreshTrigger?: number;
  poll?: boolean;
  pollIntervalMs?: number;
}

function StatusBadge({ status }: { status: FileProcessingStatus }) {
  switch (status) {
    case "pending":
      return <Badge variant="outline">Pending</Badge>;
    case "processing":
      return <Badge>Processing</Badge>;
    case "processed":
      return <Badge variant="secondary">Processed</Badge>;
    case "failed":
      return <Badge variant="destructive">Failed</Badge>;
    default:
      return <Badge variant="outline">Unknown</Badge>;
  }
}

function formatMaybeDate(iso: string | null) {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
}

export function PresentationStatusTable({
  courseId,
  refreshTrigger,
  poll = false,
  pollIntervalMs = 1500,
}: PresentationStatusTableProps) {
  const [statuses, setStatuses] = useState<CourseFileRead[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const allTerminal = useMemo(() => {
    if (statuses.length === 0) return false;
    return statuses.every((f) => f.status === "processed" || f.status === "failed");
  }, [statuses]);

  useEffect(() => {
    let cancelled = false;

    const fetchStatuses = async () => {
      try {
        const data = await presentationsApi.listStatuses(courseId);
        if (!cancelled) setStatuses(data);
      } catch (error) {
        console.error("Failed to fetch presentation statuses:", error);
        toast.error("Failed to load file statuses");
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    };

    setIsLoading(true);
    fetchStatuses();

    return () => {
      cancelled = true;
    };
  }, [courseId, refreshTrigger]);

  useEffect(() => {
    if (!poll) return;

    const tick = async () => {
      try {
        const data = await presentationsApi.listStatuses(courseId);
        setStatuses(data);

        const isDone =
          data.length > 0 && data.every((f) => f.status === "processed" || f.status === "failed");
        if (isDone) clearInterval(intervalId);
      } catch (error) {
        console.error("Status polling failed:", error);
      }
    };

    const intervalId = setInterval(tick, pollIntervalMs);

    return () => {
      clearInterval(intervalId);
    };
  }, [courseId, poll, pollIntervalMs]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-6">
        <Loader2 className="h-5 w-5 animate-spin text-primary" />
      </div>
    );
  }

  if (statuses.length === 0) {
    return (
      <div className="text-sm text-muted-foreground">
        No per-file statuses available yet.
      </div>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-[55%]">Filename</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Processed at</TableHead>
          <TableHead className="w-[35%]">Last error</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {statuses.map((file) => (
          <TableRow key={`${file.course_id}:${file.blob_path}`}>
            <TableCell className="font-medium truncate">{file.filename}</TableCell>
            <TableCell>
              <StatusBadge status={file.status} />
            </TableCell>
            <TableCell className="text-muted-foreground">
              {formatMaybeDate(file.processed_at)}
            </TableCell>
            <TableCell className={file.status === "failed" ? "text-destructive" : "text-muted-foreground"}>
              {file.status === "failed" ? file.last_error || "—" : "—"}
            </TableCell>
          </TableRow>
        ))}

        {poll && !allTerminal && (
          <TableRow>
            <TableCell colSpan={4} className="text-muted-foreground">
              <span className="inline-flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" />
                Updating statuses…
              </span>
            </TableCell>
          </TableRow>
        )}
      </TableBody>
    </Table>
  );
}
