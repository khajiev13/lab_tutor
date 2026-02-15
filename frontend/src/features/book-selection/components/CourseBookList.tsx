import { Badge } from '@/components/ui/badge';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { BookOpen, CheckCircle2, Upload } from 'lucide-react';
import type { CourseSelectedBook } from '../types';

interface CourseBookListProps {
  books: CourseSelectedBook[];
}

export function CourseBookList({ books }: CourseBookListProps) {
  if (books.length === 0) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-muted-foreground">
          <BookOpen className="mx-auto mb-3 h-8 w-8 opacity-40" />
          <p>No books associated with this course yet.</p>
        </CardContent>
      </Card>
    );
  }

  const ready = books.filter(
    (b) => b.status === 'downloaded' || b.status === 'uploaded',
  );

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-lg flex items-center gap-2">
          <BookOpen className="h-4 w-4" />
          Course Books
        </CardTitle>
        <CardDescription>
          {ready.length} of {books.length} books available
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Title</TableHead>
                <TableHead>Authors</TableHead>
                <TableHead className="w-20">Year</TableHead>
                <TableHead className="w-28">Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {books.map((book) => (
                <TableRow key={book.id}>
                  <TableCell className="font-medium max-w-xs truncate">
                    {book.title}
                  </TableCell>
                  <TableCell className="max-w-[200px] truncate text-muted-foreground">
                    {book.authors ?? '—'}
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {book.year ?? '—'}
                  </TableCell>
                  <TableCell>
                    {book.status === 'downloaded' && (
                      <Badge className="bg-green-500 hover:bg-green-600 gap-1">
                        <CheckCircle2 className="h-3 w-3" /> Ready
                      </Badge>
                    )}
                    {book.status === 'uploaded' && (
                      <Badge className="bg-blue-500 hover:bg-blue-600 gap-1">
                        <Upload className="h-3 w-3" /> Uploaded
                      </Badge>
                    )}
                    {book.status === 'failed' && (
                      <Badge variant="destructive">Failed</Badge>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}
