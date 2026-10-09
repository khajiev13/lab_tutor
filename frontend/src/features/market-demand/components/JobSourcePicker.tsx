import { Checkbox } from "@/components/ui/checkbox";
import type {
  EvidenceSource,
  JobSource,
  JobSourceAvailability,
} from "@/features/market-demand/types";

interface Props {
  sources: JobSource[];
  evidenceSources: EvidenceSource[];
  catalog: JobSourceAvailability[];
  onSourcesChange: (sources: JobSource[]) => void;
  onEvidenceChange: (sources: EvidenceSource[]) => void;
  disabled: boolean;
}

export function JobSourcePicker({
  sources,
  evidenceSources,
  catalog,
  onSourcesChange,
  onEvidenceChange,
  disabled,
}: Props) {
  return (
    <fieldset disabled={disabled} className="space-y-3 text-sm">
      <legend className="font-medium">Evidence sources</legend>
      <div className="flex flex-wrap gap-4">
        {(["jobs", "onet"] as const).map((source) => (
          <label key={source} className="flex items-center gap-2">
            <Checkbox
              aria-label={source === "jobs" ? "Job postings" : "O*NET references"}
              checked={evidenceSources.includes(source)}
              disabled={disabled}
              onCheckedChange={(checked) =>
                onEvidenceChange(
                  checked
                    ? [...evidenceSources, source]
                    : evidenceSources.filter((value) => value !== source)
                )
              }
            />
            {source === "jobs" ? "Job postings" : "O*NET references"}
          </label>
        ))}
      </div>
      {evidenceSources.includes("jobs") && (
        <div className="flex flex-wrap gap-4">
          {catalog.map((item) => (
            <div key={item.id}>
              <label className="flex items-center gap-2">
                <Checkbox
                  aria-label={item.label}
                  checked={sources.includes(item.id)}
                  disabled={disabled || (item.availability !== "available" && !sources.includes(item.id))}
                  onCheckedChange={(checked) =>
                    onSourcesChange(
                      checked
                        ? [...sources, item.id]
                        : sources.filter((value) => value !== item.id)
                    )
                  }
                />
                {item.label}
              </label>
              {item.reason && <p className="text-xs text-muted-foreground">{item.reason}</p>}
            </div>
          ))}
        </div>
      )}
      {evidenceSources.includes("onet") && !evidenceSources.includes("jobs") && (
        <p className="text-xs text-muted-foreground">
          O*NET supports discovery and draft shortlisting. Approval requires supporting job postings
          collected in a new analysis with explicitly selected job providers.
        </p>
      )}
    </fieldset>
  );
}
