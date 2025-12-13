import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { coursesApi, presentationsApi } from '@/services/api';
import type { Course } from '@/types';
import { FileUpload } from '@/components/FileUpload';
import { PresentationList } from '@/components/PresentationList';

export default function TeacherCourseDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [course, setCourse] = useState<Course | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  useEffect(() => {
    const fetchCourse = async () => {
      try {
        // Since we don't have a get-by-id endpoint, we list all and find
        const courses = await coursesApi.list();
        const foundCourse = courses.find((c) => c.id === Number(id));
        if (foundCourse) {
          setCourse(foundCourse);
        } else {
          toast.error('Course not found');
          navigate('/courses');
        }
      } catch (error) {
        toast.error('Failed to fetch course details');
        console.error(error);
        navigate('/courses');
      } finally {
        setIsLoading(false);
      }
    };

    if (id) {
      fetchCourse();
    }
  }, [id, navigate]);

  const handleUpload = async (files: File[]) => {
    if (!course) return;
    await presentationsApi.upload(course.id, files);
    setRefreshTrigger((prev) => prev + 1);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (!course) return null;

  return (
    <div className="container mx-auto py-8 max-w-4xl">
      <Button
        variant="ghost"
        className="mb-6 pl-0 hover:bg-transparent hover:text-primary"
        onClick={() => navigate('/courses')}
      >
        <ArrowLeft className="mr-2 h-4 w-4" />
        Back to Courses
      </Button>

      <div className="grid gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-2xl">{course.title}</CardTitle>
            <CardDescription className="text-base mt-2">
              {course.description || 'No description provided.'}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center text-sm text-muted-foreground">
              <span className="font-medium text-foreground mr-2">Created:</span>
              {new Date(course.created_at).toLocaleDateString()}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Course Materials</CardTitle>
            <CardDescription>
              Manage presentations and documents for this course.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <FileUpload onUpload={handleUpload} />
            <div className="border-t pt-6">
                <PresentationList courseId={course.id} refreshTrigger={refreshTrigger} />
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
