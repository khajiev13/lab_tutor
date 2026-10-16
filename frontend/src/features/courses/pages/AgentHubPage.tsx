import { useCallback, useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Loader2 } from "lucide-react";

import { useAuth } from "@/features/auth/context/AuthContext";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
} from "@/components/ui/card";
import { LogIn, LogOut } from "lucide-react";
import { toast } from "sonner";
import { coursesApi } from "@/features/courses/api";
import {
  CourseDetailProvider,
  useCourseDetail,
} from "@/features/courses/context/CourseDetailContext";
import { CourseHeader } from "@/features/courses/components/CourseHeader";
import { CourseReadinessRoad } from "@/features/courses/components/readiness/CourseReadinessRoad";
import { AgentHubGrid } from "@/features/agents/components/AgentHubGrid";
import {
  LEARNING_ANALYTICS_AGENTS,
  SKILL_RESOURCE_AGENTS,
} from "@/features/agents/config";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { useCourseReadiness } from "@/features/courses/hooks/useCourseReadiness";
import { CourseProgressFeedback } from "@/features/courses/components/readiness/CourseProgressFeedback";
import { TeacherAgentTimingDialog } from "@/features/agents/components/TeacherAgentTimingDialog";

import { MaterialsReadinessNotice } from "@/features/courses/components/readiness/MaterialsReadinessNotice";

/* ── Teacher course setup ───────────────────────────────────── */

function HubContent() {
  const { courseId, isLoading, materialsReady, materialsMessage } = useCourseDetail();
  const { readiness, error, refresh } = useCourseReadiness(courseId);
  const [insightAgentId, setInsightAgentId] = useState<"architect" | "market-analyst" | null>(null);
  const nextAgent = readiness?.next_action.id === "book"
    ? "architect"
    : readiness?.next_action.id === "market" ? "market-analyst" : null;

  return (
    <>
      <CourseHeader compact />
      {!materialsReady && <MaterialsReadinessNotice courseId={courseId} message={materialsMessage} />}
      {readiness ? (
        <CourseReadinessRoad
          readiness={readiness}
          onRefresh={refresh}
          onLearnMore={nextAgent ? () => setInsightAgentId(nextAgent) : undefined}
        />
      ) : <CourseProgressFeedback error={error} onRetry={refresh} />}

      <Accordion type="single" collapsible className="rounded-xl border px-5 sm:px-6">
        <AccordionItem value="course-tools">
          <AccordionTrigger className="py-5 hover:no-underline">
            <span className="space-y-1">
              <span className="block text-base font-semibold">More course tools</span>
              <span className="block text-sm font-normal text-muted-foreground">Learning resources and class insights, whenever you need them.</span>
            </span>
          </AccordionTrigger>
          <AccordionContent className="space-y-6 pb-6">
            <section className="space-y-3">
              <div>
                <h2 className="font-medium">Learning resources</h2>
                <p className="mt-1 text-sm text-muted-foreground">Reading and video resources for the skills students choose.</p>
              </div>
              <AgentHubGrid agents={SKILL_RESOURCE_AGENTS} disabledAgentIds={materialsReady ? [] : ["reading-agent", "video-agent"]} courseId={courseId} isLoading={isLoading} statuses={{}} />
            </section>
            <section className="space-y-3">
              <div>
                <h2 className="font-medium">Class insights</h2>
                <p className="mt-1 text-sm text-muted-foreground">Explore student progress and learning needs once teaching begins.</p>
              </div>
              <AgentHubGrid agents={LEARNING_ANALYTICS_AGENTS} courseId={courseId} isLoading={isLoading} statuses={{}} />
            </section>
          </AccordionContent>
        </AccordionItem>
      </Accordion>
      <TeacherAgentTimingDialog
        disabled={!materialsReady && insightAgentId === "market-analyst"}
        courseId={courseId}
        agentId={insightAgentId}
        open={insightAgentId !== null}
        onOpenChange={(open) => { if (!open) setInsightAgentId(null); }}
      />
    </>
  );
}

/* ── Student content ─────────────────────────────────────────── */

function StudentContent({ courseId }: { courseId: number }) {
  const [isEnrolled, setIsEnrolled] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const navigate = useNavigate();

  const checkEnrollment = useCallback(async () => {
    try {
      const enrollment = await coursesApi.getEnrollment(courseId);
      setIsEnrolled(!!enrollment);
    } catch {
      /* ignore */
    }
  }, [courseId]);

  useEffect(() => {
    checkEnrollment();
  }, [checkEnrollment]);

  const handleJoin = async () => {
    setIsLoading(true);
    try {
      await coursesApi.join(courseId);
      setIsEnrolled(true);
      toast.success("Successfully joined the course!");
    } catch {
      toast.error("Failed to join course");
    } finally {
      setIsLoading(false);
    }
  };

  const handleLeave = async () => {
    setIsLoading(true);
    try {
      await coursesApi.leave(courseId);
      setIsEnrolled(false);
      toast.success("Successfully left the course");
    } catch {
      toast.error("Failed to leave course");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex justify-between items-center">
          <h2 className="text-xl font-semibold">Student Dashboard</h2>
          <Button
            onClick={isEnrolled ? handleLeave : handleJoin}
            disabled={isLoading}
            variant={isEnrolled ? "destructive" : "default"}
          >
            {isLoading ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : isEnrolled ? (
              <>
                <LogOut className="mr-2 h-4 w-4" />
                Leave Course
              </>
            ) : (
              <>
                <LogIn className="mr-2 h-4 w-4" />
                Join Course
              </>
            )}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          {isEnrolled
            ? "You are enrolled in this course. You can now build your personalized learning path."
            : "Join this course to access materials and build a personalized learning path."}
        </p>

        {isEnrolled && (
          <Button 
            className="w-full sm:w-auto" 
            onClick={() => navigate(`/courses/${courseId}/learning-path`)}
          >
            Go to My Learning Path
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

/* ── Page ─────────────────────────────────────────────────────── */

export default function AgentHubPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();

  const courseId = Number(id);
  if (!id || isNaN(courseId)) {
    navigate("/courses");
    return null;
  }

  return (
    <CourseDetailProvider key={courseId} courseId={courseId} checkMaterials={user?.role === "teacher"}>
      <div className="mx-auto w-full max-w-6xl space-y-6 pb-8">
        <Button
          variant="ghost"
          className="pl-0 hover:bg-transparent hover:text-primary"
          onClick={() => navigate("/courses")}
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Courses
        </Button>

        {user?.role === "teacher" ? (
          <HubContent />
        ) : (
          <StudentContent courseId={courseId} />
        )}
      </div>
    </CourseDetailProvider>
  );
}
