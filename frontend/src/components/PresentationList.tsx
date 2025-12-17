import { useEffect, useState } from 'react';
import { File, Trash2, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
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
} from '@/components/ui/alert-dialog';
import { presentationsApi } from '@/features/courses/api';
import { toast } from 'sonner';

interface PresentationListProps {
  courseId: number;
  refreshTrigger?: number; // Used to trigger a refresh from parent
  disabled?: boolean;
}

export function PresentationList({ courseId, refreshTrigger, disabled = false }: PresentationListProps) {
  const [files, setFiles] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [deletingFile, setDeletingFile] = useState<string | null>(null);

  useEffect(() => {
    const fetchFiles = async () => {
      try {
        const fileList = await presentationsApi.list(courseId);
        setFiles(fileList);
      } catch (error) {
        console.error('Failed to fetch presentations:', error);
        toast.error('Failed to load presentations');
      } finally {
        setIsLoading(false);
      }
    };

    fetchFiles();
  }, [courseId, refreshTrigger]);

  const handleDelete = async (filename: string) => {
    if (disabled) return;
    setDeletingFile(filename);
    try {
      await presentationsApi.delete(courseId, filename);
      setFiles((prev) => prev.filter((f) => f !== filename));
      toast.success('File deleted successfully');
    } catch (error) {
      console.error('Failed to delete file:', error);
      toast.error('Failed to delete file');
    } finally {
      setDeletingFile(null);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
      </div>
    );
  }

  if (files.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        No presentations uploaded yet.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {files.map((file) => (
        <div
          key={file}
          className="flex items-center justify-between p-3 border rounded-lg bg-card hover:bg-accent/50 transition-colors"
        >
          <div className="flex items-center gap-3 overflow-hidden">
            <div className="h-8 w-8 rounded bg-primary/10 flex items-center justify-center flex-shrink-0">
              <File className="h-4 w-4 text-primary" />
            </div>
            <span className="text-sm font-medium truncate">{file}</span>
          </div>
          
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-muted-foreground hover:text-destructive"
                disabled={!!deletingFile || disabled}
              >
                {deletingFile === file ? (
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
                  This will permanently delete "{file}". This action cannot be undone.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  onClick={() => handleDelete(file)}
                  className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                >
                  Delete
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      ))}
    </div>
  );
}
