import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { dispatchAuthSessionExpired } from '@/features/auth/auth-events';
import { decodeJwtPayload } from '@/features/auth/utils/token';
import {
  captureAuthSessionState,
  invalidateAuthSession,
  isAuthSessionStateCurrent,
  StaleAuthSessionError,
  type AuthSessionStateSnapshot,
} from '@/features/auth/auth-session';

// Production should never call localhost from the deployed site.
// Prefer VITE_API_URL injected at build time; otherwise fall back to the known Azure backend FQDN.
const DEFAULT_PROD_API_URL = '';
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
  __authAccessToken?: string | null;
  __authRefreshToken?: string | null;
  __authSession?: AuthSessionStateSnapshot;
};

type RefreshTokens = { access_token: string; refresh_token: string };

type RefreshFlight = {
  sourceAccessToken: string | null;
  sourceRefreshToken: string;
  authSession: AuthSessionStateSnapshot;
  promise: Promise<RefreshTokens>;
};

// Concurrent 401s share a refresh only when they belong to the same token/session source.
let refreshingFlight: RefreshFlight | null = null;

const LOG_API_TIMINGS =
  import.meta.env.DEV && String(import.meta.env.VITE_LOG_API_TIMINGS) === 'true';

function isSameAuthSession(
  left: AuthSessionStateSnapshot,
  right: AuthSessionStateSnapshot,
): boolean {
  return left.generation === right.generation && left.userId === right.userId;
}

function isRefreshSourceCurrent(flight: RefreshFlight): boolean {
  return (
    isAuthSessionStateCurrent(flight.authSession) &&
    localStorage.getItem('access_token') === flight.sourceAccessToken &&
    localStorage.getItem('refresh_token') === flight.sourceRefreshToken
  );
}

function isRefreshResultCurrent(flight: RefreshFlight, tokens: RefreshTokens): boolean {
  return (
    isAuthSessionStateCurrent(flight.authSession) &&
    localStorage.getItem('access_token') === tokens.access_token &&
    localStorage.getItem('refresh_token') === tokens.refresh_token
  );
}

function getRefreshFlight(
  sourceAccessToken: string | null,
  sourceRefreshToken: string,
  authSession: AuthSessionStateSnapshot,
): RefreshFlight {
  if (
    refreshingFlight &&
    refreshingFlight.sourceAccessToken === sourceAccessToken &&
    refreshingFlight.sourceRefreshToken === sourceRefreshToken &&
    isSameAuthSession(refreshingFlight.authSession, authSession)
  ) {
    return refreshingFlight;
  }

  const flight: RefreshFlight = {
    sourceAccessToken,
    sourceRefreshToken,
    authSession,
    promise: Promise.resolve({ access_token: '', refresh_token: '' }),
  };
  flight.promise = import('@/features/auth/api')
    .then(({ authApi }) => authApi.refresh(sourceRefreshToken))
    .finally(() => {
      if (refreshingFlight === flight) {
        refreshingFlight = null;
      }
    });
  refreshingFlight = flight;
  return flight;
}

function expireCurrentSession(): void {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  invalidateAuthSession();
  dispatchAuthSessionExpired();
}

function getRequestAccessToken(config: TimedRequestConfig): string | null {
  const authorization = config.headers?.Authorization ?? config.headers?.authorization;
  if (typeof authorization !== 'string') {
    return null;
  }
  return authorization.match(/^Bearer\s+(.+)$/i)?.[1] ?? null;
}

function getAccessTokenUserId(token: string | null): number | null {
  if (!token) {
    return null;
  }
  const subject = decodeJwtPayload(token)?.sub;
  const userId = typeof subject === 'string' ? Number(subject) : Number.NaN;
  return Number.isSafeInteger(userId) && userId > 0 ? userId : null;
}

function isSameUserTokenRotation(
  authSession: AuthSessionStateSnapshot,
  requestAccessToken: string,
  currentAccessToken: string,
): boolean {
  const requestUserId = authSession.userId ?? getAccessTokenUserId(requestAccessToken);
  return requestUserId !== null && getAccessTokenUserId(currentAccessToken) === requestUserId;
}

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
    const timedConfig = config as TimedRequestConfig;
    timedConfig.__authAccessToken = token;
    timedConfig.__authRefreshToken = localStorage.getItem('refresh_token');
    timedConfig.__authSession = captureAuthSessionState();
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
      const requestAuthSession = originalRequest.__authSession;
      if (requestAuthSession && !isAuthSessionStateCurrent(requestAuthSession)) {
        return Promise.reject(new StaleAuthSessionError());
      }
      const requestAccessToken =
        originalRequest.__authAccessToken ?? getRequestAccessToken(originalRequest);
      const currentAccessToken = localStorage.getItem('access_token');
      if (requestAccessToken && requestAccessToken !== currentAccessToken) {
        if (
          requestAuthSession &&
          currentAccessToken &&
          isSameUserTokenRotation(
            requestAuthSession,
            requestAccessToken,
            currentAccessToken,
          )
        ) {
          originalRequest._retry = true;
          originalRequest.headers.Authorization = `Bearer ${currentAccessToken}`;
          return api(originalRequest);
        }
        return Promise.reject(new StaleAuthSessionError());
      }
      const refreshToken = localStorage.getItem('refresh_token');
      if (
        originalRequest.__authRefreshToken !== undefined &&
        originalRequest.__authRefreshToken !== refreshToken
      ) {
        return Promise.reject(new StaleAuthSessionError());
      }

      if (refreshToken) {
        originalRequest._retry = true;
        const sourceAccessToken = currentAccessToken;
        const authSession = requestAuthSession ?? captureAuthSessionState();
        const flight = getRefreshFlight(
          sourceAccessToken,
          refreshToken,
          authSession,
        );
        let tokens: RefreshTokens;
        try {
          tokens = await flight.promise;
        } catch (refreshError) {
          if (isRefreshSourceCurrent(flight)) {
            expireCurrentSession();
          }
          return Promise.reject(refreshError);
        }

        if (isRefreshSourceCurrent(flight)) {
          localStorage.setItem('access_token', tokens.access_token);
          localStorage.setItem('refresh_token', tokens.refresh_token);
        } else if (!isRefreshResultCurrent(flight, tokens)) {
          return Promise.reject(new StaleAuthSessionError());
        }

        // Retry only after verifying the refresh still belongs to this session.
        originalRequest.headers.Authorization = `Bearer ${tokens.access_token}`;
        return api(originalRequest);
      } else {
        expireCurrentSession();
      }
    }
    return Promise.reject(error);
  }
);

export default api;
