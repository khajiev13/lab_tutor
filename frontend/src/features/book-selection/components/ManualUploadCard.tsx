import { useState, useRef } from 'react';
import axios from 'axios';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Loader2, Upload, Plus } from 'lucide-react';
import { uploadCustomSelectedBook } from '../api';
import type { CourseSelectedBook } from '../types';
import { toast } from 'sonner';

interface ManualUploadCardProps {
  courseId: number;
  onUploaded: (book: CourseSelectedBook) => void;
}

export function ManualUploadCard({ courseId, onUploaded }: ManualUploadCardProps) {
  const [title, setTitle] = useState('');
  const [authors, setAuthors] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleSubmit = async () => {
    if (!file || !title.trim()) return;
    setUploading(true);
    try {
      const book = await uploadCustomSelectedBook(
        courseId,
        file,
        title.trim(),
        authors.trim() || undefined,
      );
      toast.success(`"${title}" uploaded successfully`);
      onUploaded(book);
      setTitle('');
      setAuthors('');
      setFile(null);
      if (fileRef.current) fileRef.current.value = '';
    } catch (err) {
      const message =
        axios.isAxiosError(err) && err.response?.data?.detail
          ? err.response.data.detail
          : err instanceof Error
            ? err.message
            : 'Unknown error';
      toast.error(`Upload failed: ${message}`);
    } finally {
      setUploading(false);
    }
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-lg flex items-center gap-2">
          <Plus className="h-4 w-4" />
          Add Your Own Book
        </CardTitle>
        <CardDescription>
          Upload a book PDF that wasn't discovered by the AI agent.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1">
            <Label htmlFor="book-title">Title *</Label>
            <Input
              id="book-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Data Structures & Algorithms"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="book-authors">Authors</Label>
            <Input
              id="book-authors"
              value={authors}
              onChange={(e) => setAuthors(e.target.value)}
              placeholder="e.g. Cormen, Leiserson"
            />
          </div>
        </div>

        <div className="space-y-1">
          <Label>PDF File *</Label>
          <div className="flex items-center gap-3">
            <input
              ref={fileRef}
              type="file"
              accept=".pdf"
              className="hidden"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            <Button
              variant="outline"
              size="sm"
              onClick={() => fileRef.current?.click()}
            >
              <Upload className="mr-1 h-3 w-3" />
              {file ? file.name : 'Choose file'}
            </Button>
            {file && (
              <span className="text-xs text-muted-foreground">
                {(file.size / 1024 / 1024).toFixed(1)} MB
              </span>
            )}
          </div>
        </div>

        <Button
          onClick={handleSubmit}
          disabled={!title.trim() || !file || uploading}
          className="w-full"
        >
          {uploading ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Upload className="mr-2 h-4 w-4" />
          )}
          Upload Book
        </Button>
      </CardContent>
    </Card>
  );
}
