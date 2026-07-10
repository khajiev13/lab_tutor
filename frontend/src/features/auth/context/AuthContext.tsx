import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';
import { authApi } from '../api';
import type { LoginCredentials, RegisterData, UserResponse } from '../types';
import { decodeJwtPayload, isTokenExpired } from '../utils/token';
import {
  clearIndividualGraphSession,
  clearIndividualGraphSessionForOtherUser,
} from '@/features/individual-learning/graph-session';
import { resetTeacherTwinSimulationTasks } from '@/features/arcd-agent/state/teacherTwinSimulationStore';
import { resetTeacherTwinUiState } from '@/features/arcd-agent/state/teacherTwinUiStore';
import {
  captureAuthSessionState,
  establishAuthSession,
  invalidateAuthSession,
  isAuthSessionStateCurrent,
  StaleAuthSessionError,
} from '@/features/auth/auth-session';
import { AUTH_SESSION_EXPIRED_EVENT } from '@/features/auth/auth-events';

// User type alias
type User = UserResponse;

// Auth context interface
interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  /** True when we're waiting on a cold-started backend (> 4s). */
  isServerWakingUp: boolean;
  sessionError: string | null;
  retrySession: () => Promise<void>;
  login: (credentials: LoginCredentials) => Promise<UserResponse>;
  register: (data: RegisterData) => Promise<UserResponse>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

function getHttpStatus(error: unknown): number | null {
  if (!error || typeof error !== 'object' || !('response' in error)) {
    return null;
  }
  const response = (error as { response?: { status?: unknown } }).response;
  return typeof response?.status === 'number' ? response.status : null;
}

function isConfirmedAuthenticationFailure(error: unknown): boolean {
  const status = getHttpStatus(error);
  return status === 401 || status === 403;
}

function getTokenUserId(token: string | null): number | null {
  if (!token) {
    return null;
  }
  const subject = decodeJwtPayload(token)?.sub;
  const userId = typeof subject === 'string' ? Number(subject) : Number.NaN;
  return Number.isSafeInteger(userId) && userId > 0 ? userId : null;
}

const SESSION_VERIFICATION_ERROR =
  'We could not verify your session. Your work is preserved; retry when the server is available.';

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isServerWakingUp, setIsServerWakingUp] = useState(false);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const authAttemptRef = useRef(0);
  const isMountedRef = useRef(true);
  const userRef = useRef<User | null>(null);

  const clearTokens = useCallback(() => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
  }, []);

  const resetUserScopedState = useCallback(() => {
    clearIndividualGraphSession();
    resetTeacherTwinSimulationTasks();
    resetTeacherTwinUiState();
  }, []);

  const clearConfirmedSession = useCallback(() => {
    clearTokens();
    invalidateAuthSession();
    resetUserScopedState();
    if (isMountedRef.current) {
      userRef.current = null;
      setUser(null);
      setSessionError(null);
    }
  }, [clearTokens, resetUserScopedState]);

  const fetchUser = useCallback(async (attempt: number): Promise<UserResponse> => {
    const userData = await authApi.getMe();
    if (attempt !== authAttemptRef.current || !isMountedRef.current) {
      throw new StaleAuthSessionError();
    }

    clearIndividualGraphSessionForOtherUser(userData.id);
    establishAuthSession(userData.id);
    userRef.current = userData;
    setUser(userData);
    setSessionError(null);
    return userData;
  }, []);

  /**
   * Try to restore the session from stored tokens.
   *
   * Optimisation: we decode the JWT on the client to check expiry *before*
   * making any network call.  This avoids a wasted round-trip to `/users/me`
   * that would 401 anyway if the access token has expired while the backend
   * is cold-starting on Azure Container Apps.
   */
  const restoreSession = useCallback(async () => {
    const attempt = ++authAttemptRef.current;
    const accessToken = localStorage.getItem('access_token');
    const refreshToken = localStorage.getItem('refresh_token');
    const authSession = captureAuthSessionState();
    let expectedAccessToken = accessToken;
    let expectedRefreshToken = refreshToken;
    const restoreSourceIsCurrent = () =>
      attempt === authAttemptRef.current &&
      isMountedRef.current &&
      isAuthSessionStateCurrent(authSession) &&
      localStorage.getItem('access_token') === expectedAccessToken &&
      localStorage.getItem('refresh_token') === expectedRefreshToken;

    if (isMountedRef.current) {
      setSessionError(null);
    }

    // Nothing stored → go straight to login.
    if (!accessToken) {
      invalidateAuthSession();
      resetUserScopedState();
      if (isMountedRef.current && attempt === authAttemptRef.current) {
        userRef.current = null;
        setUser(null);
        setIsLoading(false);
        setIsServerWakingUp(false);
      }
      return;
    }

    // Show "server waking up" hint after 4 s to reassure the user.
    const wakingUpTimer = setTimeout(() => setIsServerWakingUp(true), 4_000);

    try {
      // Fast path: access token still valid → fetch user immediately.
      if (!isTokenExpired(accessToken)) {
        await fetchUser(attempt);
        return;
      }

      // Access token expired.  Try to refresh without hitting /users/me first.
      if (refreshToken && !isTokenExpired(refreshToken)) {
        try {
          const tokens = await authApi.refresh(refreshToken);
          if (!restoreSourceIsCurrent()) {
            throw new StaleAuthSessionError();
          }
          localStorage.setItem('access_token', tokens.access_token);
          localStorage.setItem('refresh_token', tokens.refresh_token);
          expectedAccessToken = tokens.access_token;
          expectedRefreshToken = tokens.refresh_token;
          await fetchUser(attempt);
          return;
        } catch (error: unknown) {
          if (error instanceof StaleAuthSessionError) {
            return;
          }
          const refreshSourceIsCurrent = restoreSourceIsCurrent();
          if (isConfirmedAuthenticationFailure(error) && refreshSourceIsCurrent) {
            clearConfirmedSession();
          } else if (refreshSourceIsCurrent) {
            setSessionError(SESSION_VERIFICATION_ERROR);
          }
          return;
        }
      }

      // Both tokens expired or refresh failed → clear & show login.
      clearConfirmedSession();
    } catch (error: unknown) {
      if (error instanceof StaleAuthSessionError) {
        return;
      }
      if (isConfirmedAuthenticationFailure(error) && restoreSourceIsCurrent()) {
        clearConfirmedSession();
      } else if (restoreSourceIsCurrent()) {
        setSessionError(SESSION_VERIFICATION_ERROR);
      }
    } finally {
      clearTimeout(wakingUpTimer);
      if (isMountedRef.current && attempt === authAttemptRef.current) {
        setIsLoading(false);
        setIsServerWakingUp(false);
      }
    }
  }, [clearConfirmedSession, fetchUser, resetUserScopedState]);

  useEffect(() => {
    isMountedRef.current = true;
    void restoreSession();
    return () => {
      isMountedRef.current = false;
      authAttemptRef.current += 1;
    };
  }, [restoreSession]);

  useEffect(() => {
    const handleStorage = (event: StorageEvent) => {
      if (event.key !== 'access_token' || event.oldValue === event.newValue) {
        return;
      }

      const previousUserId = getTokenUserId(event.oldValue);
      const nextUserId = getTokenUserId(event.newValue);
      const currentUserId = userRef.current?.id ?? captureAuthSessionState().userId;
      if (
        nextUserId !== null &&
        (nextUserId === currentUserId ||
          (currentUserId === null && nextUserId === previousUserId))
      ) {
        return;
      }

      authAttemptRef.current += 1;
      invalidateAuthSession();
      resetUserScopedState();
      userRef.current = null;
      setUser(null);
      setSessionError(null);
      setIsLoading(true);
      setIsServerWakingUp(false);
      void restoreSession();
    };

    window.addEventListener('storage', handleStorage);
    return () => window.removeEventListener('storage', handleStorage);
  }, [resetUserScopedState, restoreSession]);

  useEffect(() => {
    const handleExpiredSession = () => {
      authAttemptRef.current += 1;
      clearConfirmedSession();
      if (isMountedRef.current) {
        setIsLoading(false);
        setIsServerWakingUp(false);
      }
    };

    window.addEventListener(AUTH_SESSION_EXPIRED_EVENT, handleExpiredSession);
    return () => window.removeEventListener(AUTH_SESSION_EXPIRED_EVENT, handleExpiredSession);
  }, [clearConfirmedSession]);

  const retrySession = useCallback(async () => {
    if (isMountedRef.current) {
      setIsLoading(true);
      setSessionError(null);
    }
    await restoreSession();
  }, [restoreSession]);

  const login = useCallback(async (credentials: LoginCredentials): Promise<UserResponse> => {
    const response = await authApi.login(credentials);
    const attempt = ++authAttemptRef.current;
    invalidateAuthSession();
    resetUserScopedState();
    userRef.current = null;
    setUser(null);
    setSessionError(null);
    localStorage.setItem('access_token', response.access_token);
    localStorage.setItem('refresh_token', response.refresh_token);
    try {
      return await fetchUser(attempt);
    } catch (error: unknown) {
      if (isConfirmedAuthenticationFailure(error)) {
        clearConfirmedSession();
      }
      throw error;
    }
  }, [clearConfirmedSession, fetchUser, resetUserScopedState]);

  const register = useCallback(async (data: RegisterData): Promise<UserResponse> => {
    const response = await authApi.register(data);
    return response;
  }, []);

  const logout = useCallback(() => {
    authAttemptRef.current += 1;
    clearTokens();
    invalidateAuthSession();
    resetUserScopedState();
    userRef.current = null;
    setUser(null);
    setSessionError(null);
    setIsLoading(false);
    setIsServerWakingUp(false);
    // Clear teacher-twin caches so the next teacher who logs in starts with
    // a fresh dashboard. The simulation store holds expensive results; the
    // UI store holds tab/filter/slider state. Both are session-scoped.
  }, [clearTokens, resetUserScopedState]);

  const value: AuthContextType = {
    user,
    isAuthenticated: !!user,
    isLoading,
    isServerWakingUp,
    sessionError,
    retrySession,
    login,
    register,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

// eslint-disable-next-line react-refresh/only-export-components
export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export default AuthContext;
