import { zodResolver } from '@hookform/resolvers/zod';
import { FileUp, Loader2, Sparkles } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { Link } from 'react-router-dom';
import { z } from 'zod';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import {
  getIndividualProfile,
  type IndividualProfile,
  uploadCv,
} from '@/features/individual-learning/api';

const uploadSchema = z.object({
  file: z.custom<FileList>(
    (value) => value instanceof FileList && value.length > 0,
    'Select a CV file to continue.',
  ),
});

type UploadFormValues = z.infer<typeof uploadSchema>;

function formatStatus(status: IndividualProfile['onboarding_status']) {
  return status.replace(/_/g, ' ');
}

export default function IndividualOnboardingPage() {
  const [profile, setProfile] = useState<IndividualProfile | null>(null);
  const [isLoadingProfile, setIsLoadingProfile] = useState(true);
  const [isUploading, setIsUploading] = useState(false);
  const [lastUpload, setLastUpload] = useState<{ id: number; status: string } | null>(null);

  const form = useForm<UploadFormValues>({
    resolver: zodResolver(uploadSchema),
  });

  useEffect(() => {
    let active = true;

    async function loadProfile() {
      try {
        const nextProfile = await getIndividualProfile();
        if (active) {
          setProfile(nextProfile);
        }
      } catch (error) {
        console.error(error);
        toast.error('Failed to load your onboarding status.');
      } finally {
        if (active) {
          setIsLoadingProfile(false);
        }
      }
    }

    loadProfile();

    return () => {
      active = false;
    };
  }, []);

  const onSubmit = form.handleSubmit(async (values) => {
    const file = values.file.item(0);
    if (!file) {
      return;
    }

    setIsUploading(true);
    try {
      const response = await uploadCv(file);
      setLastUpload(response);
      const nextProfile = await getIndividualProfile();
      setProfile(nextProfile);
      toast.success('CV uploaded', {
        description: 'We saved your document and refreshed your onboarding status.',
      });
      form.reset();
    } catch (error) {
      console.error(error);
      toast.error('CV upload failed', {
        description: 'Please try a PDF or DOC file again.',
      });
    } finally {
      setIsUploading(false);
    }
  });

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold">CV onboarding</h1>
        <p className="text-sm text-muted-foreground">
          Upload your latest CV so Lab Tutor can prepare your individual learning profile.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>Upload CV</CardTitle>
            <CardDescription>
              This shell is wired to the real onboarding upload endpoint.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Form {...form}>
              <form onSubmit={onSubmit} className="space-y-4">
                <FormField
                  control={form.control}
                  name="file"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>CV file</FormLabel>
                      <FormControl>
                        <Input
                          type="file"
                          name={field.name}
                          ref={field.ref}
                          accept=".pdf,.doc,.docx"
                          onBlur={field.onBlur}
                          onChange={(event) => field.onChange(event.target.files)}
                        />
                      </FormControl>
                      <FormDescription>
                        PDF, DOC, and DOCX files are accepted by this frontend shell.
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <div className="flex flex-wrap gap-3">
                  <Button type="submit" disabled={isUploading}>
                    {isUploading ? (
                      <Loader2 className="size-4 animate-spin" />
                    ) : (
                      <FileUp className="size-4" />
                    )}
                    Upload CV
                  </Button>
                  <Button variant="outline" asChild>
                    <Link to="/individual/profile">View profile status</Link>
                  </Button>
                </div>
              </form>
            </Form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Current status</CardTitle>
            <CardDescription>Live profile data from `/individual-learning/profile`.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            <div className="rounded-md border p-4">
              <div className="text-muted-foreground">Onboarding</div>
              <div className="mt-1 font-medium capitalize">
                {isLoadingProfile ? 'Loading...' : profile ? formatStatus(profile.onboarding_status) : 'Unavailable'}
              </div>
            </div>
            {lastUpload ? (
              <div className="rounded-md border p-4">
                <div className="text-muted-foreground">Last upload</div>
                <div className="mt-1 font-medium">Document #{lastUpload.id}</div>
                <div className="capitalize text-muted-foreground">{lastUpload.status}</div>
              </div>
            ) : null}
            <div className="rounded-md border p-4">
              <div className="flex items-center gap-2 font-medium">
                <Sparkles className="size-4" />
                What happens next
              </div>
              <p className="mt-2 text-muted-foreground">
                After upload, the backend moves your profile toward review, job selection, and skill
                selection.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
