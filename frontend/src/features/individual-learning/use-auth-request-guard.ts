import { useCallback, useEffect, useRef } from 'react';
import {
  assertAuthSessionCurrent,
  isAuthSessionCurrent,
  StaleAuthSessionError,
  type AuthSessionSnapshot,
} from '@/features/auth/auth-session';

export function useAuthRequestGuard() {
  const isMountedRef = useRef(true);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const assertRequestCurrent = useCallback((snapshot: AuthSessionSnapshot) => {
    if (!isMountedRef.current) {
      throw new StaleAuthSessionError('The page closed before the request completed.');
    }
    assertAuthSessionCurrent(snapshot);
  }, []);

  const isRequestCurrent = useCallback(
    (snapshot: AuthSessionSnapshot) =>
      isMountedRef.current && isAuthSessionCurrent(snapshot),
    [],
  );

  return { assertRequestCurrent, isRequestCurrent };
}
