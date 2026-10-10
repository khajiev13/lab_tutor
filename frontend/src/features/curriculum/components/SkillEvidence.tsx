import type { SkillEvidenceFields } from '@/features/curriculum/types';

export function SkillEvidence({ skill }: { skill: SkillEvidenceFields }) {
  const links = [...new Set(skill.qualifying_posting_links ?? [])];
  const associations = skill.onet_associations ?? [];
  if (!skill.skill_reference_id && !links.length && !associations.length) return null;

  const metrics = skill.job_metrics;
  return (
    <div className="space-y-2 text-xs text-muted-foreground">
      {links.map((url, index) => (
        <a key={url} href={url} target="_blank" rel="noopener noreferrer" className="block text-primary underline">
          Supporting job posting{links.length > 1 ? ` ${index + 1}` : ''}
        </a>
      ))}
      {metrics?.percentage != null
        ? <p>Job demand: {metrics.percentage}%</p>
        : <p>Job demand unavailable</p>}
      {metrics && (
        <p>
          {metrics.supporting_posting_count ?? 'Unavailable'} supporting / {metrics.assessed_posting_count ?? 'unavailable'} assessed / {metrics.selected_posting_count ?? 'unavailable'} selected postings
          {' · '}Coverage: {metrics.coverage_status ?? 'unavailable'}
        </p>
      )}
      {skill.evidence_references?.map((evidence) => (
        <p key={`${evidence.snapshot_id}:${evidence.original_phrase}`}>
          {evidence.provider} · {evidence.evidence_kind === 'provider_tag' ? 'Provider tag' : 'Extracted passage'}: {evidence.original_phrase}
          {evidence.excerpt && ` — ${evidence.excerpt}`}
          {' · '}{evidence.status} · Retrieved {evidence.retrieved_at}
        </p>
      ))}
      {associations.map(({ evidence, relation, rationale }, index) => (
        <div key={`${evidence.id}:${relation}:${index}`} className="space-y-1 border-t pt-2">
          <p>O*NET context · {relation} · {evidence.occupation_title} ({evidence.soc_code}) · Release {evidence.release}</p>
          <p>{evidence.label}: {evidence.definition}</p>
          {rationale && <p>{rationale}</p>}
          {Object.entries(evidence.ratings).map(([scale, metric]) => metric && (
            <p key={scale}>
              {scale === 'IM' ? 'Importance (IM)' : scale === 'LV' ? 'Occupational level (LV)' : scale}
              {': '}{metric.status === 'reported' && metric.value != null
                ? `${metric.value} (${metric.minimum}–${metric.maximum})`
                : `Unavailable (${metric.status})`}
            </p>
          ))}
          {Object.entries(evidence.flags).map(([flag, value]) => value != null && <p key={flag}>{flag}: {value ? 'Yes' : 'No'}</p>)}
          <a href={evidence.source_url} target="_blank" rel="noopener noreferrer" className="text-primary underline">O*NET reference</a>
          <p>{evidence.attribution}</p>
        </div>
      ))}
    </div>
  );
}

export function SkillAvailability({ skill }: { skill: SkillEvidenceFields }) {
  if (!skill.skill_reference_id || (skill.available_for_new_selection && skill.projection_status === 'projected')) return null;
  return <p className="text-xs text-amber-700 dark:text-amber-300">
    {skill.availability_reason ?? (skill.projection_status === 'pending' ? 'Awaiting projection' : skill.projection_status === 'error' ? 'Projection failed' : 'Unavailable for new selection')}
  </p>;
}
