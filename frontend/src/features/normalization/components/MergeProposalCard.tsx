import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import type { MergeProposal } from '@/features/normalization/api';

type Props = {
  proposal: MergeProposal;
  isSelected: boolean;
  onSelect: () => void;
};

function decisionBadgeVariant(decision: MergeProposal['decision']): 'default' | 'secondary' | 'destructive' {
  switch (decision) {
    case 'approved':
      return 'default';
    case 'rejected':
      return 'destructive';
    default:
      return 'secondary';
  }
}

export function MergeProposalCard({ proposal, isSelected, onSelect }: Props) {
  const variantsCount = proposal.variants?.length ?? 0;
  const preview =
    variantsCount <= 1
      ? proposal.canonical
      : proposal.variants.slice(0, 4).join(', ') + (variantsCount > 4 ? '…' : '');

  return (
    <Card
      className={[
        'cursor-pointer transition-colors',
        isSelected ? 'border-primary' : 'hover:bg-muted/40',
      ].join(' ')}
      onClick={onSelect}
    >
      <CardContent className="py-3 space-y-1">
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0 truncate text-sm">
            <span className="font-medium">{proposal.canonical}</span>
            <span className="ml-2 text-xs text-muted-foreground">
              ({variantsCount} variants)
            </span>
          </div>
          <Badge variant={decisionBadgeVariant(proposal.decision)}>{proposal.decision}</Badge>
        </div>
        <div className="text-xs text-muted-foreground line-clamp-2">{preview}</div>
        {proposal.r ? (
          <div className="text-xs text-muted-foreground/80 line-clamp-2">{proposal.r}</div>
        ) : null}
        {proposal.applied && (
          <div className="text-xs text-green-700 dark:text-green-400">Applied</div>
        )}
      </CardContent>
    </Card>
  );
}


