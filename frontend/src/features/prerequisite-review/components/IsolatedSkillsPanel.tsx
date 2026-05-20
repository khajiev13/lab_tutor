import { Button } from "@/components/ui/button";

interface IsolatedSkillsPanelProps {
  isolatedSkills: string[];
  reviewed: boolean;
  onMarkReviewed: () => void;
  isSaving?: boolean;
}

export function IsolatedSkillsPanel({
  isolatedSkills,
  reviewed,
  onMarkReviewed,
  isSaving = false,
}: IsolatedSkillsPanelProps) {
  return (
    <div className="rounded-lg border bg-background p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-base font-semibold">Isolated skills</h2>
          <p className="mt-1 text-sm text-muted-foreground">{isolatedSkills.length} unlinked</p>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={reviewed || isSaving || isolatedSkills.length === 0}
          onClick={onMarkReviewed}
        >
          {reviewed ? "Reviewed" : "Mark reviewed"}
        </Button>
      </div>
      {isolatedSkills.length > 0 ? (
        <ul className="mt-4 space-y-2 text-sm">
          {isolatedSkills.map((skill) => (
            <li key={skill} className="rounded-md border px-3 py-2">
              {skill}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-4 text-sm text-muted-foreground">No isolated skills.</p>
      )}
    </div>
  );
}
