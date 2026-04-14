import * as React from "react"
import { Check, Loader2 } from "lucide-react"

import { cn } from "@/lib/utils"
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
  TooltipProvider,
} from "@/components/ui/tooltip"

/* ── Types ──────────────────────────────────────────────────── */

export type StepStatus = "completed" | "active" | "pending" | "locked"

export interface StepItem {
  label: string
  icon: React.ElementType
  status: StepStatus
  description?: string
  /** Tooltip shown when the step is locked */
  lockedReason?: string
}

/* ── Stepper ────────────────────────────────────────────────── */

interface StepperProps {
  steps: StepItem[]
  activeIndex: number
  onStepClick?: (index: number) => void
  className?: string
}

function Stepper({ steps, activeIndex, onStepClick, className }: StepperProps) {
  return (
    <nav
      aria-label="Progress"
      className={cn("w-full", className)}
    >
      {/* Desktop */}
      <ol className="hidden sm:flex items-center w-full">
        {steps.map((step, i) => (
          <li
            key={i}
            className={cn(
              "flex items-center",
              i < steps.length - 1 ? "flex-1" : "",
            )}
          >
            <StepCircle
              step={step}
              isActive={i === activeIndex}
              onClick={() => onStepClick?.(i)}
            />
            {i < steps.length - 1 && <StepConnector status={step.status} />}
          </li>
        ))}
      </ol>

      {/* Mobile */}
      <div className="flex sm:hidden items-center justify-between gap-3 rounded-lg border bg-card p-3">
        <div className="flex items-center gap-3 min-w-0">
          <StepCircle
            step={steps[activeIndex]}
            isActive
            compact
          />
          <div className="min-w-0">
            <p className="text-sm font-medium truncate">
              {steps[activeIndex].label}
            </p>
            <p className="text-xs text-muted-foreground">
              Step {activeIndex + 1} of {steps.length}
            </p>
          </div>
        </div>
        <div className="flex gap-1">
          {steps.map((s, i) => (
            <button
              key={i}
              type="button"
              disabled={s.status === "locked"}
              onClick={() => onStepClick?.(i)}
              className={cn(
                "h-1.5 rounded-full transition-all",
                i === activeIndex
                  ? "w-6 bg-primary"
                  : s.status === "completed"
                    ? "w-3 bg-primary/50"
                    : "w-3 bg-muted-foreground/20",
              )}
              aria-label={`Go to step ${i + 1}: ${s.label}`}
            />
          ))}
        </div>
      </div>
    </nav>
  )
}

/* ── StepCircle ─────────────────────────────────────────────── */

interface StepCircleProps {
  step: StepItem
  isActive: boolean
  compact?: boolean
  onClick?: () => void
}

function StepCircle({
  step,
  isActive,
  compact,
  onClick,
}: StepCircleProps) {
  const Icon = step.icon

  const circle = (
    <button
      type="button"
      disabled={step.status === "locked"}
      onClick={onClick}
      aria-current={isActive ? "step" : undefined}
      className={cn(
        "group relative flex items-center gap-3 outline-none transition-all",
        step.status === "locked"
          ? "cursor-not-allowed"
          : "cursor-pointer",
        !compact && "pr-2",
      )}
    >
      {/* Circle — always shows the step icon */}
      <span
        className={cn(
          "relative flex h-10 w-10 shrink-0 items-center justify-center rounded-full border-2 transition-all duration-200",
          step.status === "completed" &&
            "border-primary bg-primary/10 text-primary",
          step.status === "active" &&
            "border-primary bg-primary/10 text-primary ring-4 ring-primary/10",
          step.status === "pending" &&
            "border-muted-foreground/30 bg-background text-muted-foreground",
          step.status === "locked" &&
            "border-muted-foreground/15 bg-muted/50 text-muted-foreground/40",
          step.status !== "locked" && "group-hover:shadow-md",
        )}
      >
        <Icon className={cn(
          "h-4.5 w-4.5",
          step.status === "locked" && "opacity-40",
        )} />

        {/* Completed badge — small green check in top-right corner */}
        {step.status === "completed" && (
          <span className="absolute -top-1 -right-1 flex h-4.5 w-4.5 items-center justify-center rounded-full bg-primary text-primary-foreground ring-2 ring-background">
            <Check className="h-3 w-3" strokeWidth={3} />
          </span>
        )}

        {/* Pulse ring for active step */}
        {step.status === "active" && (
          <span className="absolute inset-0 rounded-full animate-ping bg-primary/20 [animation-duration:2s]" />
        )}
      </span>

      {/* Label — desktop only */}
      {!compact && (
        <div className="hidden lg:block text-left min-w-0">
          <p
            className={cn(
              "text-sm font-medium leading-tight truncate max-w-28",
              step.status === "completed" && "text-primary",
              step.status === "active" && "text-foreground",
              step.status === "pending" && "text-muted-foreground",
              step.status === "locked" && "text-muted-foreground/50",
            )}
          >
            {step.label}
          </p>
          {step.description && (
            <p
              className={cn(
                "text-xs leading-tight truncate max-w-28",
                step.status === "locked"
                  ? "text-muted-foreground/30"
                  : "text-muted-foreground",
              )}
            >
              {step.description}
            </p>
          )}
        </div>
      )}
    </button>
  )

  if (step.status === "locked" && step.lockedReason) {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>{circle}</TooltipTrigger>
          <TooltipContent side="bottom">
            <p>{step.lockedReason}</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    )
  }

  return circle
}

/* ── StepConnector ──────────────────────────────────────────── */

function StepConnector({ status }: { status: StepStatus }) {
  return (
    <div
      className={cn(
        "h-0.5 flex-1 mx-1 rounded-full transition-colors duration-300",
        status === "completed" ? "bg-primary" : "bg-muted-foreground/15",
      )}
    />
  )
}

/* ── StepContent ────────────────────────────────────────────── */

interface StepContentProps {
  activeIndex: number
  index: number
  children: React.ReactNode
  className?: string
}

function StepContent({
  activeIndex,
  index,
  children,
  className,
}: StepContentProps) {
  if (activeIndex !== index) return null
  return (
    <div
      data-slot="step-content"
      className={cn("animate-in fade-in-0 slide-in-from-bottom-2 duration-300", className)}
    >
      {children}
    </div>
  )
}

/* ── StepLoadingIndicator (optional) ────────────────────────── */

function StepLoadingIndicator({ label }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16">
      <Loader2 className="h-8 w-8 animate-spin text-primary" />
      {label && <p className="text-sm text-muted-foreground">{label}</p>}
    </div>
  )
}

export { Stepper, StepContent, StepLoadingIndicator }
