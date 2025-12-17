import api from '@/services/api';
import type { LoginCredentials, LoginResponse, RegisterData, UserResponse } from './types';

export const authApi = {
  login: async (credentials: LoginCredentials): Promise<LoginResponse> => {
    // FastAPI OAuth2PasswordBearer expects form data for token endpoint
    const formData = new URLSearchParams();
    formData.append('username', credentials.email);
    formData.append('password', credentials.password);

    const response = await api.post<LoginResponse>('/auth/jwt/login', formData, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    });
    return response.data;
  },
  register: async (data: RegisterData): Promise<UserResponse> => {
    const response = await api.post<UserResponse>('/auth/register', data);
    return response.data;
  },
  getMe: async (): Promise<UserResponse> => {
    const response = await api.get<UserResponse>('/users/me');
    return response.data;
  },
};
