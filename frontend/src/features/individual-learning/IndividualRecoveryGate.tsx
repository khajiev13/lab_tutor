import { Loader2, RefreshCw } from 'lucide-react';
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/features/auth/context/AuthContext';
import {
  getIndividualRecoveryRedirect,
  recoverIndividualWorkflow,
} from '@/features/individual-learning/recovery';

type RecoveryGateState = {
  requestKey: string;
  error: string | null;
  redirectPath: string | null;
};

export function IndividualRecoveryGate({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const location = useLocation();
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<RecoveryGateState | null>(null);
  const userId = user?.id;
  const userRole = user?.role;
  const requestKey = useMemo(
    () => `${userId ?? 'anonymous'}:${userRole ?? 'none'}:${location.pathname}:${attempt}`,
    [attempt, location.pathname, userId, userRole],
  );

  useEffect(() => {
    if (!userId || userRole !== 'individual') {
      return;
    }

    let active = true;
    recoverIndividualWorkflow(userId)
      .then(({ profile, session }) => {
        if (active) {
          setState({
            requestKey,
            error: null,
            redirectPath: getIndividualRecoveryRedirect(
              profile.next_step,
              location.pathname,
              session,
            ),
          });
        }
      })
      .catch((recoveryError) => {
        console.error(recoveryError);
        if (active) {
          setState({
            requestKey,
            error: 'We could not recover your progress. Check your connection and try again.',
            redirectPath: null,
          });
        }
      });

    return () => {
      active = false;
    };
  }, [location.pathname, requestKey, userId, userRole]);

  if (!user || user.role !== 'individual') {
    return <Navigate to="/home" replace />;
  }

  if (state?.requestKey !== requestKey) {
    return (
      <div className="flex min-h-64 items-center justify-center gap-3 text-sm text-muted-foreground">
        <Loader2 className="size-5 animate-spin" />
        Recovering your individual learning progress...
      </div>
    );
  }

  if (state.error) {
    return (
      <Alert variant="destructive" className="mx-auto max-w-2xl">
        <RefreshCw className="size-4" />
        <AlertTitle>Could not recover your progress</AlertTitle>
        <AlertDescription className="flex flex-col items-start gap-3">
          <span>{state.error}</span>
          <Button type="button" size="sm" variant="outline" onClick={() => setAttempt((value) => value + 1)}>
            <RefreshCw className="size-4" />
            Retry recovery
          </Button>
        </AlertDescription>
      </Alert>
    );
  }

  if (state.redirectPath && state.redirectPath !== location.pathname) {
    return <Navigate to={state.redirectPath} replace />;
  }

  return <>{children}</>;
}
