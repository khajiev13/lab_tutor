import { zodResolver } from '@hookform/resolvers/zod';
import { FileUp, Loader2, RefreshCw, Sparkles } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { Link, useNavigate } from 'react-router-dom';
import { z } from 'zod';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
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
  startIndividualGraph,
  type IndividualProfile,
  uploadCv,
} from '@/features/individual-learning/api';
import { persistIndividualGraphResponse } from '@/features/individual-learning/graph-session';

const uploadSchema = z.object({
  file: z
    .custom<File>((value) => value instanceof File, 'Select a CV file to continue.')
    .refine((file) => /\.(pdf|docx)$/i.test(file.name), 'Choose a PDF or DOCX file.'),
});

type UploadFormValues = z.infer<typeof uploadSchema>;

function formatStatus(status: IndividualProfile['onboarding_status']) {
  return status.replace(/_/g, ' ');
}

export default function IndividualOnboardingPage() {
  const navigate = useNavigate();
  const [profile, setProfile] = useState<IndividualProfile | null>(null);
  const [isLoadingProfile, setIsLoadingProfile] = useState(true);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [profileLoadAttempt, setProfileLoadAttempt] = useState(0);
  const [isUploading, setIsUploading] = useState(false);
  const [lastUpload, setLastUpload] = useState<{
    id: number;
    original_filename: string;
    status: string;
  } | null>(null);

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
          setProfileError(null);
        }
      } catch (error) {
        console.error(error);
        if (active) {
          setProfileError('We could not load your current onboarding status.');
        }
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
  }, [profileLoadAttempt]);

  const retryProfileStatus = () => {
    setProfileError(null);
    setIsLoadingProfile(true);
    setProfileLoadAttempt((attempt) => attempt + 1);
  };

  const onSubmit = form.handleSubmit(async ({ file }) => {
    setIsUploading(true);
    let didUpload = false;
    try {
      const uploadResponse = await uploadCv(file);
      didUpload = true;
      setLastUpload({
        id: uploadResponse.id,
        original_filename: uploadResponse.original_filename,
        status: uploadResponse.status,
      });

      const graphResponse = await startIndividualGraph(uploadResponse.id);
      const { stored } = persistIndividualGraphResponse(graphResponse, {
        cvDocumentId: uploadResponse.id,
        ownerUserId: uploadResponse.user_id,
        replace: true,
      });
      if (!stored) {
        toast.warning('Review state is available for this page session only.', {
          description: 'Avoid reloading until you finish profile review.',
        });
      }
      toast.success('CV uploaded', {
        description: 'Your extracted profile is ready for review.',
      });
      navigate('/individual/profile');
    } catch (error) {
      console.error(error);
      toast.error(didUpload ? 'Could not start CV review' : 'CV upload failed', {
        description: didUpload
          ? 'Your CV was saved, but the review workflow did not start. Please try again.'
          : 'Please try a PDF or DOCX file again.',
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
              Upload a PDF or DOCX CV to start the individual learning review flow.
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
                          accept=".pdf,.docx"
                          onBlur={field.onBlur}
                          onChange={(event) => field.onChange(event.target.files?.[0])}
                        />
                      </FormControl>
                      <FormDescription>
                        Accepted formats: `.pdf` and `.docx`.
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
            {profileError ? (
              <Alert variant="destructive">
                <RefreshCw className="size-4" />
                <AlertTitle>Status unavailable</AlertTitle>
                <AlertDescription className="flex flex-col items-start gap-3">
                  <span>{profileError}</span>
                  <Button type="button" size="sm" variant="outline" onClick={retryProfileStatus}>
                    <RefreshCw className="size-4" />
                    Retry status
                  </Button>
                </AlertDescription>
              </Alert>
            ) : null}
            <div className="rounded-md border p-4">
              <div className="text-muted-foreground">Onboarding</div>
              <div className="mt-1 font-medium capitalize">
                {isLoadingProfile ? 'Loading...' : profile ? formatStatus(profile.onboarding_status) : 'Unavailable'}
              </div>
            </div>
            {lastUpload ? (
              <div className="rounded-md border p-4">
                <div className="text-muted-foreground">Last upload</div>
                <div className="mt-1 font-medium">{lastUpload.original_filename}</div>
                <div className="text-sm text-muted-foreground">Document #{lastUpload.id}</div>
                <div className="capitalize text-muted-foreground">{lastUpload.status}</div>
              </div>
            ) : null}
            <div className="rounded-md border p-4">
              <div className="flex items-center gap-2 font-medium">
                <Sparkles className="size-4" />
                What happens next
              </div>
              <p className="mt-2 text-muted-foreground">
                After upload, you will review extracted profile details, choose interested jobs, and
                then build a market-skill learning path.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
