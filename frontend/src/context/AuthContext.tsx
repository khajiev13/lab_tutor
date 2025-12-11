import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { authApi } from '@/services/api';
import type { LoginCredentials, RegisterData, UserResponse } from '@/services/api';

// JWT token payload interface
interface JWTPayload {
  sub: string; // email
  role: 'student' | 'teacher';
  exp: number;
}

// User interface for context
interface User {
  email: string;
  role: 'student' | 'teacher';
  first_name?: string;
  last_name?: string;
}

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

// Helper function to decode JWT token
const decodeToken = (token: string): JWTPayload | null => {
  try {
    const base64Url = token.split('.')[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split('')
        .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join('')
    );
    return JSON.parse(jsonPayload);
  } catch {
    return null;
  }
};

// Helper function to check if token is expired
const isTokenExpired = (token: string): boolean => {
  const payload = decodeToken(token);
  if (!payload) return true;
  return Date.now() >= payload.exp * 1000;
};

// Helper function to get user from token
const getUserFromToken = (token: string): User | null => {
  const payload = decodeToken(token);
  if (!payload) return null;
  return {
    email: payload.sub,
    role: payload.role,
  };
};

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Initialize auth state from stored token
  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (token && !isTokenExpired(token)) {
      const tokenUser = getUserFromToken(token);
      setUser(tokenUser);
    } else if (token) {
      // Token exists but is expired
      localStorage.removeItem('access_token');
    }
    setIsLoading(false);
  }, []);

  const login = useCallback(async (credentials: LoginCredentials) => {
    const response = await authApi.login(credentials);
    localStorage.setItem('access_token', response.access_token);
    const tokenUser = getUserFromToken(response.access_token);
    setUser(tokenUser);
  }, []);

  const register = useCallback(async (data: RegisterData): Promise<UserResponse> => {
    const response = await authApi.register(data);
    return response;
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('access_token');
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

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export default AuthContext;
