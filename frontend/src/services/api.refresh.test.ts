import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { LoginResponse } from '@/features/auth/types';

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

describe('api.ts refresh interceptor', () => {
  beforeEach(() => {
    // Some existing tests stub `localStorage` without implementing `.clear()`.
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    vi.clearAllMocks();
  });

  it('on 401 retries request once after refreshing token', async () => {
    localStorage.setItem('refresh_token', 'refresh-1');
    vi.mocked(authApi.refresh).mockResolvedValue({
      access_token: 'access-2',
      refresh_token: 'refresh-2',
      token_type: 'bearer',
    } satisfies LoginResponse);

    // Import after mocks; this registers interceptors on axiosInstance
    const apiModule = await import('@/services/api');
    const api = apiModule.default;

    // Grab the response error handler (2nd arg of interceptors.response.use)
    expect(axiosInstance.interceptors.response.use).toHaveBeenCalled();
    const [, onRejected] = axiosInstance.interceptors.response.use.mock.calls[0];

    const err = {
      response: { status: 401 },
      config: { url: '/courses/', method: 'get', headers: {} },
    };

    await onRejected(err);

    expect(authApi.refresh).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem('access_token')).toBe('access-2');
    expect(localStorage.getItem('refresh_token')).toBe('refresh-2');
    expect(api).toHaveBeenCalledTimes(1);
    expect(api).toHaveBeenCalledWith(expect.objectContaining({ url: '/courses/' }));
  });
});


