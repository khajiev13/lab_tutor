import { useState, useRef } from 'react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Progress } from '@/components/ui/progress';
import {
  CheckCircle2,
  Download,
  ExternalLink,
  EyeOff,
  Loader2,
  RotateCcw,
  Upload,
  XCircle,
  FileText,
} from 'lucide-react';
import type { CourseSelectedBook, StreamEvent } from '../types';
import { ignoreSelectedBook, uploadToSelectedBook } from '../api';
import { toast } from 'sonner';

interface DownloadStatusPanelProps {
  selectedBooks: CourseSelectedBook[];
  downloadEvents: StreamEvent[];
  isDownloading: boolean;
  onRefresh: () => void;
  onReselect?: () => void;
  isReselecting?: boolean;
}

export function DownloadStatusPanel({
  selectedBooks,
  downloadEvents,
  isDownloading,
  onRefresh,
  onReselect,
  isReselecting,
}: DownloadStatusPanelProps) {
  const doneCount = selectedBooks.filter(
    (b) => b.status === 'downloaded' || b.status === 'uploaded',
  ).length;

  const failedCount = selectedBooks.filter(
    (b) => b.status === 'failed',
  ).length;

  const ignoredCount = selectedBooks.filter(
    (b) => b.status === 'ignored',
  ).length;

  const activeTotal = selectedBooks.length - ignoredCount;

  const progressPct =
    activeTotal > 0
      ? Math.round((doneCount / activeTotal) * 100)
      : 0;

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-lg flex items-center gap-2">
              <Download className="h-4 w-4" />
              Download Status
            </CardTitle>
            <CardDescription>
              {isDownloading
                ? 'Downloading selected books...'
                : `${doneCount}/${activeTotal} books ready`}
            </CardDescription>
          </div>
          {failedCount > 0 && !isDownloading && (
            <Badge variant="destructive">
              {failedCount} failed — upload manually below
            </Badge>
          )}
          {!isDownloading && onReselect && (
            <Button
              variant="outline"
              size="sm"
              onClick={onReselect}
              disabled={isReselecting}
            >
              {isReselecting ? (
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              ) : (
                <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
              )}
              Reselect Books
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {isDownloading && (
          <div className="space-y-1">
            <Progress value={progressPct} />
            <p className="text-xs text-muted-foreground text-right tabular-nums">
              {doneCount}/{activeTotal}
            </p>
          </div>
        )}

        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Title</TableHead>
                <TableHead className="w-32">Status</TableHead>
                <TableHead className="w-28" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {selectedBooks.map((book) => (
                <DownloadRow
                  key={book.id}
                  book={book}
                  onUploaded={onRefresh}
                />
              ))}
            </TableBody>
          </Table>
        </div>

        {/* Activity events */}
        {downloadEvents.length > 0 && (
          <div className="space-y-1 max-h-32 overflow-y-auto">
            {downloadEvents.slice(-6).map((evt, i) => (
              <p
                key={i}
                className="text-xs text-muted-foreground/70 font-mono truncate"
              >
                {evt.message}
              </p>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function DownloadRow({
  book,
  onUploaded,
}: {
  book: CourseSelectedBook;
  onUploaded: () => void;
}) {
  const [uploading, setUploading] = useState(false);
  const [ignoring, setIgnoring] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleUpload = async (file: File) => {
    setUploading(true);
    try {
      await uploadToSelectedBook(book.id, file);
      toast.success(`Uploaded "${book.title}" successfully`);
      onUploaded();
    } catch (err) {
      toast.error(`Upload failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setUploading(false);
    }
  };

  const handleIgnore = async () => {
    setIgnoring(true);
    try {
      await ignoreSelectedBook(book.id);
      toast.success(`Ignored "${book.title}"`);
      onUploaded();
    } catch (err) {
      toast.error(`Ignore failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setIgnoring(false);
    }
  };

  return (
    <TableRow>
      <TableCell className="font-medium max-w-xs truncate">
        {book.title}
      </TableCell>
      <TableCell>
        <StatusBadge status={book.status} />
      </TableCell>
      <TableCell className="space-x-1">
        {book.status === 'failed' && (
          <>
            {/* Show a link to the PDF if the error message contains a URL */}
            {book.error_message && extractUrl(book.error_message) && (
              <Button
                size="sm"
                variant="ghost"
                asChild
              >
                <a
                  href={extractUrl(book.error_message)!}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <ExternalLink className="mr-1 h-3 w-3" />
                  Link
                </a>
              </Button>
            )}
            <input
              ref={fileRef}
              type="file"
              accept=".pdf"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleUpload(f);
              }}
            />
            <Button
              size="sm"
              variant="outline"
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
            >
              {uploading ? (
                <Loader2 className="mr-1 h-3 w-3 animate-spin" />
              ) : (
                <Upload className="mr-1 h-3 w-3" />
              )}
              Upload
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={handleIgnore}
              disabled={ignoring}
            >
              {ignoring ? (
                <Loader2 className="mr-1 h-3 w-3 animate-spin" />
              ) : (
                <EyeOff className="mr-1 h-3 w-3" />
              )}
              Ignore
            </Button>
          </>
        )}
        {(book.status === 'downloaded' || book.status === 'uploaded') && (
          <FileText className="h-4 w-4 text-green-500" />
        )}
      </TableCell>
    </TableRow>
  );
}

/** Extract the first URL from a string (e.g. an error message). */
function extractUrl(text: string): string | null {
  const match = text.match(/https?:\/\/[^\s)]+/);
  return match ? match[0] : null;
}

function StatusBadge({ status }: { status: string }) {
  switch (status) {
    case 'downloaded':
      return (
        <Badge className="bg-green-500 hover:bg-green-600 gap-1">
          <CheckCircle2 className="h-3 w-3" /> Downloaded
        </Badge>
      );
    case 'uploaded':
      return (
        <Badge className="bg-blue-500 hover:bg-blue-600 gap-1">
          <Upload className="h-3 w-3" /> Uploaded
        </Badge>
      );
    case 'failed':
      return (
        <Badge variant="destructive" className="gap-1">
          <XCircle className="h-3 w-3" /> Failed
        </Badge>
      );
    case 'ignored':
      return (
        <Badge variant="secondary" className="gap-1">
          <EyeOff className="h-3 w-3" /> Ignored
        </Badge>
      );
    default:
      return <Badge variant="outline">{status}</Badge>;
  }
}
