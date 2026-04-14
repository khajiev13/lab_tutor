import { zodResolver } from '@hookform/resolvers/zod';
import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { Loader2, Settings2 } from 'lucide-react';
import { toast } from 'sonner';

import { coursesApi } from '@/features/courses/api';
import type { SkillSelectionRange } from '@/features/curriculum/types';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';

const rangeSchema = z
  .object({
    min_skills: z.number().int().min(1).max(200),
    max_skills: z.number().int().min(1).max(200),
  })
  .refine((value) => value.min_skills <= value.max_skills, {
    message: 'Minimum must be less than or equal to maximum.',
    path: ['max_skills'],
  });

type RangeFormValues = z.infer<typeof rangeSchema>;

type SkillSelectionRangeCardProps = {
  courseId: number;
  selectionRange: SkillSelectionRange;
  onUpdated: (range: SkillSelectionRange) => void;
};

export function SkillSelectionRangeCard({
  courseId,
  selectionRange,
  onUpdated,
}: SkillSelectionRangeCardProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const form = useForm<RangeFormValues>({
    resolver: zodResolver(rangeSchema),
    defaultValues: {
      min_skills: selectionRange.min_skills,
      max_skills: selectionRange.max_skills,
    },
  });

  useEffect(() => {
    form.reset({
      min_skills: selectionRange.min_skills,
      max_skills: selectionRange.max_skills,
    });
  }, [form, selectionRange.max_skills, selectionRange.min_skills]);

  const handleCancel = () => {
    form.reset({
      min_skills: selectionRange.min_skills,
      max_skills: selectionRange.max_skills,
    });
    setIsEditing(false);
  };

  const handleSubmit = form.handleSubmit(async (values) => {
    setIsSaving(true);
    try {
      const updatedRange = await coursesApi.updateSkillSelectionRange(courseId, values);
      onUpdated(updatedRange);
      setIsEditing(false);
      toast.success('Skill selection range saved');
    } catch (error) {
      toast.error('Failed to save skill selection range');
      console.error(error);
    } finally {
      setIsSaving(false);
    }
  });

  return (
    <Card className="mb-5 border-border/60 shadow-none">
      <CardHeader className="pb-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div className="space-y-1">
            <CardTitle className="flex items-center gap-2 text-base">
              <Settings2 className="h-4 w-4 text-muted-foreground" />
              Student skill selection range
            </CardTitle>
            <CardDescription>
              This course setting controls how many skills a student can include before building a
              learning path.
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="secondary">
              {selectionRange.min_skills}-{selectionRange.max_skills} skills
            </Badge>
            {selectionRange.is_default && <Badge variant="outline">Using default</Badge>}
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        {!isEditing ? (
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <p className="text-sm text-muted-foreground">
              Students will be guided to stay between {selectionRange.min_skills} and{' '}
              {selectionRange.max_skills} selected skills before building.
            </p>
            <Button variant="outline" onClick={() => setIsEditing(true)}>
              Edit range
            </Button>
          </div>
        ) : (
          <Form {...form}>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <FormField
                  control={form.control}
                  name="min_skills"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Minimum skills</FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          min={1}
                          max={200}
                          value={field.value}
                          onChange={(event) =>
                            field.onChange(
                              event.target.value === '' ? Number.NaN : Number(event.target.value),
                            )
                          }
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="max_skills"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Maximum skills</FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          min={1}
                          max={200}
                          value={field.value}
                          onChange={(event) =>
                            field.onChange(
                              event.target.value === '' ? Number.NaN : Number(event.target.value),
                            )
                          }
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
              <div className="flex items-center justify-end gap-2">
                <Button type="button" variant="ghost" onClick={handleCancel} disabled={isSaving}>
                  Cancel
                </Button>
                <Button type="submit" disabled={isSaving}>
                  {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  Save
                </Button>
              </div>
            </form>
          </Form>
        )}
      </CardContent>
    </Card>
  );
}
