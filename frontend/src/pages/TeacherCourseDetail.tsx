import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Loader2, Play, AlertCircle, CheckCircle2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Progress } from '@/components/ui/progress';
import { coursesApi, presentationsApi } from '@/services/api';
import type { Course, ExtractionStatus } from '@/types';
import { FileUpload } from '@/components/FileUpload';
import { PresentationList } from '@/components/PresentationList';

export default function TeacherCourseDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [course, setCourse] = useState<Course | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [isExtracting, setIsExtracting] = useState(false);

  const fetchCourse = useCallback(async () => {
    if (!id) return;
    try {
      const data = await coursesApi.getCourse(Number(id));
      setCourse(data);
    } catch (error) {
      toast.error('Failed to fetch course details');
      console.error(error);
      navigate('/courses');
    } finally {
      setIsLoading(false);
    }
  }, [id, navigate]);

  useEffect(() => {
    fetchCourse();
  }, [fetchCourse]);

  // Polling for extraction status
  useEffect(() => {
    let intervalId: NodeJS.Timeout;

    if (course?.extraction_status === 'in_progress') {
      intervalId = setInterval(async () => {
        if (!id) return;
        try {
          const updatedCourse = await coursesApi.getCourse(Number(id));
          setCourse(updatedCourse);
          
          if (updatedCourse.extraction_status !== 'in_progress') {
            if (updatedCourse.extraction_status === 'finished') {
              toast.success('Data extraction completed successfully!');
            } else if (updatedCourse.extraction_status === 'failed') {
              toast.error('Data extraction failed.');
            }
          }
        } catch (error) {
          console.error('Polling failed', error);
        }
      }, 3000); // Poll every 3 seconds
    }

    return () => {
      if (intervalId) clearInterval(intervalId);
    };
  }, [course?.extraction_status, id]);

  const handleUpload = async (files: File[]) => {
    if (!course) return;
    if (course.extraction_status === 'in_progress') {
      toast.error('Cannot modify files while extraction is in progress');
      return;
    }
    await presentationsApi.upload(course.id, files);
    setRefreshTrigger((prev) => prev + 1);
  };

  const handleStartExtraction = async () => {
    if (!course) return;
    setIsExtracting(true);
    try {
      const response = await coursesApi.startExtraction(course.id);
      toast.success(response.message);
      // Update local state immediately
      setCourse(prev => prev ? { ...prev, extraction_status: response.status } : null);
    } catch (error) {
      toast.error('Failed to start extraction');
      console.error(error);
    } finally {
      setIsExtracting(false);
    }
  };

  const getStatusBadge = (status: ExtractionStatus) => {
    switch (status) {
      case 'not_started':
        return <Badge variant="secondary">Ready to Extract</Badge>;
      case 'in_progress':
        return <Badge variant="default" className="bg-blue-500 hover:bg-blue-600">Extracting Data...</Badge>;
      case 'finished':
        return <Badge variant="default" className="bg-green-500 hover:bg-green-600">Extraction Complete</Badge>;
      case 'failed':
        return <Badge variant="destructive">Extraction Failed</Badge>;
      default:
        return <Badge variant="outline">Unknown</Badge>;
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (!course) return null;

  const isExtractionInProgress = course.extraction_status === 'in_progress';

  return (
    <div className="container mx-auto py-8 max-w-4xl space-y-6">
      <div className="flex items-center justify-between">
        <Button
          variant="ghost"
          className="pl-0 hover:bg-transparent hover:text-primary"
          onClick={() => navigate('/courses')}
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Courses
        </Button>
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">Status:</span>
          {getStatusBadge(course.extraction_status)}
        </div>
      </div>

      <Card>
        <CardHeader>
          <div className="flex justify-between items-start">
            <div>
              <CardTitle className="text-2xl">{course.title}</CardTitle>
              <CardDescription className="text-base mt-2">
                {course.description || 'No description provided.'}
              </CardDescription>
            </div>
            {(course.extraction_status === 'not_started' || course.extraction_status === 'failed') && (
              <Button onClick={handleStartExtraction} disabled={isExtracting}>
                {isExtracting ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Play className="mr-2 h-4 w-4" />
                )}
                Start Data Extraction
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex items-center text-sm text-muted-foreground">
            <span className="font-medium text-foreground mr-2">Created:</span>
            {new Date(course.created_at).toLocaleDateString()}
          </div>
          
          {isExtractionInProgress && (
            <div className="mt-6 space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="text-blue-500 font-medium flex items-center">
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Processing course materials...
                </span>
                <span className="text-muted-foreground">Please wait</span>
              </div>
              <Progress value={45} className="w-full animate-pulse" />
              <p className="text-xs text-muted-foreground">
                This process may take a few minutes depending on the size of your presentations.
              </p>
            </div>
          )}

          {course.extraction_status === 'failed' && (
            <Alert variant="destructive" className="mt-6">
              <AlertCircle className="h-4 w-4" />
              <AlertTitle>Extraction Failed</AlertTitle>
              <AlertDescription>
                There was an error processing your course materials. Please check your files and try again.
              </AlertDescription>
            </Alert>
          )}

          {course.extraction_status === 'finished' && (
            <Alert className="mt-6 border-green-500 text-green-600 bg-green-50 dark:bg-green-950/20">
              <CheckCircle2 className="h-4 w-4 text-green-600" />
              <AlertTitle>Ready for Students</AlertTitle>
              <AlertDescription>
                Your course data has been successfully extracted and is ready for the knowledge graph.
              </AlertDescription>
            </Alert>
          )}
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
          <div className={isExtractionInProgress ? "opacity-50 pointer-events-none" : ""}>
            <FileUpload onUpload={handleUpload} disabled={isExtractionInProgress} />
          </div>
          
          {isExtractionInProgress && (
            <Alert className="bg-muted/50">
              <AlertCircle className="h-4 w-4" />
              <AlertTitle>File Management Locked</AlertTitle>
              <AlertDescription>
                You cannot upload or delete files while data extraction is in progress.
              </AlertDescription>
            </Alert>
          )}

          <div className="border-t pt-6">
              <PresentationList 
                courseId={course.id} 
                refreshTrigger={refreshTrigger} 
                disabled={isExtractionInProgress}
              />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
