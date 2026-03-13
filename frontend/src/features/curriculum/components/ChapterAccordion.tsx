import { useState } from "react";
import {
  BookOpen,
  ChevronDown,
  Layers,
  TrendingUp,
  Lightbulb,
} from "lucide-react";

import { cn } from "@/lib/utils";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import type { ChapterRead } from "../types";
import { SkillCard } from "./SkillCard";

function SectionsList({ sections }: { sections: ChapterRead["sections"] }) {
  const [open, setOpen] = useState(false);
  const totalConcepts = sections.reduce(
    (sum, s) => sum + s.concepts.length,
    0
  );

  if (sections.length === 0) return null;

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors w-full py-2">
        <Layers className="size-3.5" />
        <span>
          {sections.length} sections &middot; {totalConcepts} concepts
        </span>
        <ChevronDown
          className={cn(
            "size-3.5 ml-auto transition-transform",
            open && "rotate-180"
          )}
        />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="space-y-3 pt-1 pl-1">
          {sections.map((section) => (
            <div key={section.section_index}>
              <p className="text-xs font-medium text-foreground mb-1">
                {section.title}
              </p>
              {section.concepts.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {section.concepts.map((c) => (
                    <Badge
                      key={c.name}
                      variant="secondary"
                      className="text-[10px] px-1.5 py-0"
                    >
                      <Lightbulb className="size-2.5 mr-0.5" />
                      {c.name}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

export function ChapterAccordion({
  chapters,
}: {
  chapters: ChapterRead[];
}) {
  const bookSkillCount = (ch: ChapterRead) =>
    ch.skills.filter((s) => s.source === "book").length;
  const marketSkillCount = (ch: ChapterRead) =>
    ch.skills.filter((s) => s.source === "market_demand").length;

  return (
    <Accordion type="multiple" className="w-full">
      {chapters.map((ch) => (
        <AccordionItem
          key={ch.chapter_index}
          value={`chapter-${ch.chapter_index}`}
        >
          <AccordionTrigger className="hover:no-underline gap-3">
            <div className="flex flex-1 items-center gap-3 min-w-0">
              <span className="flex items-center justify-center size-7 rounded-md bg-muted text-xs font-bold shrink-0">
                {ch.chapter_index}
              </span>
              <span className="font-medium text-sm truncate">{ch.title}</span>
            </div>
            <div className="flex items-center gap-1.5 shrink-0 mr-2">
              {bookSkillCount(ch) > 0 && (
                <Badge variant="outline" className="text-[10px] px-1.5 py-0 gap-0.5">
                  <BookOpen className="size-2.5" />
                  {bookSkillCount(ch)}
                </Badge>
              )}
              {marketSkillCount(ch) > 0 && (
                <Badge
                  className="border-transparent bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400 text-[10px] px-1.5 py-0 gap-0.5"
                >
                  <TrendingUp className="size-2.5" />
                  {marketSkillCount(ch)}
                </Badge>
              )}
              {ch.sections.length > 0 && (
                <Badge variant="secondary" className="text-[10px] px-1.5 py-0 gap-0.5">
                  <Layers className="size-2.5" />
                  {ch.sections.length}
                </Badge>
              )}
            </div>
          </AccordionTrigger>
          <AccordionContent>
            <div className="space-y-4 pl-10">
              {/* Summary */}
              {ch.summary && (
                <p className="text-xs text-muted-foreground leading-relaxed">
                  {ch.summary}
                </p>
              )}

              {/* Skills */}
              {ch.skills.length > 0 && (
                <div className="space-y-2">
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Skills
                  </h4>
                  <div className="grid gap-2">
                    {ch.skills.map((skill) => (
                      <SkillCard key={`${skill.source}-${skill.name}`} skill={skill} />
                    ))}
                  </div>
                </div>
              )}

              {/* Sections */}
              <SectionsList sections={ch.sections} />
            </div>
          </AccordionContent>
        </AccordionItem>
      ))}
    </Accordion>
  );
}
