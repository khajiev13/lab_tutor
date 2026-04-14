import { useEffect, useMemo, useRef, useState } from "react";
import { File, Loader2, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { presentationsApi } from "@/features/courses/api";
import type {
  CourseEmbeddingStatusResponse,
  CourseFileRead,
  EmbeddingStatus,
  FileProcessingStatus,
} from "@/features/courses/types";

interface CourseMaterialsTableProps {
  courseId: number;
  refreshTrigger?: number;
  disabled?: boolean;
  poll?: boolean;
  pollIntervalMs?: number;
  embeddingStatus?: CourseEmbeddingStatusResponse | null;
  onFilesChange?: (files: string[]) => void;
  onProgressChange?: (stats: {
    total: number;
    processed: number;
    failed: number;
    terminal: number;
    value: number;
    allTerminal: boolean;
  }) => void;
}

type CombinedStatus = FileProcessingStatus | "not_available";

function StatusBadge({ status }: { status: CombinedStatus }) {
  switch (status) {
    case "pending":
      return <Badge variant="outline">Pending</Badge>;
    case "processing":
      return <Badge>Processing</Badge>;
    case "processed":
      return <Badge variant="secondary">Processed</Badge>;
    case "failed":
      return <Badge variant="destructive">Failed</Badge>;
    case "not_available":
      return <Badge variant="outline">Not processed</Badge>;
    default:
      return <Badge variant="outline">Unknown</Badge>;
  }
}

function EmbeddingBadge({ status }: { status: EmbeddingStatus }) {
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

function formatMaybeDate(iso: string | null | undefined) {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
}

export function CourseMaterialsTable({
  courseId,
  refreshTrigger,
  disabled = false,
  poll = false,
  pollIntervalMs = 1500,
  embeddingStatus,
  onFilesChange,
  onProgressChange,
}: CourseMaterialsTableProps) {
  const [files, setFiles] = useState<string[]>([]);
  const [statuses, setStatuses] = useState<CourseFileRead[]>([]);
  const [isInitialLoading, setIsInitialLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [deletingFile, setDeletingFile] = useState<string | null>(null);
  const [isDeletingAll, setIsDeletingAll] = useState(false);
  const hasLoadedOnceRef = useRef(false);

  const onFilesChangeRef = useRef<CourseMaterialsTableProps["onFilesChange"]>(onFilesChange);
  useEffect(() => {
    onFilesChangeRef.current = onFilesChange;
  }, [onFilesChange]);

  const statusByFilename = useMemo(() => {
    const map = new Map<string, CourseFileRead>();
    statuses.forEach((s) => map.set(s.filename, s));
    return map;
  }, [statuses]);

  const embeddingByFilename = useMemo(() => {
    const map = new Map<string, NonNullable<CourseMaterialsTableProps["embeddingStatus"]>["files"][number]>();
    embeddingStatus?.files?.forEach((f) => map.set(f.filename, f));
    return map;
  }, [embeddingStatus]);

  const rows = useMemo(() => {
    const all = new Set<string>();
    files.forEach((f) => all.add(f));
    statuses.forEach((s) => all.add(s.filename));
    return Array.from(all).sort((a, b) => a.localeCompare(b));
  }, [files, statuses]);

  const progressStats = useMemo(() => {
    const total = rows.length;
    let processed = 0;
    let failed = 0;
    let terminal = 0;

    rows.forEach((name) => {
      const s = statusByFilename.get(name)?.status;
      if (s === "processed") {
        processed += 1;
        terminal += 1;
      } else if (s === "failed") {
        failed += 1;
        terminal += 1;
      }
    });

    const value = total > 0 ? Math.round((terminal / total) * 100) : 0;
    return { total, processed, failed, terminal, value };
  }, [rows, statusByFilename]);

  const allTerminal = useMemo(() => {
    if (rows.length === 0) return false;
    // If a file has no status yet, treat it as non-terminal.
    return rows.every((name) => {
      const s = statusByFilename.get(name)?.status;
      return s === "processed" || s === "failed";
    });
  }, [rows, statusByFilename]);

  useEffect(() => {
    if (!poll) return;
    onProgressChange?.({ ...progressStats, allTerminal });
  }, [allTerminal, onProgressChange, poll, progressStats]);

  useEffect(() => {
    let cancelled = false;

    const fetchAll = async () => {
      if (hasLoadedOnceRef.current) setIsRefreshing(true);
      try {
        const [fileList, statusList] = await Promise.all([
          presentationsApi.list(courseId),
          presentationsApi.listStatuses(courseId),
        ]);
        if (cancelled) return;
        setFiles(fileList);
        onFilesChangeRef.current?.(fileList);
        setStatuses(statusList);
      } catch (error) {
        console.error("Failed to fetch course materials:", error);
        toast.error("Failed to load course materials");
      } finally {
        if (!cancelled) {
          setIsInitialLoading(false);
          setIsRefreshing(false);
          hasLoadedOnceRef.current = true;
        }
      }
    };

    fetchAll();
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

  const handleDelete = async (filename: string) => {
    if (disabled) return;
    setDeletingFile(filename);
    try {
      await presentationsApi.delete(courseId, filename);
      setFiles((prev) => {
        const next = prev.filter((f) => f !== filename);
        onFilesChangeRef.current?.(next);
        return next;
      });
      setStatuses((prev) => prev.filter((s) => s.filename !== filename));
      toast.success("File deleted successfully");
    } catch (error) {
      console.error("Failed to delete file:", error);
      toast.error("Failed to delete file");
    } finally {
      setDeletingFile(null);
    }
  };

  if (isInitialLoading && rows.length === 0) {
    return (
      <div className="flex items-center justify-center py-6">
        <Loader2 className="h-5 w-5 animate-spin text-primary" />
      </div>
    );
  }

  if (rows.length === 0) {
    return <div className="text-center py-8 text-muted-foreground">No presentations uploaded yet.</div>;
  }

  const colCount = embeddingStatus ? 5 : 4;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div className="text-xs text-muted-foreground">
          {rows.length} file{rows.length === 1 ? "" : "s"}
        </div>

        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button
              variant="destructive"
              size="sm"
              className="h-8"
              disabled={disabled || isRefreshing || isDeletingAll || !!deletingFile}
              aria-label="Delete all files"
            >
              {isDeletingAll ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="mr-2 h-4 w-4" />
              )}
              Delete all
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete all files?</AlertDialogTitle>
              <AlertDialogDescription>
                This will permanently delete all uploaded presentations for this course. This action cannot be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel disabled={isDeletingAll}>Cancel</AlertDialogCancel>
              <AlertDialogAction
                disabled={isDeletingAll}
                onClick={async () => {
                  if (disabled) return;
                  setIsDeletingAll(true);
                  try {
                    await presentationsApi.deleteAll(courseId);
                    setFiles([]);
                    setStatuses([]);
                    onFilesChangeRef.current?.([]);
                    toast.success("All files deleted successfully");
                  } catch (error) {
                    console.error("Failed to delete all files:", error);
                    toast.error("Failed to delete all files");
                  } finally {
                    setIsDeletingAll(false);
                  }
                }}
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              >
                Delete all files
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>

      {/* Use fixed table layout so long text wraps instead of forcing page-wide horizontal overflow */}
      <Table className="table-fixed">
        <TableHeader>
          <TableRow>
            {/* Let filename take remaining space; other columns are fixed-width so the table fits without horizontal scroll */}
            <TableHead>Filename</TableHead>
            <TableHead className="w-[120px]">Status</TableHead>
            {embeddingStatus && <TableHead className="w-[160px]">Embedding</TableHead>}
            <TableHead className="w-[220px]">Processed at</TableHead>
            <TableHead className="w-[140px] text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((filename) => {
            const status = statusByFilename.get(filename);
            const combinedStatus: CombinedStatus = status?.status ?? "not_available";
            const isDeletingThis = deletingFile === filename;
            const embeddingFile = embeddingStatus ? embeddingByFilename.get(filename) : undefined;

            return (
              <TableRow key={filename}>
                <TableCell className="font-medium">
                  <span className="inline-flex items-center gap-2 min-w-0">
                    <span className="h-7 w-7 rounded bg-primary/10 inline-flex items-center justify-center flex-shrink-0">
                      <File className="h-4 w-4 text-primary" />
                    </span>
                    <span className="truncate">{filename}</span>
                  </span>
                </TableCell>
                <TableCell>
                  <StatusBadge status={combinedStatus} />
                </TableCell>

                {embeddingStatus && (
                  <TableCell>
                    {embeddingFile ? (
                      <EmbeddingBadge status={embeddingFile.embedding_status} />
                    ) : (
                      <Badge variant="outline">—</Badge>
                    )}
                  </TableCell>
                )}

                <TableCell className="text-muted-foreground tabular-nums whitespace-nowrap">
                  {formatMaybeDate(status?.processed_at)}
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex items-center justify-end gap-2">
                    {combinedStatus === "failed" && status?.last_error && (
                      <Dialog>
                        <DialogTrigger asChild>
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-8"
                            aria-label={`View error for ${filename}`}
                          >
                            View
                          </Button>
                        </DialogTrigger>
                        <DialogContent className="sm:max-w-2xl">
                          <DialogHeader>
                            <DialogTitle>Error details</DialogTitle>
                            <DialogDescription className="break-words">
                              {filename}
                            </DialogDescription>
                          </DialogHeader>
                          <div className="max-h-[55vh] overflow-auto rounded-md border bg-muted/20 p-3">
                            <pre className="text-xs leading-relaxed whitespace-pre-wrap break-words font-mono">
                              {status.last_error}
                            </pre>
                          </div>
                          <DialogFooter>
                            <DialogClose asChild>
                              <Button variant="outline">Close</Button>
                            </DialogClose>
                            <Button
                              onClick={async () => {
                                try {
                                  await navigator.clipboard.writeText(status.last_error ?? "");
                                  toast.success("Copied error to clipboard");
                                } catch {
                                  toast.error("Failed to copy");
                                }
                              }}
                            >
                              Copy
                            </Button>
                          </DialogFooter>
                        </DialogContent>
                      </Dialog>
                    )}

                    {embeddingStatus &&
                      embeddingFile?.embedding_status === "failed" &&
                      embeddingFile.embedding_last_error && (
                        <Dialog>
                          <DialogTrigger asChild>
                            <Button
                              variant="outline"
                              size="sm"
                              className="h-8"
                              aria-label={`View embedding error for ${filename}`}
                            >
                              View
                            </Button>
                          </DialogTrigger>
                          <DialogContent className="sm:max-w-2xl">
                            <DialogHeader>
                              <DialogTitle>Embedding error details</DialogTitle>
                              <DialogDescription className="break-words">
                                {filename}
                              </DialogDescription>
                            </DialogHeader>
                            <div className="max-h-[55vh] overflow-auto rounded-md border bg-muted/20 p-3">
                              <pre className="text-xs leading-relaxed whitespace-pre-wrap break-words font-mono">
                                {embeddingFile.embedding_last_error}
                              </pre>
                            </div>
                            <DialogFooter>
                              <DialogClose asChild>
                                <Button variant="outline">Close</Button>
                              </DialogClose>
                              <Button
                                onClick={async () => {
                                  try {
                                    await navigator.clipboard.writeText(embeddingFile.embedding_last_error ?? "");
                                    toast.success("Copied error to clipboard");
                                  } catch {
                                    toast.error("Failed to copy");
                                  }
                                }}
                              >
                                Copy
                              </Button>
                            </DialogFooter>
                          </DialogContent>
                        </Dialog>
                      )}

                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-muted-foreground hover:text-destructive"
                          disabled={disabled || !!deletingFile || isRefreshing}
                          aria-label={`Delete ${filename}`}
                        >
                          {isDeletingThis ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Trash2 className="h-4 w-4" />
                          )}
                        </Button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>Are you sure?</AlertDialogTitle>
                          <AlertDialogDescription>
                            This will permanently delete "{filename}". This action cannot be undone.
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Cancel</AlertDialogCancel>
                          <AlertDialogAction
                            onClick={() => handleDelete(filename)}
                            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                          >
                            Delete
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </div>
                </TableCell>
              </TableRow>
            );
          })}

          {poll && !allTerminal && (
            <TableRow>
              <TableCell colSpan={colCount} className="text-muted-foreground">
                <span className="inline-flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Updating statuses…
                </span>
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
}


