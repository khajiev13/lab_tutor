import { useEffect, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { fetchOnetReleases, searchOnetOccupations } from "@/features/market-demand/api";
import type { OnetOccupation, OnetRelease } from "@/features/market-demand/types";

const schema = z.object({
  q: z.string().max(200),
  codes: z.array(z.string()).min(1).max(5),
});
type FormValues = z.infer<typeof schema>;

interface Props {
  courseId: number;
  release: string | null;
  selectedCodes: string[];
  disabled: boolean;
  onReleaseChange: (release: string) => void;
  onConfirm: (release: string, codes: string[]) => Promise<void> | void;
}

export function OnetOccupationPicker({
  courseId,
  release,
  selectedCodes,
  disabled,
  onReleaseChange,
  onConfirm,
}: Props) {
  const [releases, setReleases] = useState<OnetRelease[]>([]);
  const [occupations, setOccupations] = useState<OnetOccupation[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [confirming, setConfirming] = useState(false);
  const {
    register,
    control,
    setValue,
    getValues,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { q: "", codes: selectedCodes },
  });
  const codes = useWatch({ control, name: "codes" });
  const activeRelease = release ?? releases.find((item) => item.active)?.version ?? null;
  const attribution = releases.find((item) => item.version === activeRelease)?.attribution;

  useEffect(() => {
    setValue("codes", selectedCodes);
  }, [selectedCodes, setValue]);

  useEffect(() => {
    const abort = new AbortController();
    fetchOnetReleases(courseId, abort.signal)
      .then((data) => {
        if (abort.signal.aborted) return;
        setReleases(data.items);
        if (!data.items.length) {
          setError("O*NET catalog unavailable: no imported release is ready.");
          setLoading(false);
        }
      })
      .catch((cause) => {
        if (abort.signal.aborted) return;
        setError(cause instanceof Error ? cause.message : "O*NET catalog unavailable");
        setLoading(false);
      });
    return () => abort.abort();
  }, [courseId]);

  useEffect(() => {
    if (!activeRelease || releases.length === 0) return;
    const abort = new AbortController();
    setLoading(true);
    setError(null);
    searchOnetOccupations(courseId, activeRelease, query, 0, 20, abort.signal)
      .then((data) => {
        if (!abort.signal.aborted) setOccupations(data.items);
      })
      .catch((cause) => {
        if (!abort.signal.aborted) {
          setError(cause instanceof Error ? cause.message : "O*NET catalog unavailable");
        }
      })
      .finally(() => {
        if (!abort.signal.aborted) setLoading(false);
      });
    return () => abort.abort();
  }, [courseId, activeRelease, query, releases]);

  const hiddenCodes = codes.filter(
    (code) => !occupations.some((item) => item.soc_code === code)
  );

  return (
    <div className="space-y-2 text-sm">
      <label className="flex items-center gap-2">
        O*NET release
        <select
          aria-label="O*NET release"
          className="rounded-md border bg-background px-2 py-1"
          disabled={disabled || loading || confirming}
          value={activeRelease ?? ""}
          onChange={(event) => {
            setValue("codes", []);
            onReleaseChange(event.target.value);
          }}
        >
          {releases.map((item) => (
            <option key={item.version} value={item.version}>{item.version}</option>
          ))}
        </select>
      </label>
      {attribution && <p className="text-xs text-muted-foreground">{attribution}</p>}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          setQuery(getValues("q").trim());
        }}
        className="flex gap-2"
      >
        <Input
          aria-label="Search occupations"
          {...register("q")}
          disabled={disabled || confirming}
          placeholder="Search occupations"
        />
        <Button type="submit" variant="outline" disabled={disabled || loading || confirming}>Search</Button>
      </form>
      {error ? (
        <p role="alert" className="text-xs text-destructive">{error}</p>
      ) : loading ? (
        <p className="text-xs text-muted-foreground">Loading O*NET catalog…</p>
      ) : (
        <>
          <p className="text-xs text-muted-foreground">
            Choose 1–5 occupations · {codes.length} selected
          </p>
          <div className="max-h-40 space-y-2 overflow-y-auto">
            {occupations.map((item) => (
              <label key={item.soc_code} className="flex items-start gap-2">
                <Checkbox
                  aria-label={`${item.title} (${item.soc_code})`}
                  checked={codes.includes(item.soc_code)}
                  disabled={disabled || confirming || (!codes.includes(item.soc_code) && codes.length >= 5)}
                  onCheckedChange={(checked) =>
                    setValue(
                      "codes",
                      checked
                        ? [...codes, item.soc_code]
                        : codes.filter((value) => value !== item.soc_code)
                    )
                  }
                />
                <span>
                  {item.title} <span className="text-xs text-muted-foreground">{item.soc_code}</span>
                </span>
              </label>
            ))}
          </div>
          {occupations.length === 0 && (
            <p className="text-xs text-muted-foreground">No matching occupations.</p>
          )}
          {hiddenCodes.map((code) => (
            <label key={code} className="flex items-center gap-2">
              <Checkbox
                aria-label={`Selected occupation ${code}`}
                checked
                disabled={disabled || confirming}
                onCheckedChange={() => setValue("codes", codes.filter((value) => value !== code))}
              />
              {code} (selected)
            </label>
          ))}
        </>
      )}
      {errors.codes && (
        <p role="alert" className="text-xs text-destructive">Choose 1–5 occupations.</p>
      )}
      <Button
        type="button"
        size="sm"
        disabled={disabled || confirming || loading || !!error || !activeRelease || codes.length === 0}
        onClick={handleSubmit(async (values) => {
          if (!activeRelease) return;
          setConfirming(true);
          try {
            await onConfirm(activeRelease, values.codes);
          } catch (cause) {
            setError(cause instanceof Error ? cause.message : "Occupation confirmation failed");
          } finally {
            setConfirming(false);
          }
        })}
      >
        {confirming ? "Confirming…" : "Confirm occupations"}
      </Button>
    </div>
  );
}
