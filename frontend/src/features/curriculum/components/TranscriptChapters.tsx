import {
  FileText,
  GraduationCap,
  Target,
} from "lucide-react";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import type { CourseChapter } from "../types";

export function TranscriptChapters({
  chapters,
}: {
  chapters: CourseChapter[];
}) {
  if (chapters.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <FileText className="size-10 text-muted-foreground/40 mb-3" />
        <p className="text-sm font-medium text-muted-foreground">
          No course chapters found
        </p>
        <p className="text-xs text-muted-foreground/60 mt-1">
          Build your course chapters using the Curricular Alignment Architect
        </p>
      </div>
    );
  }

  return (
    <Accordion type="multiple" className="w-full">
      {chapters.map((ch) => (
        <AccordionItem
          key={ch.chapter_index}
          value={`transcript-${ch.chapter_index}`}
        >
          <AccordionTrigger className="hover:no-underline gap-3">
            <div className="flex flex-1 items-center gap-3 min-w-0">
              <span className="flex items-center justify-center size-7 rounded-md bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-400 text-xs font-bold shrink-0">
                {ch.chapter_index}
              </span>
              <span className="font-medium text-sm truncate">{ch.title}</span>
            </div>
            <div className="flex items-center gap-1.5 shrink-0 mr-2">
              {ch.documents.length > 0 && (
                <Badge
                  variant="secondary"
                  className="text-[10px] px-1.5 py-0 gap-0.5"
                >
                  <FileText className="size-2.5" />
                  {ch.documents.length}
                </Badge>
              )}
              {ch.learning_objectives.length > 0 && (
                <Badge
                  variant="outline"
                  className="text-[10px] px-1.5 py-0 gap-0.5"
                >
                  <Target className="size-2.5" />
                  {ch.learning_objectives.length}
                </Badge>
              )}
            </div>
          </AccordionTrigger>
          <AccordionContent>
            <div className="space-y-4 pl-10">
              {/* Description */}
              {ch.description && (
                <p className="text-xs text-muted-foreground leading-relaxed">
                  {ch.description}
                </p>
              )}

              {/* Learning Objectives */}
              {ch.learning_objectives.length > 0 && (
                <div className="space-y-2">
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                    <GraduationCap className="size-3" />
                    Learning Objectives
                  </h4>
                  <ul className="space-y-1">
                    {ch.learning_objectives.map((obj, i) => (
                      <li
                        key={i}
                        className="text-xs text-muted-foreground pl-4 relative before:absolute before:left-0 before:top-[7px] before:size-1.5 before:rounded-full before:bg-blue-400/50"
                      >
                        {obj}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Teacher Documents */}
              {ch.documents.length > 0 && (
                <div className="space-y-2">
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                    <FileText className="size-3" />
                    Teacher Transcripts
                  </h4>
                  <div className="grid gap-1.5">
                    {ch.documents.map((doc) => (
                      <div
                        key={doc.topic}
                        className="flex items-start gap-2 rounded-md border px-3 py-2"
                      >
                        <FileText className="size-3.5 text-blue-500 mt-0.5 shrink-0" />
                        <div className="min-w-0">
                          <p className="text-xs font-medium truncate">
                            {doc.topic}
                          </p>
                          {doc.source_filename && (
                            <p className="text-[10px] text-muted-foreground truncate">
                              {doc.source_filename}
                            </p>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </AccordionContent>
        </AccordionItem>
      ))}
    </Accordion>
  );
}
