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
import { presentationsApi } from '@/services/api';
import { toast } from 'sonner';

interface PresentationListProps {
  courseId: number;
  refreshTrigger?: number; // Used to trigger a refresh from parent
}

export function PresentationList({ courseId, refreshTrigger }: PresentationListProps) {
  const [files, setFiles] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isDeleting, setIsDeleting] = useState(false);
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

  const handleDeleteAll = async () => {
    setIsDeleting(true);
    try {
      await presentationsApi.deleteAll(courseId);
      setFiles([]);
      toast.success('All files deleted successfully');
    } catch (error) {
      console.error('Failed to delete all files:', error);
      toast.error('Failed to delete all files');
    } finally {
      setIsDeleting(false);
    }
  };

  if (isLoading) {
    return <div className="text-sm text-muted-foreground">Loading presentations...</div>;
  }

  if (files.length === 0) {
    return <div className="text-sm text-muted-foreground italic">No presentations uploaded yet.</div>;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-medium">Course Presentations</h3>
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button variant="destructive" size="sm" disabled={isDeleting}>
              <Trash2 className="mr-2 h-4 w-4" />
              Delete All
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Are you sure?</AlertDialogTitle>
              <AlertDialogDescription>
                This action cannot be undone. This will permanently delete all presentation files for this course.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction onClick={handleDeleteAll} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
                Delete All
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>

      <div className="grid gap-2">
        {files.map((filename) => (
          <div
            key={filename}
            className="flex items-center justify-between p-3 border rounded-md bg-card hover:bg-accent/50 transition-colors"
          >
            <div className="flex items-center gap-3 overflow-hidden">
              <File className="h-5 w-5 flex-shrink-0 text-primary" />
              <span className="text-sm font-medium truncate">{filename}</span>
            </div>
            <div className="flex items-center gap-2">
                {/* Add a download/view button if needed, for now just delete */}
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-muted-foreground hover:text-destructive"
                      disabled={deletingFile === filename}
                    >
                      {deletingFile === filename ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Trash2 className="h-4 w-4" />
                      )}
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Delete File</AlertDialogTitle>
                      <AlertDialogDescription>
                        Are you sure you want to delete "{filename}"? This action cannot be undone.
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
          </div>
        ))}
      </div>
    </div>
  );
}
