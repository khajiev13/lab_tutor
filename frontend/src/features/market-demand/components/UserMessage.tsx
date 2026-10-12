import {
  Message,
  MessageAvatar,
  MessageContent,
} from "@/components/ui/message";

import type { ResolvedContextMetadata } from "@/features/market-demand/types";

interface UserMessageProps {
  content: string;
  context?: ResolvedContextMetadata;
  evidenceUnavailable?: boolean;
}

export function UserMessage({ content, context, evidenceUnavailable }: UserMessageProps) {
  return (
    <Message className="flex-row-reverse">
      <MessageAvatar src="" alt="User" fallback="U" className="bg-muted" />
      <div className="max-w-[80%]">
        <MessageContent className="bg-accent text-accent-foreground rounded-2xl">{content}</MessageContent>
        {context && <details className="mt-2 rounded-md border p-2 text-xs">
          <summary className="cursor-pointer">Historical attachment · {context.kind === "run_review" ? "Saved review" : "Occupation reference"}</summary>
          <p>This describes what the assistant received for this turn.</p>
          <p>{context.candidate_ids.map(id => context.candidate_labels[id] ?? id).join(", ") || "No focused skills"}</p>
          {context.kind === "run_review" && <p>Candidate revision {context.candidate_revision} · Selection revision {context.selection_revision}</p>}
          {context.release && <p>O*NET release {context.release}</p>}
          <p>{context.occupation_codes.join(", ")} · {context.metric}</p>
          <p>{context.included_count} included · {context.omitted_count} omitted · {context.evidence_omitted_count} evidence items omitted</p>
          {context.notices.map((notice, index) => <p key={index}>{notice}</p>)}
          <p>{evidenceUnavailable ? "Evidence unavailable in the current review; sources may have been removed or purged." : "Historical source evidence may have changed. Inspect the current evidence before using it."}</p>
        </details>}
      </div>
    </Message>
  );
}
