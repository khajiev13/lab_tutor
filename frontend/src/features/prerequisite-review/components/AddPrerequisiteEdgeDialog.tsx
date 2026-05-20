import { useMemo, useState } from "react";
import type { FormEvent } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { PrerequisiteDraftEdge, PrerequisiteSkill } from "@/features/courses/types";

interface AddPrerequisiteEdgeDialogProps {
  open: boolean;
  skills: PrerequisiteSkill[];
  onOpenChange: (open: boolean) => void;
  onAdd: (edge: PrerequisiteDraftEdge) => void;
  isSaving?: boolean;
}

export function AddPrerequisiteEdgeDialog({
  open,
  skills,
  onOpenChange,
  onAdd,
  isSaving = false,
}: AddPrerequisiteEdgeDialogProps) {
  const [prerequisiteName, setPrerequisiteName] = useState("");
  const [dependentName, setDependentName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const skillNames = useMemo(() => skills.map((skill) => skill.name).sort(), [skills]);
  const skillNameSet = useMemo(() => new Set(skillNames), [skillNames]);

  function reset() {
    setPrerequisiteName("");
    setDependentName("");
    setError(null);
  }

  function handleOpenChange(nextOpen: boolean) {
    onOpenChange(nextOpen);
    if (!nextOpen) reset();
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const prerequisite = prerequisiteName.trim();
    const dependent = dependentName.trim();

    if (!skillNameSet.has(prerequisite) || !skillNameSet.has(dependent)) {
      setError("Choose skills from the course skill bank.");
      return;
    }

    if (prerequisite === dependent) {
      setError("A skill cannot depend on itself.");
      return;
    }

    onAdd({
      prerequisite_name: prerequisite,
      dependent_name: dependent,
      confidence: "medium",
      reasoning: "Teacher added prerequisite relationship.",
      source: "teacher",
    });
    reset();
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add prerequisite edge</DialogTitle>
        </DialogHeader>
        <form className="space-y-4" onSubmit={handleSubmit}>
          <div className="space-y-2">
            <Label htmlFor="prerequisite-skill">Prerequisite</Label>
            <Input
              id="prerequisite-skill"
              list="prerequisite-review-skill-names"
              value={prerequisiteName}
              onChange={(event) => setPrerequisiteName(event.target.value)}
              disabled={isSaving}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="dependent-skill">Dependent skill</Label>
            <Input
              id="dependent-skill"
              list="prerequisite-review-skill-names"
              value={dependentName}
              onChange={(event) => setDependentName(event.target.value)}
              disabled={isSaving}
            />
          </div>
          <datalist id="prerequisite-review-skill-names">
            {skillNames.map((skillName) => (
              <option key={skillName} value={skillName} />
            ))}
          </datalist>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={isSaving}
              onClick={() => handleOpenChange(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isSaving}>
              Save edge
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
