import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { authApi } from '../api';
import type { LoginCredentials, RegisterData, UserResponse } from '../types';
import { isTokenExpired } from '../utils/token';

// User type alias
type User = UserResponse;

// Auth context interface
interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  /** True when we're waiting on a cold-started backend (> 4s). */
  isServerWakingUp: boolean;
  login: (credentials: LoginCredentials) => Promise<void>;
  register: (data: RegisterData) => Promise<UserResponse>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isServerWakingUp, setIsServerWakingUp] = useState(false);

  const clearTokens = useCallback(() => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
  }, []);

  const fetchUser = useCallback(async () => {
    try {
      const userData = await authApi.getMe();
      setUser(userData);
    } catch (error: unknown) {
      console.error('Failed to fetch user:', error);
      clearTokens();
      setUser(null);
    } finally {
      setIsLoading(false);
      setIsServerWakingUp(false);
    }
  }, [clearTokens]);

  /**
   * Try to restore the session from stored tokens.
   *
   * Optimisation: we decode the JWT on the client to check expiry *before*
   * making any network call.  This avoids a wasted round-trip to `/users/me`
   * that would 401 anyway if the access token has expired while the backend
   * is cold-starting on Azure Container Apps.
   */
  const restoreSession = useCallback(async () => {
    const accessToken = localStorage.getItem('access_token');
    const refreshToken = localStorage.getItem('refresh_token');

    // Nothing stored → go straight to login.
    if (!accessToken) {
      setIsLoading(false);
      return;
    }

    // Show "server waking up" hint after 4 s to reassure the user.
    const wakingUpTimer = setTimeout(() => setIsServerWakingUp(true), 4_000);

    try {
      // Fast path: access token still valid → fetch user immediately.
      if (!isTokenExpired(accessToken)) {
        await fetchUser();
        return;
      }

      // Access token expired.  Try to refresh without hitting /users/me first.
      if (refreshToken && !isTokenExpired(refreshToken)) {
        try {
          const tokens = await authApi.refresh(refreshToken);
          localStorage.setItem('access_token', tokens.access_token);
          localStorage.setItem('refresh_token', tokens.refresh_token);
          await fetchUser();
          return;
        } catch {
          // Refresh failed — fall through to clear tokens.
        }
      }

      // Both tokens expired or refresh failed → clear & show login.
      clearTokens();
      setUser(null);
    } finally {
      clearTimeout(wakingUpTimer);
      setIsLoading(false);
      setIsServerWakingUp(false);
    }
  }, [fetchUser, clearTokens]);

  useEffect(() => {
    restoreSession();
  }, [restoreSession]);

  const login = useCallback(async (credentials: LoginCredentials) => {
    const response = await authApi.login(credentials);
    localStorage.setItem('access_token', response.access_token);
    localStorage.setItem('refresh_token', response.refresh_token);
    await fetchUser();
  }, [fetchUser]);

  const register = useCallback(async (data: RegisterData): Promise<UserResponse> => {
    const response = await authApi.register(data);
    return response;
  }, []);

  const logout = useCallback(() => {
    clearTokens();
    setUser(null);
  }, [clearTokens]);

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
