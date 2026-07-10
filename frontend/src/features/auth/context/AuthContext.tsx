import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';
import { authApi } from '../api';
import type { LoginCredentials, RegisterData, UserResponse } from '../types';
import { isTokenExpired } from '../utils/token';
import {
  clearIndividualGraphSession,
  clearIndividualGraphSessionForOtherUser,
} from '@/features/individual-learning/graph-session';
import { resetTeacherTwinSimulationTasks } from '@/features/arcd-agent/state/teacherTwinSimulationStore';
import { resetTeacherTwinUiState } from '@/features/arcd-agent/state/teacherTwinUiStore';
import {
  establishAuthSession,
  invalidateAuthSession,
  StaleAuthSessionError,
} from '@/features/auth/auth-session';

// User type alias
type User = UserResponse;

// Auth context interface
interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  /** True when we're waiting on a cold-started backend (> 4s). */
  isServerWakingUp: boolean;
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

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isServerWakingUp, setIsServerWakingUp] = useState(false);
  const authAttemptRef = useRef(0);
  const isMountedRef = useRef(true);

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
      setUser(null);
    }
  }, [clearTokens, resetUserScopedState]);

  const fetchUser = useCallback(async (attempt: number): Promise<UserResponse> => {
    const userData = await authApi.getMe();
    if (attempt !== authAttemptRef.current || !isMountedRef.current) {
      throw new StaleAuthSessionError();
    }

    clearIndividualGraphSessionForOtherUser(userData.id);
    establishAuthSession(userData.id);
    setUser(userData);
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

    // Nothing stored → go straight to login.
    if (!accessToken) {
      invalidateAuthSession();
      resetUserScopedState();
      if (isMountedRef.current && attempt === authAttemptRef.current) {
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
          localStorage.setItem('access_token', tokens.access_token);
          localStorage.setItem('refresh_token', tokens.refresh_token);
          await fetchUser(attempt);
          return;
        } catch (error: unknown) {
          if (error instanceof StaleAuthSessionError) {
            return;
          }
          if (isConfirmedAuthenticationFailure(error)) {
            clearConfirmedSession();
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
      if (isConfirmedAuthenticationFailure(error)) {
        clearConfirmedSession();
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

      authAttemptRef.current += 1;
      invalidateAuthSession();
      resetUserScopedState();
      setUser(null);
      setIsLoading(true);
      setIsServerWakingUp(false);
      void restoreSession();
    };

    window.addEventListener('storage', handleStorage);
    return () => window.removeEventListener('storage', handleStorage);
  }, [resetUserScopedState, restoreSession]);

  const login = useCallback(async (credentials: LoginCredentials): Promise<UserResponse> => {
    const response = await authApi.login(credentials);
    const attempt = ++authAttemptRef.current;
    invalidateAuthSession();
    resetUserScopedState();
    setUser(null);
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
    setUser(null);
    // Clear teacher-twin caches so the next teacher who logs in starts with
    // a fresh dashboard. The simulation store holds expensive results; the
    // UI store holds tab/filter/slider state. Both are session-scoped.
  }, [clearTokens, resetUserScopedState]);

  const value: AuthContextType = {
    user,
    isAuthenticated: !!user,
    isLoading,
    isServerWakingUp,
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
