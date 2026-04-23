import { useState } from 'react';
import { BookOpen, ChevronDown, Library, Lightbulb, Users } from 'lucide-react';

import { cn } from '@/lib/utils';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { Badge } from '@/components/ui/badge';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import type { SkillBankDisplayBook } from '@/features/curriculum/types';

export function BookSkillBank({
  books,
  selectedStudentName,
}: {
  books: SkillBankDisplayBook[];
  selectedStudentName?: string | null;
}) {
  if (books.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <Library className="mb-3 size-10 text-muted-foreground/40" />
        <p className="text-sm font-medium text-muted-foreground">No books analyzed yet</p>
        <p className="mt-1 text-xs text-muted-foreground/60">
          Use the Curricular Alignment Architect to select and analyze textbooks
        </p>
      </div>
    );
  }

  const totalSkills = books.reduce(
    (sum, book) => sum + book.chapters.reduce((chapterTotal, chapter) => chapterTotal + chapter.skills.length, 0),
    0,
  );
  const totalChapters = books.reduce((sum, book) => sum + book.chapters.length, 0);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
        <Badge variant="outline" className="gap-1">
          <Library className="size-3" />
          {books.length} {books.length === 1 ? 'book' : 'books'}
        </Badge>
        <Badge variant="outline" className="gap-1">
          <BookOpen className="size-3" />
          {totalChapters} chapters
        </Badge>
        <Badge variant="outline" className="gap-1">
          <Lightbulb className="size-3" />
          {totalSkills} skills
        </Badge>
        {selectedStudentName && (
          <Badge variant="secondary">Overlaying {selectedStudentName}&apos;s saved selections</Badge>
        )}
      </div>

      {books.map((book) => (
        <BookCard key={book.book_id} book={book} selectedStudentName={selectedStudentName} />
      ))}
    </div>
  );
}

function BookCard({
  book,
  selectedStudentName,
}: {
  book: SkillBankDisplayBook;
  selectedStudentName?: string | null;
}) {
  const totalSkills = book.chapters.reduce((sum, chapter) => sum + chapter.skills.length, 0);

  return (
    <Card className="shadow-none">
      <CardHeader className="pb-2">
        <div className="flex items-start gap-3">
          <div className="rounded-md bg-violet-100 p-2 shrink-0 dark:bg-violet-950">
            <BookOpen className="size-4 text-violet-600 dark:text-violet-400" />
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="text-sm font-semibold leading-tight">{book.title}</h3>
            {book.authors && <p className="mt-0.5 text-xs text-muted-foreground">{book.authors}</p>}
            <div className="mt-1.5 flex items-center gap-2">
              <Badge variant="secondary" className="px-1.5 py-0 text-[10px]">
                {book.chapters.length} chapters
              </Badge>
              <Badge variant="secondary" className="px-1.5 py-0 text-[10px]">
                {totalSkills} skills
              </Badge>
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <Accordion type="multiple" className="w-full">
          {book.chapters.map((chapter) => (
            <AccordionItem
              key={chapter.chapter_id}
              value={chapter.chapter_id}
              className="border-b-0 last:border-b-0"
            >
              <AccordionTrigger className="gap-2 py-2 hover:no-underline">
                <div className="flex min-w-0 flex-1 items-center gap-2">
                  <span className="flex size-5 shrink-0 items-center justify-center rounded bg-muted text-[10px] font-bold">
                    {chapter.chapter_index}
                  </span>
                  <span className="truncate text-xs">Chapter {chapter.chapter_index}: {chapter.title}</span>
                </div>
                <Badge variant="outline" className="mr-2 shrink-0 gap-0.5 px-1.5 py-0 text-[10px]">
                  <Lightbulb className="size-2.5" />
                  {chapter.skills.length}
                </Badge>
              </AccordionTrigger>
              <AccordionContent>
                {chapter.skills.length === 0 ? (
                  <p className="pl-7 text-xs text-muted-foreground">No skills extracted</p>
                ) : (
                  <div className="flex flex-wrap gap-1.5 pl-7">
                    {chapter.skills.map((skill) => (
                      <ReadOnlySkillChip
                        key={`${chapter.chapter_id}-${skill.name}`}
                        skill={skill}
                        selectedStudentName={selectedStudentName}
                      />
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

function ReadOnlySkillChip({
  skill,
  selectedStudentName,
}: {
  skill: SkillBankDisplayBook['chapters'][number]['skills'][number];
  selectedStudentName?: string | null;
}) {
  const [open, setOpen] = useState(false);
  const hasDescription = Boolean(skill.description);

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <Collapsible open={open} onOpenChange={setOpen}>
        <CollapsibleTrigger asChild>
          <Badge
            variant={skill.overlay?.isSelected ? 'default' : 'secondary'}
            className="cursor-pointer gap-1 px-2 py-0.5 text-[11px] transition-colors hover:bg-secondary/80"
            title={skill.description ?? ''}
          >
            <span>{skill.name}</span>
            {hasDescription && (
              <ChevronDown
                className={cn('size-2.5 transition-transform', open && 'rotate-180')}
              />
            )}
          </Badge>
        </CollapsibleTrigger>
        {hasDescription && (
          <CollapsibleContent className="mt-1 mb-1 w-full basis-full">
            <p className="rounded bg-muted/50 px-2 py-1 text-[10px] text-muted-foreground">
              {skill.description}
            </p>
          </CollapsibleContent>
        )}
      </Collapsible>

      {skill.overlay?.isSelected && selectedStudentName && (
        <Badge variant="outline" className="text-[10px]">
          Selected by {selectedStudentName}
        </Badge>
      )}

      {(skill.overlay?.peerCount ?? 0) > 0 && (
        <Badge variant="outline" className="gap-1 text-[10px]">
          <Users className="size-3" />
          {skill.overlay?.peerCount}
        </Badge>
      )}
    </div>
  );
}
