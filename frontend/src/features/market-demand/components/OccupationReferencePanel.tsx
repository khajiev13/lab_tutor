import {useEffect, useRef, useState} from "react";
import {useForm} from "react-hook-form";
import {zodResolver} from "@hookform/resolvers/zod";
import {z} from "zod";
import {Button} from "@/components/ui/button";
import {Input} from "@/components/ui/input";
import {cn} from "@/lib/utils";
import {fetchOnetReleases, getOccupationSkills, searchOnetOccupations} from "@/features/market-demand/api";
import {EvidenceLink} from "@/features/market-demand/components/SkillEvidencePanel";
import {buildOccupationReferenceContext} from "@/features/market-demand/workspace-context";
import type {OccupationReferenceContext, OnetEvidence, OnetMetric, OnetOccupation, OnetRelease} from "@/features/market-demand/types";

interface Props {
  courseId: number;
  compact?: boolean;
  onAsk: (context: OccupationReferenceContext, suggestedQuestion: string) => void;
}
const searchSchema = z.object({q: z.string().trim().min(2, "Search must contain 2–120 characters.").max(120, "Search must contain 2–120 characters.")});
type SearchValues = z.infer<typeof searchSchema>;
function message(cause: unknown, fallback: string) {return cause instanceof Error ? cause.message : fallback;}
function metricText(rating: OnetMetric | undefined, name: "IM" | "LV") {
  if (!rating) return `${name}: unavailable (missing)`;
  if (rating.status !== "reported") return `${name}: unavailable (${rating.status.replaceAll("_", " ")})`;
  const [minimum, maximum] = name === "IM" ? [1, 5] : [0, 7];
  if (rating.scale_id !== name || rating.minimum !== minimum || rating.maximum !== maximum ||
    typeof rating.value !== "number" || !Number.isFinite(rating.value) || rating.value < minimum || rating.value > maximum) {
    return `${name}: unavailable (invalid reported value or scale)`;
  }
  return `${name}: ${rating.value} (${minimum}–${maximum})`;
}

// A course boundary immediately discards all local reference selections and aborts its requests.
export function OccupationReferencePanel(props: Props) {
  return <ReferenceSession key={props.courseId} {...props}/>;
}
function ReferenceSession({courseId, onAsk, compact = false}: Props) {
  const [releases, setReleases] = useState<OnetRelease[]>([]);
  const [release, setRelease] = useState("");
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [catalogRetry, setCatalogRetry] = useState(0);
  const [occupations, setOccupations] = useState<OnetOccupation[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState("");
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [occupation, setOccupation] = useState<OnetOccupation | null>(null);
  const [items, setItems] = useState<OnetEvidence[]>([]);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);
  const [referencePage, setReferencePage] = useState(1);
  const [occupationPage, setOccupationPage] = useState(1);
  const [metric, setMetric] = useState<"IM" | "LV">("IM");
  const searchAbort = useRef<AbortController | null>(null);
  const evidenceAbort = useRef<AbortController | null>(null);
  const {register, handleSubmit, reset, formState: {errors}} = useForm<SearchValues>({resolver: zodResolver(searchSchema), defaultValues: {q: ""}});

  useEffect(() => {
    const abort = new AbortController();
    fetchOnetReleases(courseId, abort.signal).then(data => {
      if (abort.signal.aborted) return;
      setReleases(data.items);
      setRelease(data.items.find(item => item.active)?.version ?? "");
    }).catch(cause => {
      if (!abort.signal.aborted) setCatalogError(message(cause, "O*NET catalog unavailable"));
    }).finally(() => {if (!abort.signal.aborted) setCatalogLoading(false);});
    return () => abort.abort();
  }, [courseId, catalogRetry]);
  useEffect(() => () => {searchAbort.current?.abort(); evidenceAbort.current?.abort();}, []);

  function changeRelease(value: string) {
    searchAbort.current?.abort(); evidenceAbort.current?.abort();
    setReferencePage(1); setOccupationPage(1);
    setRelease(value); setQuery(""); reset({q: ""}); setOccupations([]); setTotal(0); setOccupation(null); setItems([]);
    setSearchLoading(false); setEvidenceLoading(false); setSearchError(null); setEvidenceError(null);
  }
  async function search(value: string) {
    if (!release) return;
    searchAbort.current?.abort();
    const abort = new AbortController(); searchAbort.current = abort;
    setOccupationPage(1); setQuery(value); setOccupations([]); setTotal(0); setSearchError(null); setSearchLoading(true);
    try {
      const data = await searchOnetOccupations(courseId, release, value, 0, 20, abort.signal);
      if (abort.signal.aborted) return;
      if (data.release !== release) throw new Error("Occupation results belong to another release. Retry search.");
      setOccupations(data.items);
      setTotal(data.total);
    } catch (cause) {if (!abort.signal.aborted) setSearchError(message(cause, "Occupation search unavailable"));}
    finally {if (!abort.signal.aborted) setSearchLoading(false);}
  }
  async function browse(choice: OnetOccupation) {
    evidenceAbort.current?.abort();
    const abort = new AbortController(); evidenceAbort.current = abort;
    setReferencePage(1); setOccupation(choice); setItems([]); setEvidenceError(null); setEvidenceLoading(true);
    try {
      const data = await getOccupationSkills(courseId, release, choice.soc_code, abort.signal);
      if (abort.signal.aborted) return;
      if (data.release !== release || data.soc_code !== choice.soc_code ||
        data.items.some(item => item.release !== release || item.soc_code !== choice.soc_code)) {
        throw new Error("Reference evidence belongs to another release or occupation. Retry evidence.");
      }
      setItems(data.items);
    } catch (cause) {if (!abort.signal.aborted) setEvidenceError(message(cause, "Occupation evidence unavailable"));}
    finally {if (!abort.signal.aborted) setEvidenceLoading(false);}
  }
  function context(elementIds: string[] = []) {
    return buildOccupationReferenceContext({release, occupationCodes: occupation ? [occupation.soc_code] : [], elementIds, metric});
  }
  function ask(elementIds: string[] = []) {
    const result = context(elementIds);
    if (result.ok && items.length && !evidenceLoading && !evidenceError) {
      onAsk(result.context, elementIds.length ? "Explain this O*NET descriptor and its reported evidence." : "Explain the O*NET reference evidence for this occupation.");
    }
  }
  if (compact) {
    const importance = (item: OnetEvidence) => {
      const value = item.ratings.IM;
      return value?.status === "reported" && value.scale_id === "IM" && value.minimum === 1 && value.maximum === 5 &&
        typeof value.value === "number" && Number.isFinite(value.value) && value.value >= 1 && value.value <= 5 ? value.value : null;
    };
    const references = items.filter(item => item.family !== "software").sort((a, b) =>
      (importance(b) ?? -1) - (importance(a) ?? -1) || a.label.localeCompare(b.label));
    const referencePages = Math.max(1, Math.ceil(references.length / 5));
    const currentReferencePage = Math.min(referencePage, referencePages);
    const occupationPages = Math.max(1, Math.ceil(occupations.length / 5));
    const currentOccupationPage = Math.min(occupationPage, occupationPages);
    return <section aria-label="O*NET occupation reference" className="space-y-3 text-sm">
      <p className="text-xs text-muted-foreground">Occupation reference importance; these ratings describe the occupation, not an individual job skill. Original 1–5 scale.</p>
      {catalogLoading ? <p role="status">Loading O*NET catalog…</p> : catalogError || !releases.length ? <div className="space-y-2">
        <p role={catalogError ? "alert" : "status"}>{catalogError ?? "No imported O*NET release is ready."}</p>
        <Button size="sm" variant="outline" onClick={() => {setCatalogError(null); setCatalogLoading(true); setCatalogRetry(value => value + 1);}}>Retry catalog</Button>
      </div> : <>
        {release && <p className="text-xs text-muted-foreground">O*NET release {release}</p>}
        {(!release || releases.length > 1) && <details open={!release}><summary className="cursor-pointer text-xs">Choose imported release</summary>
          <select aria-label="O*NET release" className="mt-2 rounded-md border bg-background p-2" value={release} onChange={event => changeRelease(event.target.value)}>
            {!release && <option value="">Choose an imported release</option>}{releases.map(item => <option key={item.version} value={item.version}>{item.version}</option>)}
          </select>
        </details>}
        <form onSubmit={handleSubmit(values => search(values.q))} className="flex flex-wrap gap-2">
          <Input aria-label="Search occupations" {...register("q")} placeholder="Search occupations" className="min-w-0 flex-1"/>
          <Button size="sm" type="submit" variant="outline" disabled={!release}>Search</Button>
        </form>
        {errors.q && <p role="alert" className="text-xs text-destructive">{errors.q.message}</p>}
        {searchLoading && <p role="status">Searching occupations…</p>}
        {searchError && <p role="alert">{searchError}</p>}
        {query && !searchLoading && !occupations.length && !searchError && <p>No matching imported occupations.</p>}
        {query && !searchLoading && (searchError || !occupations.length) && <Button size="sm" variant="outline" onClick={() => void search(query)}>Retry search</Button>}
        {occupations.length > 0 && <ul aria-label="Occupation search results" className="space-y-1">{occupations.slice((currentOccupationPage - 1) * 5, currentOccupationPage * 5).map(item => <li key={item.soc_code}>
          <Button size="sm" variant="outline" aria-pressed={occupation?.soc_code === item.soc_code} className="h-auto w-full justify-start whitespace-normal text-left" onClick={() => void browse(item)}>Browse {item.title}</Button>
        </li>)}</ul>}
        {occupationPages > 1 && <div className="flex items-center justify-between gap-2 text-xs">
          <Button size="sm" variant="outline" aria-label="Previous occupation page" disabled={currentOccupationPage === 1} onClick={() => setOccupationPage(currentOccupationPage - 1)}>Previous</Button>
          <span>Page {currentOccupationPage} of {occupationPages}</span>
          <Button size="sm" variant="outline" aria-label="Next occupation page" disabled={currentOccupationPage === occupationPages} onClick={() => setOccupationPage(currentOccupationPage + 1)}>Next</Button>
        </div>}
        {occupation && <div className="space-y-2">
          <h3 className="font-medium">{occupation.title}</h3>
          {evidenceLoading && <p role="status">Loading occupation evidence…</p>}
          {evidenceError && <p role="alert">{evidenceError}</p>}
          {!evidenceLoading && !references.length && !evidenceError && <p>No imported importance descriptors for this occupation.</p>}
          {!evidenceLoading && (evidenceError || !items.length) && <Button size="sm" variant="outline" onClick={() => void browse(occupation)}>Retry evidence</Button>}
          {references.slice((currentReferencePage - 1) * 5, currentReferencePage * 5).map(item => <article key={item.id} aria-label={item.label} className="space-y-1 rounded-md border p-2">
            <div className="flex items-start justify-between gap-2"><h4 className="min-w-0 break-words font-medium">{item.label}</h4><span className="shrink-0 text-xs">{importance(item) !== null ? `${importance(item)} / 5` : "Unavailable"}</span></div>
            <details className="text-xs text-muted-foreground"><summary className="cursor-pointer">Descriptor details</summary>
              <p>{item.definition}</p><p>{item.release} · {item.family} · {item.element_id} · {item.id}</p>
              <p>{metricText(item.ratings.IM, "IM")}</p>{item.ratings.IM && <p>Reported date: {item.ratings.IM.date ?? "unavailable"} · quality: {JSON.stringify(item.ratings.IM.quality)}</p>}
              {item.workplace_example && <p>{item.workplace_example}</p>}<p>{item.attribution}</p>
            </details>
            <div className="flex flex-wrap items-center gap-2 text-xs"><EvidenceLink url={item.source_url} label="O*NET source"/>
              <Button size="sm" variant="ghost" className="h-auto max-w-full justify-start whitespace-normal text-left" disabled={!context([item.element_id]).ok} onClick={() => ask([item.element_id])}>Ask about {item.label}</Button>
            </div>
          </article>)}
          {referencePages > 1 && <div className="flex items-center justify-between gap-2 text-xs">
            <Button size="sm" variant="outline" aria-label="Previous reference page" disabled={currentReferencePage === 1} onClick={() => setReferencePage(currentReferencePage - 1)}>Previous</Button>
            <span>Page {currentReferencePage} of {referencePages} · {references.length} occupation descriptors</span>
            <Button size="sm" variant="outline" aria-label="Next reference page" disabled={currentReferencePage === referencePages} onClick={() => setReferencePage(currentReferencePage + 1)}>Next</Button>
          </div>}
        </div>}
      </>}
    </section>;
  }
  return <section aria-label="O*NET occupation reference" className="space-y-4 rounded-lg border p-4 text-sm">
    <div><h2 className="font-semibold">Explore O*NET occupations</h2>
      <p className="text-muted-foreground">Reference browsing and questions do not change analysis settings or your shortlist. Publishing a skill still requires qualifying job evidence.</p></div>
    {catalogLoading ? <p role="status">Loading O*NET catalog…</p> : catalogError || !releases.length ? <div className="space-y-2">
      <p role={catalogError ? "alert" : "status"}>{catalogError ?? "O*NET catalog unavailable: no imported release is ready."}</p>
      <Button variant="outline" onClick={() => {setCatalogError(null); setCatalogLoading(true); setCatalogRetry(value => value + 1);}}>Retry catalog</Button>
    </div> : <>
      <label className="flex flex-wrap items-center gap-2">O*NET release
        <select aria-label="O*NET release" className="rounded-md border bg-background p-2" value={release} onChange={event => changeRelease(event.target.value)}>
          {!release && <option value="">Choose an imported release</option>}
          {releases.map(item => <option key={item.version} value={item.version}>{item.version}</option>)}
        </select>
      </label>
      {!release && <p>Choose an imported O*NET release; none is active.</p>}
      <p className="text-muted-foreground">{releases.find(item => item.version === release)?.attribution}</p>
      <form onSubmit={handleSubmit(values => search(values.q))} className="flex flex-wrap gap-2">
        <Input aria-label="Search occupations" {...register("q")} placeholder="Search occupations" className="min-w-40 flex-1"/>
        <Button type="submit" variant="outline" disabled={!release}>Search</Button>
      </form>
      {errors.q && <p role="alert" className="text-destructive">{errors.q.message}</p>}
      {!query && <p className="text-muted-foreground">Enter 2–120 characters to search occupations.</p>}
      {searchLoading && <p role="status">Searching occupations…</p>}
      {searchError && <p role="alert" className="text-destructive">{searchError}</p>}
      {query && !searchLoading && !occupations.length && !searchError && <p>No matching imported occupations.</p>}
      {!!occupations.length && <p className="text-muted-foreground">Showing {occupations.length} of {total} matching occupations.{total > occupations.length && " Refine your search to find other occupations."}</p>}
      {query && !searchLoading && (searchError || !occupations.length) && <Button variant="outline" onClick={() => void search(query)}>Retry search</Button>}
      <ul className="max-h-64 space-y-2 overflow-y-auto" aria-label="Occupation search results">
        {occupations.map(item => <li key={item.soc_code}>
          <Button variant="outline" aria-pressed={occupation?.soc_code === item.soc_code} className={cn("h-auto w-full justify-start whitespace-normal text-left", occupation?.soc_code === item.soc_code && "border-primary")}
            onClick={() => void browse(item)}>Browse {item.title} ({item.soc_code})</Button>
          <p className="mt-1 text-muted-foreground">{item.description}</p>
        </li>)}
      </ul>
      {occupation && <div className="space-y-3">
        <h3 className="font-semibold">{occupation.title} · {occupation.soc_code} · release {release}</h3>
        {evidenceLoading && <p role="status">Loading occupation evidence…</p>}
        {evidenceError && <p role="alert" className="text-destructive">{evidenceError}</p>}
        {!evidenceLoading && !items.length && !evidenceError && <p>No imported reference evidence for this occupation.</p>}
        {!evidenceLoading && (evidenceError || !items.length) && <Button variant="outline" onClick={() => void browse(occupation)}>Retry evidence</Button>}
        {!!items.length && <>
          <label className="flex flex-wrap items-center gap-2">Reference question metric
            <select aria-label="Reference question metric" className="rounded-md border bg-background p-2" value={metric} onChange={event => setMetric(event.target.value === "LV" ? "LV" : "IM")}>
              <option value="IM">Importance (1–5)</option><option value="LV">Level (0–7)</option>
            </select>
          </label>
          <Button variant="outline" disabled={!context().ok} onClick={() => ask()}>Ask about this occupation</Button>
          <p className="text-muted-foreground">Ask stages an explanation in the conversation. Review the question before sending.</p>
          {items.map(item => <article key={item.id} aria-label={item.label} className="space-y-2 rounded-md border p-3">
            <h4 className="font-medium">{item.label}</h4><p>{item.definition}</p>
            <p>{item.release} · {item.family} · {item.element_id} · {item.id}</p>
            {item.workplace_example && <p>Workplace example: {item.workplace_example}</p>}
            {item.family === "software" ? <p>Categorical software evidence — no importance or level rating.</p> : (["IM", "LV"] as const).map(name => <div key={name}>
              <p>{metricText(item.ratings[name], name)}</p>
              {item.ratings[name] && <p className="text-xs text-muted-foreground">{name} reported scale: {item.ratings[name].minimum}–{item.ratings[name].maximum} · date: {item.ratings[name].date ?? "unavailable"} · quality: {JSON.stringify(item.ratings[name].quality)}</p>}
            </div>)}
            {!!Object.keys(item.flags).length && <p>Flags: {JSON.stringify(item.flags)}</p>}
            <EvidenceLink url={item.source_url} label="O*NET source"/><p>{item.attribution}</p>
            <Button variant="outline" size="sm" disabled={!context([item.element_id]).ok} onClick={() => ask([item.element_id])}>Ask about {item.label}</Button>
          </article>)}
        </>}
      </div>}
    </>}
  </section>;
}
