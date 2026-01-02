import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { authApi } from '../api';
import type { LoginCredentials, RegisterData, UserResponse } from '../types';

// User type alias
type User = UserResponse;

// Auth context interface
interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (credentials: LoginCredentials) => Promise<void>;
  register: (data: RegisterData) => Promise<UserResponse>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const fetchUser = useCallback(async () => {
    // #region agent log
    const fetchStart = Date.now();
    const token = localStorage.getItem('access_token');
    fetch('http://127.0.0.1:7242/ingest/22646e48-28ee-4f69-a8db-ceec81e08aac',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'AuthContext.tsx:24',message:'fetchUser starting',data:{hasToken:!!token},timestamp:fetchStart,sessionId:'debug-session',runId:'run1',hypothesisId:'H'})}).catch(()=>{});
    // #endregion
    try {
      const userData = await authApi.getMe();
      // #region agent log
      fetch('http://127.0.0.1:7242/ingest/22646e48-28ee-4f69-a8db-ceec81e08aac',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'AuthContext.tsx:27',message:'fetchUser success',data:{userId:userData.id,elapsed:Date.now()-fetchStart},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'H'})}).catch(()=>{});
      // #endregion
      setUser(userData);
    } catch (error: any) {
      // #region agent log
      fetch('http://127.0.0.1:7242/ingest/22646e48-28ee-4f69-a8db-ceec81e08aac',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'AuthContext.tsx:29',message:'fetchUser error',data:{status:error.response?.status,message:error.message,elapsed:Date.now()-fetchStart},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'H'})}).catch(()=>{});
      // #endregion
      console.error('Failed to fetch user:', error);
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (token) {
      fetchUser();
    } else {
      setIsLoading(false);
    }
  }, [fetchUser]);

  const login = useCallback(async (credentials: LoginCredentials) => {
    // #region agent log
    const loginStart = Date.now();
    fetch('http://127.0.0.1:7242/ingest/22646e48-28ee-4f69-a8db-ceec81e08aac',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'AuthContext.tsx:46',message:'AuthContext login starting',data:{email:credentials.email},timestamp:loginStart,sessionId:'debug-session',runId:'run1',hypothesisId:'C'})}).catch(()=>{});
    // #endregion
    try {
      const response = await authApi.login(credentials);
      // #region agent log
      fetch('http://127.0.0.1:7242/ingest/22646e48-28ee-4f69-a8db-ceec81e08aac',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'AuthContext.tsx:49',message:'AuthContext login success, storing tokens',data:{hasAccessToken:!!response.access_token,hasRefreshToken:!!response.refresh_token,tokenType:response.token_type,elapsed:Date.now()-loginStart},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'C'})}).catch(()=>{});
      // #endregion
      localStorage.setItem('access_token', response.access_token);
      localStorage.setItem('refresh_token', response.refresh_token);
      await fetchUser();
    } catch (error: any) {
      // #region agent log
      fetch('http://127.0.0.1:7242/ingest/22646e48-28ee-4f69-a8db-ceec81e08aac',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'AuthContext.tsx:52',message:'AuthContext login error',data:{error:error.message,status:error.response?.status,elapsed:Date.now()-loginStart},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'C'})}).catch(()=>{});
      // #endregion
      throw error;
    }
  }, [fetchUser]);

  const register = useCallback(async (data: RegisterData): Promise<UserResponse> => {
    const response = await authApi.register(data);
    return response;
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    setUser(null);
  }, []);

  const value: AuthContextType = {
    user,
    isAuthenticated: !!user,
    isLoading,
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
