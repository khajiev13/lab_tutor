import { AlertCircle, BriefcaseBusiness, FileText, Route, UserRoundCheck } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { getIndividualProfile, type IndividualProfile } from '../api';

function formatStatus(status: IndividualProfile['onboarding_status']) {
  return status.replace(/_/g, ' ');
}

function getPrimaryAction(status: IndividualProfile['onboarding_status']) {
  switch (status) {
    case 'needs_cv':
      return { label: 'Upload CV', to: '/individual/onboarding', icon: FileText };
    case 'needs_jobs':
      return { label: 'Choose job matches', to: '/individual/jobs', icon: BriefcaseBusiness };
    case 'needs_skill_selection':
    case 'ready':
      return { label: 'Review skills', to: '/individual/skills', icon: Route };
    default:
      return { label: 'Refresh later', to: '/individual/profile', icon: UserRoundCheck };
  }
}

export default function IndividualProfilePage() {
  const [profile, setProfile] = useState<IndividualProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function loadProfile() {
      try {
        const data = await getIndividualProfile();
        if (active) {
          setProfile(data);
        }
      } catch (loadError) {
        console.error(loadError);
        if (active) {
          setError('We could not load your individual learning profile.');
        }
      } finally {
        if (active) {
          setIsLoading(false);
        }
      }
    }

    loadProfile();

    return () => {
      active = false;
    };
  }, []);

  const primaryAction = useMemo(
    () => (profile ? getPrimaryAction(profile.onboarding_status) : null),
    [profile],
  );

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold">Individual profile</h1>
        <p className="text-sm text-muted-foreground">
          Track your onboarding state and the target roles driving your learning path.
        </p>
      </div>

      {error ? (
        <Alert variant="destructive">
          <AlertCircle className="size-4" />
          <AlertTitle>Profile unavailable</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>Profile status</CardTitle>
            <CardDescription>Live data from the individual profile endpoint.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap items-center gap-3">
              <Badge variant="secondary" className="capitalize">
                {isLoading ? 'Loading status' : profile ? formatStatus(profile.onboarding_status) : 'Unknown'}
              </Badge>
              {profile?.reviewed_at ? (
                <span className="text-sm text-muted-foreground">
                  Reviewed {new Date(profile.reviewed_at).toLocaleString()}
                </span>
              ) : null}
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <div className="rounded-md border p-4">
                <div className="text-sm text-muted-foreground">Preferred country</div>
                <div className="mt-1 font-medium">{profile?.preferred_country ?? 'Not set yet'}</div>
              </div>
              <div className="rounded-md border p-4">
                <div className="text-sm text-muted-foreground">Preferred location</div>
                <div className="mt-1 font-medium">{profile?.preferred_location ?? 'Not set yet'}</div>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Next step</CardTitle>
            <CardDescription>Use the current onboarding status to move forward.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="rounded-md border p-4">
              <div className="text-sm text-muted-foreground">Target titles</div>
              <div className="mt-2 flex flex-wrap gap-2">
                {profile?.target_titles.length ? (
                  profile.target_titles.map((title) => (
                    <Badge key={title} variant="outline">
                      {title}
                    </Badge>
                  ))
                ) : (
                  <span className="text-sm text-muted-foreground">No titles selected yet.</span>
                )}
              </div>
            </div>
            {primaryAction ? (
              <Button asChild className="w-full">
                <Link to={primaryAction.to}>
                  <primaryAction.icon className="size-4" />
                  {primaryAction.label}
                </Link>
              </Button>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
