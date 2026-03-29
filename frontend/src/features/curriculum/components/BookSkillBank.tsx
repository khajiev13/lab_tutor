import { useState } from "react";
import {
  BookOpen,
  ChevronDown,
  Lightbulb,
  Library,
  Hash,
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
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import type { BookSkillBankBook } from "../types";

export function BookSkillBank({ books }: { books: BookSkillBankBook[] }) {
  if (books.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <Library className="size-10 text-muted-foreground/40 mb-3" />
        <p className="text-sm font-medium text-muted-foreground">
          No books analyzed yet
        </p>
        <p className="text-xs text-muted-foreground/60 mt-1">
          Use the Curricular Alignment Architect to select and analyze textbooks
        </p>
      </div>
    );
  }

  const totalSkills = books.reduce(
    (sum, b) =>
      sum + b.chapters.reduce((cSum, ch) => cSum + ch.skills.length, 0),
    0
  );
  const totalChapters = books.reduce(
    (sum, b) => sum + b.chapters.length,
    0
  );

  return (
    <div className="space-y-4">
      {/* Summary strip */}
      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        <Badge variant="outline" className="gap-1">
          <Library className="size-3" />
          {books.length} {books.length === 1 ? "book" : "books"}
        </Badge>
        <Badge variant="outline" className="gap-1">
          <Hash className="size-3" />
          {totalChapters} chapters
        </Badge>
        <Badge variant="outline" className="gap-1">
          <Lightbulb className="size-3" />
          {totalSkills} skills
        </Badge>
      </div>

      {/* Book cards */}
      {books.map((book) => (
        <BookCard key={book.book_id} book={book} />
      ))}
    </div>
  );
}

function BookCard({ book }: { book: BookSkillBankBook }) {
  const totalSkills = book.chapters.reduce(
    (sum, ch) => sum + ch.skills.length,
    0
  );

  return (
    <Card className="shadow-none">
      <CardHeader className="pb-2">
        <div className="flex items-start gap-3">
          <div className="rounded-md bg-violet-100 dark:bg-violet-950 p-2 shrink-0">
            <BookOpen className="size-4 text-violet-600 dark:text-violet-400" />
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="text-sm font-semibold leading-tight">
              {book.title}
            </h3>
            {book.authors && (
              <p className="text-xs text-muted-foreground mt-0.5">
                {book.authors}
              </p>
            )}
            <div className="flex items-center gap-2 mt-1.5">
              <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                {book.chapters.length} chapters
              </Badge>
              <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                {totalSkills} skills
              </Badge>
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <Accordion type="multiple" className="w-full">
          {book.chapters.map((ch) => (
            <AccordionItem
              key={ch.chapter_id}
              value={ch.chapter_id}
              className="border-b-0 last:border-b-0"
            >
              <AccordionTrigger className="hover:no-underline py-2 gap-2">
                <div className="flex flex-1 items-center gap-2 min-w-0">
                  <span className="flex items-center justify-center size-5 rounded bg-muted text-[10px] font-bold shrink-0">
                    {ch.chapter_index}
                  </span>
                  <span className="text-xs truncate">
                    Chapter {ch.chapter_index}
                  </span>
                </div>
                <Badge
                  variant="outline"
                  className="text-[10px] px-1.5 py-0 gap-0.5 shrink-0 mr-2"
                >
                  <Lightbulb className="size-2.5" />
                  {ch.skills.length}
                </Badge>
              </AccordionTrigger>
              <AccordionContent>
                {ch.skills.length === 0 ? (
                  <p className="text-xs text-muted-foreground pl-7">
                    No skills extracted
                  </p>
                ) : (
                  <div className="flex flex-wrap gap-1.5 pl-7">
                    {ch.skills.map((skill) => (
                      <SkillChip key={skill.name} skill={skill} />
                    ))}
                  </div>
                )}
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </CardContent>
    </Card>
  );
}

function SkillChip({
  skill,
}: {
  skill: { name: string; description: string | null };
}) {
  const [open, setOpen] = useState(false);

  if (!skill.description) {
    return (
      <Badge variant="secondary" className="text-[11px] px-2 py-0.5">
        {skill.name}
      </Badge>
    );
  }

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger asChild>
        <Badge
          variant="secondary"
          className="text-[11px] px-2 py-0.5 cursor-pointer hover:bg-secondary/80 transition-colors gap-1"
        >
          {skill.name}
          <ChevronDown
            className={cn(
              "size-2.5 transition-transform",
              open && "rotate-180"
            )}
          />
        </Badge>
      </CollapsibleTrigger>
      <CollapsibleContent className="w-full basis-full mt-1 mb-1">
        <p className="text-[10px] text-muted-foreground bg-muted/50 rounded px-2 py-1">
          {skill.description}
        </p>
      </CollapsibleContent>
    </Collapsible>
  );
}
