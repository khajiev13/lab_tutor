import api from '@/services/api';
import type { AxiosError } from 'axios';
import type { LoginCredentials, LoginResponse, RegisterData, UserResponse } from './types';

export const authApi = {
  login: async (credentials: LoginCredentials): Promise<LoginResponse> => {
    // #region agent log
    const loginStart = Date.now();
    fetch('http://127.0.0.1:7242/ingest/22646e48-28ee-4f69-a8db-ceec81e08aac',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'api.ts:6',message:'Login request starting',data:{email:credentials.email,apiUrl:import.meta.env.VITE_API_URL || 'http://localhost:8000'},timestamp:loginStart,sessionId:'debug-session',runId:'run1',hypothesisId:'C'})}).catch(()=>{});
    // #endregion
    // FastAPI OAuth2PasswordBearer expects form data for token endpoint
    const formData = new URLSearchParams();
    formData.append('username', credentials.email);
    formData.append('password', credentials.password);

    try {
      const response = await api.post<LoginResponse>('/auth/jwt/login', formData, {
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
      });
      // #region agent log
      fetch('http://127.0.0.1:7242/ingest/22646e48-28ee-4f69-a8db-ceec81e08aac',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'api.ts:17',message:'Login request success',data:{status:response.status,hasToken:!!response.data.access_token,elapsed:Date.now()-loginStart},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'C'})}).catch(()=>{});
      // #endregion
      return response.data;
    } catch (error: unknown) {
      const axiosError = error as AxiosError | undefined;
      // #region agent log
      const code =
        axiosError && typeof axiosError === 'object' && 'code' in axiosError
          ? String((axiosError as { code?: unknown }).code ?? '')
          : '';
      fetch('http://127.0.0.1:7242/ingest/22646e48-28ee-4f69-a8db-ceec81e08aac',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'api.ts:20',message:'Login request error',data:{error:axiosError?.message,code,status:axiosError?.response?.status,elapsed:Date.now()-loginStart},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'C'})}).catch(()=>{});
      // #endregion
      throw error;
    }
  },
  register: async (data: RegisterData): Promise<UserResponse> => {
    const response = await api.post<UserResponse>('/auth/register', data);
    return response.data;
  },
  getMe: async (): Promise<UserResponse> => {
    const response = await api.get<UserResponse>('/users/me');
    return response.data;
  },
  refresh: async (refreshToken: string): Promise<LoginResponse> => {
    const response = await api.post<LoginResponse>('/auth/jwt/refresh', {
      refresh_token: refreshToken,
    });
    return response.data;
  },
};
