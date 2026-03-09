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
import { coursesApi } from "../api";
import {
  CourseDetailProvider,
  useCourseDetail,
} from "../context/CourseDetailContext";
import { CourseHeader } from "../components/CourseHeader";
import { AgentHubGrid } from "@/features/agents/components/AgentHubGrid";
import type { AgentStatus } from "@/features/agents/components/AgentCard";

/* ── Derive architect status from context ──────────────────── */

function useArchitectStatus(): {
  status: AgentStatus;
  progress: number;
  lastActivity: string;
} {
  const { course, getStepStatus } = useCourseDetail();

  if (!course) return { status: "not-started", progress: 0, lastActivity: "" };

  // Count completed steps
  let completedSteps = 0;
  let activeStep = -1;
  const stepLabels = [
    "Upload Materials",
    "Normalize Concepts",
    "Select Books",
    "Analyze Books",
    "Visualize Results",
  ];

  for (let i = 0; i < 5; i++) {
    const s = getStepStatus(i);
    if (s === "completed") completedSteps++;
    if (s === "active" && activeStep === -1) activeStep = i;
  }

  const progress = (completedSteps / 5) * 100;

  let status: AgentStatus = "not-started";
  if (completedSteps === 5) {
    status = "completed";
  } else if (completedSteps > 0 || activeStep >= 0 || course.extraction_status === "in_progress") {
    status = "in-progress";
  }

  let lastActivity = "";
  if (activeStep >= 0) {
    lastActivity = `Working on: ${stepLabels[activeStep]}`;
  } else if (completedSteps === 5) {
    lastActivity = "All steps complete";
  } else if (completedSteps > 0) {
    lastActivity = `${completedSteps}/5 steps complete`;
  }

  return { status, progress, lastActivity };
}

/* ── Hub content (rendered inside provider) ────────────────── */

function HubContent() {
  const { isLoading } = useCourseDetail();
  const { courseId } = useCourseDetail();
  const architectInfo = useArchitectStatus();

  const statuses: Record<string, { status: AgentStatus; progress?: number; lastActivity?: string }> = {
    architect: architectInfo,
  };

  return (
    <>
      <CourseHeader />
      <div className="mt-6">
        <h2 className="text-lg font-semibold mb-4">AI Agents</h2>
        <AgentHubGrid courseId={courseId} isLoading={isLoading} statuses={statuses} />
      </div>
    </>
  );
}

/* ── Student content ─────────────────────────────────────────── */

function StudentContent({ courseId }: { courseId: number }) {
  const [isEnrolled, setIsEnrolled] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

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
        <div className="flex justify-end">
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
      <CardContent>
        <p className="text-sm text-muted-foreground">
          {isEnrolled
            ? "You are enrolled in this course."
            : "Join this course to access materials and assessments."}
        </p>
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
    <CourseDetailProvider courseId={courseId}>
      <div className="space-y-6">
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
