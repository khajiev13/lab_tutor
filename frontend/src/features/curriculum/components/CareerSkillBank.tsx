import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { SkillAvailability, SkillEvidence } from '@/features/curriculum/components/SkillEvidence';
import type { CareerSkillBankSkill } from '@/features/curriculum/types';

export function CareerSkillBank({ skills, selectedStudentName, selectedKeys, onToggle }: {
  skills: CareerSkillBankSkill[];
  selectedStudentName?: string | null;
  selectedKeys?: Set<string>;
  onToggle?: (skill: CareerSkillBankSkill) => void;
}) {
  const uniqueSkills = [...new Map(skills.map((skill) => [skill.skill_reference_id, skill])).values()];
  if (!uniqueSkills.length) return <p className="py-8 text-center text-sm text-muted-foreground">No approved career skills yet.</p>;
  return <div className="space-y-3">
    {uniqueSkills.map((skill) => {
      const context = `${skill.label} · ${skill.chapters.map((chapter) => chapter.title).join(', ') || skill.category || skill.source}`;
      const selected = selectedKeys?.has(`reference:${skill.skill_reference_id}`) ?? skill.overlay?.isSelected ?? skill.is_selected;
      const available = skill.available_for_new_selection && skill.projection_status === 'projected';
      return <Card key={skill.skill_reference_id} role="article" aria-label={context} className="shadow-none">
        <CardHeader className="space-y-2">
          <div className="flex items-center gap-3">
            {onToggle && <Checkbox aria-label={`Select ${context}`} checked={selected} disabled={!selected && !available} onCheckedChange={() => onToggle(skill)} />}
            <CardTitle className="text-base">{skill.label}</CardTitle>
            <Badge variant="outline">{skill.source}</Badge>
            <Badge variant="outline">Origin: {skill.origin}</Badge>
          </div>
          <div className="flex flex-wrap gap-2">
            {skill.chapters.map((chapter) => <Badge key={chapter.chapter_id} variant="secondary">{chapter.title}</Badge>)}
            {skill.category && <Badge variant="outline">{skill.category}</Badge>}
            {selectedStudentName && selected && <Badge variant="outline">Selected by {selectedStudentName}</Badge>}
            {(skill.overlay?.peerCount ?? skill.peer_count) > 0 && <Badge variant="outline">{skill.overlay?.peerCount ?? skill.peer_count} peers</Badge>}
          </div>
          <SkillAvailability skill={skill} />
        </CardHeader>
        <CardContent className="space-y-3">
          {skill.description && <p className="text-sm text-muted-foreground">{skill.description}</p>}
          <SkillEvidence skill={skill} />
        </CardContent>
      </Card>;
    })}
  </div>;
}
