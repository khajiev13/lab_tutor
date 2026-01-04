import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';

// Production should never call localhost from the deployed site.
// Prefer VITE_API_URL injected at build time; otherwise fall back to the known Azure backend FQDN.
const DEFAULT_PROD_API_URL = 'https://backend.mangoocean-d0c97d4f.westus2.azurecontainerapps.io';
const DEV_HOST = typeof window !== 'undefined' ? window.location.hostname : 'localhost';
const DEFAULT_DEV_API_URL = `http://${DEV_HOST}:8000`;
const API_URL =
  import.meta.env.VITE_API_URL ||
  (import.meta.env.PROD ? DEFAULT_PROD_API_URL : DEFAULT_DEV_API_URL);

const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

type TimedRequestConfig = InternalAxiosRequestConfig & {
  __timingStart?: number;
  _retry?: boolean;
};

const LOG_API_TIMINGS =
  import.meta.env.DEV && String(import.meta.env.VITE_LOG_API_TIMINGS) === 'true';

// Request interceptor to add auth token
api.interceptors.request.use(
  (config) => {
    // Correlate client/server timing with a request id (also visible in Network tab).
    try {
      if (!config.headers['X-Request-Id'] && typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
        config.headers['X-Request-Id'] = (crypto as Crypto).randomUUID();
      }
    } catch {
      // best-effort
    }

    if (LOG_API_TIMINGS) {
      (config as TimedRequestConfig).__timingStart = performance.now();
    }

    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor to handle 401 errors and refresh tokens
api.interceptors.response.use(
  (response) => {
    if (LOG_API_TIMINGS) {
      const start = (response.config as TimedRequestConfig).__timingStart;
      if (typeof start === 'number') {
        const clientMs = Math.round(performance.now() - start);
        const serverMsRaw = response.headers?.['x-request-duration-ms'];
        const serverMs = serverMsRaw ? Number(serverMsRaw) : undefined;
        const method = (response.config.method || 'GET').toUpperCase();
        const url = response.config.url || '';
        const requestId = response.headers?.['x-request-id'] || response.config.headers?.['X-Request-Id'];

        console.log(
          `[api] ${method} ${url} -> ${response.status} | client=${clientMs}ms` +
            (Number.isFinite(serverMs) ? ` server=${serverMs}ms` : '') +
            (requestId ? ` id=${requestId}` : '')
        );
      }
    }
    return response;
  },
  async (error) => {
    const axiosError = error as AxiosError;
    const originalRequest = axiosError.config as TimedRequestConfig | undefined;

    if (LOG_API_TIMINGS && originalRequest) {
      const start = originalRequest.__timingStart;
      if (typeof start === 'number') {
        const clientMs = Math.round(performance.now() - start);
        const method = (originalRequest.method || 'GET').toUpperCase();
        const url = originalRequest.url || '';
        const status = axiosError.response?.status;
        const serverMsRaw = axiosError.response?.headers?.['x-request-duration-ms'];
        const serverMs = serverMsRaw ? Number(serverMsRaw) : undefined;
        const requestId =
          axiosError.response?.headers?.['x-request-id'] || originalRequest.headers?.['X-Request-Id'];

        console.log(
          `[api] ${method} ${url} -> ${status ?? 'ERR'} | client=${clientMs}ms` +
            (Number.isFinite(serverMs) ? ` server=${serverMs}ms` : '') +
            (requestId ? ` id=${requestId}` : '')
        );
      }
    }
    
    // Skip refresh for login/refresh endpoints to avoid infinite loops
    if (axiosError.response?.status === 401 && 
        originalRequest && 
        !originalRequest._retry &&
        !originalRequest.url?.includes('/auth/jwt/login') &&
        !originalRequest.url?.includes('/auth/jwt/refresh')) {
      const refreshToken = localStorage.getItem('refresh_token');
      
      if (refreshToken) {
        try {
          originalRequest._retry = true;
          // Import authApi dynamically to avoid circular dependency
          const { authApi } = await import('@/features/auth/api');
          const response = await authApi.refresh(refreshToken);
          
          localStorage.setItem('access_token', response.access_token);
          localStorage.setItem('refresh_token', response.refresh_token);
          
          // Retry original request with new token
          originalRequest.headers.Authorization = `Bearer ${response.access_token}`;
          return api(originalRequest);
        } catch (refreshError) {
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
          // Redirect to login or handle logout
          if (typeof window !== 'undefined') {
            window.location.href = '/login';
          }
          return Promise.reject(refreshError);
        }
      } else {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
      }
    }
    return Promise.reject(error);
  }
);

export default api;
