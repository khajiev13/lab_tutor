import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { LoginResponse } from '@/features/auth/types';
import {
  assertAuthSessionCurrent,
  captureAuthSession,
  establishAuthSession,
  invalidateAuthSession,
  resetAuthSessionForTests,
} from '@/features/auth/auth-session';

type AxiosInstanceLike = ((config: unknown) => Promise<unknown>) & {
  interceptors: {
    request: { use: ReturnType<typeof vi.fn> };
    response: { use: ReturnType<typeof vi.fn> };
  };
};

// Build a callable axios instance mock (function with properties)
function makeAxiosInstance(): AxiosInstanceLike {
  const fn = vi.fn(() => Promise.resolve({ data: { ok: true } })) as unknown as AxiosInstanceLike;
  fn.interceptors = {
    request: { use: vi.fn() },
    response: { use: vi.fn() },
  };
  return fn;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function tokenFor(userId: number, version: string): string {
  const header = btoa(JSON.stringify({ alg: 'none', typ: 'JWT' }));
  const payload = btoa(
    JSON.stringify({
      sub: String(userId),
      exp: Math.floor(Date.now() / 1000) + 3_600,
      version,
    }),
  );
  return `${header}.${payload}.signature`;
}

const axiosInstance = makeAxiosInstance();

vi.mock('axios', () => {
  return {
    default: {
      create: vi.fn(() => axiosInstance),
    },
  };
});

vi.mock('@/features/auth/api', () => {
  return {
    authApi: {
      refresh: vi.fn(),
    },
  };
});

import { authApi } from '@/features/auth/api';

type ResponseErrorHandler = (error: unknown) => Promise<unknown>;
type RequestHandler = (config: Record<string, unknown>) => Record<string, unknown>;

let responseErrorHandler: ResponseErrorHandler | null = null;
let requestHandler: RequestHandler | null = null;

async function getResponseErrorHandler(): Promise<ResponseErrorHandler> {
  if (responseErrorHandler) {
    return responseErrorHandler;
  }

  await import('@/services/api');
  const [onRequest] = axiosInstance.interceptors.request.use.mock.calls[0];
  const [, onRejected] = axiosInstance.interceptors.response.use.mock.calls[0];
  if (typeof onRequest !== 'function' || typeof onRejected !== 'function') {
    throw new Error('The API auth interceptors were not registered.');
  }
  requestHandler = onRequest as RequestHandler;
  responseErrorHandler = onRejected as ResponseErrorHandler;
  return responseErrorHandler;
}

async function getRequestHandler(): Promise<RequestHandler> {
  await getResponseErrorHandler();
  if (!requestHandler) {
    throw new Error('The API request interceptor was not registered.');
  }
  return requestHandler;
}

describe('api.ts refresh interceptor', () => {
  beforeEach(() => {
    // Some existing tests stub `localStorage` without implementing `.clear()`.
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    resetAuthSessionForTests();
    vi.clearAllMocks();
  });

  it('keeps an in-flight request current across a same-user 401 refresh retry', async () => {
    establishAuthSession(7);
    const sessionBeforeTokenRotation = captureAuthSession(7);
    localStorage.setItem('refresh_token', 'refresh-1');
    vi.mocked(authApi.refresh).mockResolvedValue({
      access_token: 'access-2',
      refresh_token: 'refresh-2',
      token_type: 'bearer',
    } satisfies LoginResponse);

    const onRejected = await getResponseErrorHandler();

    const err = {
      response: { status: 401 },
      config: { url: '/courses/', method: 'get', headers: {} },
    };

    await onRejected(err);

    expect(authApi.refresh).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem('access_token')).toBe('access-2');
    expect(localStorage.getItem('refresh_token')).toBe('refresh-2');
    expect(axiosInstance).toHaveBeenCalledTimes(1);
    expect(axiosInstance).toHaveBeenCalledWith(expect.objectContaining({ url: '/courses/' }));
    expect(() => assertAuthSessionCurrent(sessionBeforeTokenRotation)).not.toThrow();
  });

  it('shares one refresh flight across concurrent 401s from the same session', async () => {
    establishAuthSession(7);
    localStorage.setItem('access_token', 'access-1');
    localStorage.setItem('refresh_token', 'refresh-1');
    const refresh = deferred<LoginResponse>();
    vi.mocked(authApi.refresh).mockReturnValue(refresh.promise);
    const onRejected = await getResponseErrorHandler();

    const firstRequest = onRejected({
      response: { status: 401 },
      config: { url: '/courses/1', method: 'get', headers: {} },
    });
    const secondRequest = onRejected({
      response: { status: 401 },
      config: { url: '/courses/2', method: 'get', headers: {} },
    });
    await vi.waitFor(() => expect(authApi.refresh).toHaveBeenCalled());

    expect(authApi.refresh).toHaveBeenCalledTimes(1);
    refresh.resolve({
      access_token: 'access-2',
      refresh_token: 'refresh-2',
      token_type: 'bearer',
    });
    await Promise.all([firstRequest, secondRequest]);

    expect(axiosInstance).toHaveBeenCalledTimes(2);
  });

  it('does not let a delayed refresh from account A overwrite account B', async () => {
    establishAuthSession(7);
    localStorage.setItem('access_token', 'access-a');
    localStorage.setItem('refresh_token', 'refresh-a');
    const refreshA = deferred<LoginResponse>();
    vi.mocked(authApi.refresh).mockReturnValueOnce(refreshA.promise);
    const onRejected = await getResponseErrorHandler();

    const requestA = onRejected({
      response: { status: 401 },
      config: { url: '/individual/profile', method: 'get', headers: {} },
    });
    await vi.waitFor(() => expect(authApi.refresh).toHaveBeenCalledWith('refresh-a'));

    invalidateAuthSession();
    establishAuthSession(8);
    localStorage.setItem('access_token', 'access-b');
    localStorage.setItem('refresh_token', 'refresh-b');
    refreshA.resolve({
      access_token: 'access-a-rotated',
      refresh_token: 'refresh-a-rotated',
      token_type: 'bearer',
    });
    await requestA.catch(() => undefined);

    expect(localStorage.getItem('access_token')).toBe('access-b');
    expect(localStorage.getItem('refresh_token')).toBe('refresh-b');
    expect(axiosInstance).not.toHaveBeenCalled();
  });

  it('starts a separate refresh for account B instead of awaiting account A', async () => {
    establishAuthSession(7);
    localStorage.setItem('access_token', 'access-a');
    localStorage.setItem('refresh_token', 'refresh-a');
    const refreshA = deferred<LoginResponse>();
    const refreshB = deferred<LoginResponse>();
    vi.mocked(authApi.refresh)
      .mockReturnValueOnce(refreshA.promise)
      .mockReturnValueOnce(refreshB.promise);
    const onRejected = await getResponseErrorHandler();

    const requestA = onRejected({
      response: { status: 401 },
      config: { url: '/individual/profile', method: 'get', headers: {} },
    });
    await vi.waitFor(() => expect(authApi.refresh).toHaveBeenCalledTimes(1));

    invalidateAuthSession();
    establishAuthSession(8);
    localStorage.setItem('access_token', 'access-b');
    localStorage.setItem('refresh_token', 'refresh-b');
    const requestB = onRejected({
      response: { status: 401 },
      config: { url: '/individual/jobs', method: 'get', headers: {} },
    });

    await vi.waitFor(() => expect(authApi.refresh).toHaveBeenCalledTimes(2));
    expect(authApi.refresh).toHaveBeenNthCalledWith(2, 'refresh-b');

    refreshB.resolve({
      access_token: 'access-b-rotated',
      refresh_token: 'refresh-b-rotated',
      token_type: 'bearer',
    });
    await requestB;
    refreshA.resolve({
      access_token: 'access-a-rotated',
      refresh_token: 'refresh-a-rotated',
      token_type: 'bearer',
    });
    await requestA.catch(() => undefined);

    expect(localStorage.getItem('access_token')).toBe('access-b-rotated');
    expect(localStorage.getItem('refresh_token')).toBe('refresh-b-rotated');
  });

  it('does not clear account B when account A refresh fails late', async () => {
    establishAuthSession(7);
    localStorage.setItem('access_token', 'access-a');
    localStorage.setItem('refresh_token', 'refresh-a');
    const refreshA = deferred<LoginResponse>();
    vi.mocked(authApi.refresh).mockReturnValueOnce(refreshA.promise);
    const onRejected = await getResponseErrorHandler();
    const requestA = onRejected({
      response: { status: 401 },
      config: { url: '/individual/profile', method: 'get', headers: {} },
    });
    await vi.waitFor(() => expect(authApi.refresh).toHaveBeenCalledTimes(1));

    invalidateAuthSession();
    establishAuthSession(8);
    localStorage.setItem('access_token', 'access-b');
    localStorage.setItem('refresh_token', 'refresh-b');
    refreshA.reject(new Error('account A refresh failed'));
    await requestA.catch(() => undefined);

    expect(localStorage.getItem('access_token')).toBe('access-b');
    expect(localStorage.getItem('refresh_token')).toBe('refresh-b');
  });

  it('does not expire account B for a late 401 response sent with account A credentials', async () => {
    establishAuthSession(7);
    localStorage.setItem('access_token', 'access-a');
    localStorage.setItem('refresh_token', 'refresh-a');
    const onRequest = await getRequestHandler();
    const requestA = onRequest({
      url: '/individual/profile',
      method: 'get',
      headers: {},
    });

    invalidateAuthSession();
    establishAuthSession(8);
    localStorage.setItem('access_token', 'access-b');
    localStorage.removeItem('refresh_token');
    const expiredListener = vi.fn();
    window.addEventListener('auth:session-expired', expiredListener);
    const onRejected = await getResponseErrorHandler();

    await onRejected({
      response: { status: 401 },
      config: requestA,
    }).catch(() => undefined);

    expect(localStorage.getItem('access_token')).toBe('access-b');
    expect(authApi.refresh).not.toHaveBeenCalled();
    expect(axiosInstance).not.toHaveBeenCalled();
    expect(expiredListener).not.toHaveBeenCalled();
    window.removeEventListener('auth:session-expired', expiredListener);
  });

  it('retries a late same-user 401 with the token another refresh already rotated', async () => {
    establishAuthSession(7);
    const access1 = tokenFor(7, 'access-1');
    const access2 = tokenFor(7, 'access-2');
    localStorage.setItem('access_token', access1);
    localStorage.setItem('refresh_token', 'refresh-1');
    const onRequest = await getRequestHandler();
    const originalRequest = onRequest({
      url: '/individual/profile',
      method: 'get',
      headers: {},
    });

    localStorage.setItem('access_token', access2);
    localStorage.setItem('refresh_token', 'refresh-2');
    const onRejected = await getResponseErrorHandler();
    await onRejected({ response: { status: 401 }, config: originalRequest });

    expect(authApi.refresh).not.toHaveBeenCalled();
    expect(axiosInstance).toHaveBeenCalledWith(
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: `Bearer ${access2}` }),
      }),
    );
    expect(localStorage.getItem('access_token')).toBe(access2);
    expect(localStorage.getItem('refresh_token')).toBe('refresh-2');
  });

  it('rejects a cross-account token change even before the storage event updates generation', async () => {
    establishAuthSession(7);
    const accessA = tokenFor(7, 'account-a');
    const accessB = tokenFor(8, 'account-b');
    localStorage.setItem('access_token', accessA);
    localStorage.setItem('refresh_token', 'refresh-a');
    const onRequest = await getRequestHandler();
    const requestA = onRequest({
      url: '/individual/profile',
      method: 'get',
      headers: {},
    });

    // localStorage changes before this tab's storage event handler has invalidated generation.
    localStorage.setItem('access_token', accessB);
    localStorage.setItem('refresh_token', 'refresh-b');
    const onRejected = await getResponseErrorHandler();
    await onRejected({ response: { status: 401 }, config: requestA }).catch(() => undefined);

    expect(authApi.refresh).not.toHaveBeenCalled();
    expect(axiosInstance).not.toHaveBeenCalled();
    expect(localStorage.getItem('access_token')).toBe(accessB);
    expect(localStorage.getItem('refresh_token')).toBe('refresh-b');
  });

  it('does not refresh with a token that changed after the original request left', async () => {
    establishAuthSession(7);
    const accessToken = tokenFor(7, 'stable-access');
    localStorage.setItem('access_token', accessToken);
    localStorage.setItem('refresh_token', 'refresh-1');
    const onRequest = await getRequestHandler();
    const originalRequest = onRequest({
      url: '/individual/profile',
      method: 'get',
      headers: {},
    });

    localStorage.setItem('refresh_token', 'refresh-2');
    const onRejected = await getResponseErrorHandler();
    await onRejected({ response: { status: 401 }, config: originalRequest }).catch(
      () => undefined,
    );

    expect(authApi.refresh).not.toHaveBeenCalled();
    expect(axiosInstance).not.toHaveBeenCalled();
    expect(localStorage.getItem('access_token')).toBe(accessToken);
    expect(localStorage.getItem('refresh_token')).toBe('refresh-2');
  });

  it('notifies the current tab when a 401 has no refresh token', async () => {
    establishAuthSession(7);
    localStorage.setItem('access_token', 'access-a');
    const expiredListener = vi.fn();
    window.addEventListener('auth:session-expired', expiredListener);
    const onRejected = await getResponseErrorHandler();

    await onRejected({
      response: { status: 401 },
      config: { url: '/individual/profile', method: 'get', headers: {} },
    }).catch(() => undefined);

    expect(expiredListener).toHaveBeenCalledTimes(1);
    window.removeEventListener('auth:session-expired', expiredListener);
  });
});
