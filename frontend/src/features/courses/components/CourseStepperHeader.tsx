import {
  FileUp,
  GitMerge,
  BookOpen,
  Cpu,
  BarChart3,
} from "lucide-react";

import { Stepper, type StepItem } from "@/components/ui/stepper";
import { Badge } from "@/components/ui/badge";
import { useCourseDetail } from "../context/CourseDetailContext";

const STEP_DEFS: { label: string; icon: React.ElementType; lockMsg: string }[] = [
  { label: "Upload Materials", icon: FileUp, lockMsg: "" },
  { label: "Normalize Concepts", icon: GitMerge, lockMsg: "Complete extraction first" },
  { label: "Select Books", icon: BookOpen, lockMsg: "Complete extraction first" },
  { label: "Analyze Books", icon: Cpu, lockMsg: "Complete extraction first" },
  { label: "Visualize Results", icon: BarChart3, lockMsg: "Complete extraction first" },
];

export function CourseStepperHeader() {
  const { activeStep, setActiveStep, getStepStatus } = useCourseDetail();

  const steps: StepItem[] = STEP_DEFS.map((def, i) => {
    const status = getStepStatus(i);
    return {
      label: def.label,
      icon: def.icon,
      status,
      lockedReason: status === "locked" ? def.lockMsg : undefined,
      description:
        i === 1 && status !== "locked"
          ? "Optional"
          : undefined,
    };
  });

  return (
    <div className="space-y-1">
      <Stepper
        steps={steps}
        activeIndex={activeStep}
        onStepClick={(i) => {
          const s = getStepStatus(i);
          if (s !== "locked") setActiveStep(i);
        }}
      />
      {/* Optional badge for normalization when active */}
      {activeStep === 1 && (
        <div className="flex items-center gap-2 pl-2 pt-1">
          <Badge variant="outline" className="text-amber-600 border-amber-300 bg-amber-50 dark:bg-amber-950/20 dark:border-amber-800 dark:text-amber-400">
            Optional step
          </Badge>
          <span className="text-xs text-muted-foreground">
            You can skip this and proceed to book selection
          </span>
        </div>
      )}
    </div>
  );
}
