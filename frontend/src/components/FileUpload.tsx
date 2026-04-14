import { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { Upload, File as FileIcon, X, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { CourseFileDuplicateError } from '@/features/courses/errors';

interface FileUploadProps {
  onUpload: (files: File[]) => Promise<void>;
  disabled?: boolean;
}

export function FileUpload({ onUpload, disabled = false }: FileUploadProps) {
  const [isUploading, setIsUploading] = useState(false);
  const [files, setFiles] = useState<File[]>([]);

  const onDrop = useCallback((acceptedFiles: File[]) => {
    setFiles((prev) => [...prev, ...acceptedFiles]);
  }, []);

  const hasFilesDragType = (types?: readonly string[] | string[]) => {
    if (!types) return false;
    return Array.from(types).some((t) => t === 'Files' || t === 'application/x-moz-file');
  };

  const filterAcceptedByExtension = (candidateFiles: File[]) => {
    const acceptedExts = ['.pdf', '.pptx', '.ppt', '.txt', '.docx', '.doc'];
    const accepted: File[] = [];
    const rejected: File[] = [];

    for (const f of candidateFiles) {
      const name = (f?.name || '').toLowerCase();
      if (acceptedExts.some((ext) => name.endsWith(ext))) accepted.push(f);
      else rejected.push(f);
    }

    return { accepted, rejected };
  };

  const onDropFallback = useCallback(
    (event: React.DragEvent<HTMLElement>) => {
      // `react-dropzone` only processes drops when `dataTransfer.types` includes "Files"
      // (or Firefox's "application/x-moz-file"). Some browsers (notably Safari) may
      // report different types like "public.file-url", which makes drop silently no-op.
      if (disabled || isUploading) return;

      const dt = event.dataTransfer;
      if (!dt) return;

      // If it's a normal "Files" drag, let react-dropzone handle it to avoid duplicates.
      if (hasFilesDragType(dt.types)) return;

      const dropped = Array.from(dt.files ?? []);
      if (dropped.length === 0) return;

      event.preventDefault();
      event.stopPropagation();

      const { accepted, rejected } = filterAcceptedByExtension(dropped);
      if (rejected.length > 0)
        toast.error('Some files were skipped (only PDF/PPT/PPTX/TXT/DOCX/DOC are supported).');
      if (accepted.length > 0) setFiles((prev) => [...prev, ...accepted]);
    },
    [disabled, isUploading]
  );

  const onDragOverFallback = useCallback(
    (event: React.DragEvent<HTMLElement>) => {
      if (disabled || isUploading) return;
      const dt = event.dataTransfer;
      if (!dt) return;

      // Allow drops for Safari-style drags too.
      if (!hasFilesDragType(dt.types)) {
        event.preventDefault();
      }
    },
    [disabled, isUploading]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'application/vnd.openxmlformats-officedocument.presentationml.presentation': ['.pptx'],
      'application/vnd.ms-powerpoint': ['.ppt'],
      'text/plain': ['.txt'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'application/msword': ['.doc'],
    },
    disabled: disabled || isUploading,
    onDropRejected: () => {
      toast.error('Unsupported file type (only PDF/PPT/PPTX/TXT/DOCX/DOC are supported).');
    },
  });

  const removeFile = (fileToRemove: File) => {
    setFiles((prev) => prev.filter((file) => file !== fileToRemove));
  };

  const handleUpload = async () => {
    if (files.length === 0) return;

    setIsUploading(true);
    try {
      await onUpload(files);
      toast.success('Files uploaded successfully');
      setFiles([]);
    } catch (error) {
      console.error('Upload failed:', error);
      if (error instanceof CourseFileDuplicateError) {
        toast.error('Already uploaded', {
          description: error.existingFilename
            ? `Previously uploaded as: ${error.existingFilename}`
            : undefined,
        });
      } else {
        toast.error('Upload failed, try again');
      }
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="w-full space-y-4">
      <div
        {...getRootProps({
          onDrop: onDropFallback,
          onDragOver: onDragOverFallback,
          'data-testid': 'dropzone-root',
        })}
        className={cn(
          "border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors",
          isDragActive ? "border-primary bg-primary/5" : "border-muted-foreground/25 hover:border-primary/50",
          (disabled || isUploading) && "opacity-50 cursor-not-allowed hover:border-muted-foreground/25"
        )}
      >
        <input {...getInputProps()} data-testid="dropzone-input" />
        <div className="flex flex-col items-center gap-2">
          <div className="p-4 rounded-full bg-muted">
            <Upload className="h-6 w-6 text-muted-foreground" />
          </div>
          <div className="space-y-1">
            <p className="text-sm font-medium">
              {isDragActive ? "Drop files here" : "Drag & drop files here"}
            </p>
            <p className="text-xs text-muted-foreground">
              or click to select files (PDF, PPTX, PPT, TXT, DOCX, DOC)
            </p>
          </div>
        </div>
      </div>

      {files.length > 0 && (
        <div className="space-y-4">
          <div className="space-y-2">
            {files.map((file, index) => (
              <div
                key={`${file.name}-${index}`}
                className="flex items-center justify-between p-3 border rounded-lg bg-card"
              >
                <div className="flex items-center gap-3 overflow-hidden">
                  <div className="h-8 w-8 rounded bg-primary/10 flex items-center justify-center flex-shrink-0">
                    <FileIcon className="h-4 w-4 text-primary" />
                  </div>
                  <div className="flex flex-col min-w-0">
                    <span className="text-sm font-medium truncate">{file.name}</span>
                    <span className="text-xs text-muted-foreground">
                      {(file.size / 1024 / 1024).toFixed(2)} MB
                    </span>
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => removeFile(file)}
                  disabled={isUploading}
                  className="h-8 w-8 text-muted-foreground hover:text-destructive"
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            ))}
          </div>

          <div className="flex justify-end">
            <Button onClick={handleUpload} disabled={isUploading || disabled}>
              {isUploading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {isUploading ? 'Uploading...' : `Upload ${files.length} file${files.length === 1 ? '' : 's'}`}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
