import axios from 'axios';

// Production should never call localhost from the deployed site.
// Prefer VITE_API_URL injected at build time; otherwise fall back to the known Azure backend FQDN.
const DEFAULT_PROD_API_URL = 'https://backend.mangoocean-d0c97d4f.westus2.azurecontainerapps.io';
const API_URL =
  import.meta.env.VITE_API_URL ||
  (import.meta.env.PROD ? DEFAULT_PROD_API_URL : 'http://localhost:8000');

const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor to add auth token
api.interceptors.request.use(
  (config) => {
    // #region agent log
    fetch('http://127.0.0.1:7242/ingest/22646e48-28ee-4f69-a8db-ceec81e08aac',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'api.ts:20',message:'Request interceptor - before token check',data:{url:config.url,method:config.method},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'H'})}).catch(()=>{});
    // #endregion
    const token = localStorage.getItem('access_token');
    // #region agent log
    fetch('http://127.0.0.1:7242/ingest/22646e48-28ee-4f69-a8db-ceec81e08aac',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'api.ts:23',message:'Request interceptor - token check result',data:{url:config.url,method:config.method,hasToken:!!token},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'H'})}).catch(()=>{});
    // #endregion
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor to handle 401 errors and refresh tokens
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    // #region agent log
    fetch('http://127.0.0.1:7242/ingest/22646e48-28ee-4f69-a8db-ceec81e08aac',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'api.ts:35',message:'Response interceptor - error caught',data:{status:error.response?.status,url:error.config?.url,method:error.config?.method},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'G'})}).catch(()=>{});
    // #endregion
    const originalRequest = error.config;
    
    // Skip refresh for login/refresh endpoints to avoid infinite loops
    if (error.response?.status === 401 && 
        originalRequest && 
        !originalRequest._retry &&
        !originalRequest.url?.includes('/auth/jwt/login') &&
        !originalRequest.url?.includes('/auth/jwt/refresh')) {
      // #region agent log
      const refreshToken = localStorage.getItem('refresh_token');
      fetch('http://127.0.0.1:7242/ingest/22646e48-28ee-4f69-a8db-ceec81e08aac',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'api.ts:42',message:'401 Unauthorized detected, attempting refresh',data:{url:originalRequest.url,hasRefreshToken:!!refreshToken},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'G'})}).catch(()=>{});
      // #endregion
      
      if (refreshToken) {
        try {
          originalRequest._retry = true;
          // Import authApi dynamically to avoid circular dependency
          const { authApi } = await import('@/features/auth/api');
          const response = await authApi.refresh(refreshToken);
          
          // #region agent log
          fetch('http://127.0.0.1:7242/ingest/22646e48-28ee-4f69-a8db-ceec81e08aac',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'api.ts:51',message:'Token refresh successful',data:{hasNewAccessToken:!!response.access_token,hasNewRefreshToken:!!response.refresh_token},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'G'})}).catch(()=>{});
          // #endregion
          
          localStorage.setItem('access_token', response.access_token);
          localStorage.setItem('refresh_token', response.refresh_token);
          
          // Retry original request with new token
          originalRequest.headers.Authorization = `Bearer ${response.access_token}`;
          return api(originalRequest);
        } catch (refreshError) {
          // #region agent log
          fetch('http://127.0.0.1:7242/ingest/22646e48-28ee-4f69-a8db-ceec81e08aac',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'api.ts:60',message:'Token refresh failed',data:{error:refreshError instanceof Error ? refreshError.message : 'Unknown'},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'G'})}).catch(()=>{});
          // #endregion
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
          // Redirect to login or handle logout
          if (typeof window !== 'undefined') {
            window.location.href = '/login';
          }
          return Promise.reject(refreshError);
        }
      } else {
        // #region agent log
        fetch('http://127.0.0.1:7242/ingest/22646e48-28ee-4f69-a8db-ceec81e08aac',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'api.ts:69',message:'No refresh token available',data:{url:originalRequest.url},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'G'})}).catch(()=>{});
        // #endregion
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
      }
    }
    return Promise.reject(error);
  }
);

export default api;
