import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, render, waitFor } from '@testing-library/react';
import { AuthProvider, useAuth } from './AuthContext';
import type { LoginResponse, UserResponse } from '../types';
import {
  assertAuthSessionCurrent,
  captureAuthSession,
  captureAuthSessionState,
  isAuthSessionStateCurrent,
  resetAuthSessionForTests,
} from '@/features/auth/auth-session';

vi.mock('../api', () => {
  return {
    authApi: {
      login: vi.fn(),
      getMe: vi.fn(),
      register: vi.fn(),
      refresh: vi.fn(),
    },
  };
});

// Import after mock
import { authApi } from '../api';

function Harness({ onReady }: { onReady: (ctx: ReturnType<typeof useAuth>) => void }) {
  const ctx = useAuth();
  React.useEffect(() => {
    onReady(ctx);
  }, [ctx, onReady]);
  return null;
}

function tokenFor(userId: number): string {
  const header = btoa(JSON.stringify({ alg: 'none', typ: 'JWT' }));
  const payload = btoa(
    JSON.stringify({ sub: String(userId), exp: Math.floor(Date.now() / 1000) + 3_600 }),
  );
  return `${header}.${payload}.signature`;
}

function expiredTokenFor(userId: number): string {
  const header = btoa(JSON.stringify({ alg: 'none', typ: 'JWT' }));
  const payload = btoa(
    JSON.stringify({ sub: String(userId), exp: Math.floor(Date.now() / 1000) - 60 }),
  );
  return `${header}.${payload}.signature`;
}

function userFor(id: number, role: UserResponse['role'] = 'individual'): UserResponse {
  return {
    id,
    first_name: 'Test',
    last_name: `User ${id}`,
    email: `user-${id}@example.com`,
    role,
    created_at: new Date().toISOString(),
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolver, rejectPromise) => {
    resolve = resolver;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

describe('AuthContext', () => {
  beforeEach(() => {
    // Some existing tests stub `localStorage` without implementing `.clear()`.
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    sessionStorage.removeItem('individual-learning.graph-session');
    resetAuthSessionForTests();
    vi.resetAllMocks();
  });

  it('login stores access_token + refresh_token and fetches /users/me', async () => {
    vi.mocked(authApi.login).mockResolvedValue({
      access_token: 'access-1',
      refresh_token: 'refresh-1',
      token_type: 'bearer',
    } satisfies LoginResponse);
    vi.mocked(authApi.getMe).mockResolvedValue({
      id: 123,
      first_name: 'Test',
      last_name: 'User',
      email: 'test@example.com',
      role: 'student',
      created_at: new Date().toISOString(),
    } satisfies UserResponse);

    let ctx: ReturnType<typeof useAuth> | undefined;
    render(
      <AuthProvider>
        <Harness onReady={(c) => { ctx = c; }} />
      </AuthProvider>
    );

    await act(async () => {
      await ctx!.login({ email: 'test@example.com', password: 'pw' });
    });

    await waitFor(() => {
      expect(localStorage.getItem('access_token')).toBe('access-1');
      expect(localStorage.getItem('refresh_token')).toBe('refresh-1');
      expect(authApi.getMe).toHaveBeenCalledTimes(1);
    });
  });

  it('logout clears both tokens', async () => {
    localStorage.setItem('access_token', 'access-1');
    localStorage.setItem('refresh_token', 'refresh-1');
    sessionStorage.setItem(
      'individual-learning.graph-session',
      JSON.stringify({ ownerUserId: 7, threadId: 'individual-7-cv-42' }),
    );

    let ctx: ReturnType<typeof useAuth> | undefined;
    render(
      <AuthProvider>
        <Harness onReady={(c) => { ctx = c; }} />
      </AuthProvider>
    );

    act(() => {
      ctx!.logout();
    });

    expect(localStorage.getItem('access_token')).toBeNull();
    expect(localStorage.getItem('refresh_token')).toBeNull();
    expect(sessionStorage.getItem('individual-learning.graph-session')).toBeNull();
  });

  it('clears individual graph data when a different user logs in', async () => {
    sessionStorage.setItem(
      'individual-learning.graph-session',
      JSON.stringify({
        ownerUserId: 7,
        threadId: 'individual-7-cv-42',
        graphStatus: 'interrupted',
        reviewInterrupt: {
          kind: 'review_profile_and_roles',
          profile: { summary: 'Private CV summary' },
          target_title_suggestions: [],
        },
        targetTitles: [],
        selectedPostingUrls: [],
        selectedSkillNames: [],
      }),
    );
    vi.mocked(authApi.login).mockResolvedValue({
      access_token: 'access-2',
      refresh_token: 'refresh-2',
      token_type: 'bearer',
    });
    vi.mocked(authApi.getMe).mockResolvedValue({
      id: 123,
      first_name: 'Second',
      last_name: 'User',
      email: 'second@example.com',
      role: 'individual',
      created_at: new Date().toISOString(),
    });

    let ctx: ReturnType<typeof useAuth> | undefined;
    render(
      <AuthProvider>
        <Harness onReady={(value) => { ctx = value; }} />
      </AuthProvider>,
    );

    await act(async () => {
      await ctx!.login({ email: 'second@example.com', password: 'pw' });
    });

    expect(sessionStorage.getItem('individual-learning.graph-session')).toBeNull();
  });

  it('preserves valid tokens and individual drafts when /users/me has a transient failure', async () => {
    const accessToken = tokenFor(7);
    localStorage.setItem('access_token', accessToken);
    localStorage.setItem('refresh_token', tokenFor(7));
    const draft = JSON.stringify({
      ownerUserId: 7,
      threadId: 'thread-7',
      graphStatus: 'interrupted',
      targetTitles: ['Data Analyst'],
      selectedPostingUrls: [],
      selectedSkillNames: ['SQL'],
    });
    sessionStorage.setItem('individual-learning.graph-session', draft);
    vi.mocked(authApi.getMe).mockRejectedValue({ response: { status: 503 } });

    let ctx: ReturnType<typeof useAuth> | undefined;
    render(
      <AuthProvider>
        <Harness onReady={(value) => { ctx = value; }} />
      </AuthProvider>,
    );

    await waitFor(() => expect(ctx?.isLoading).toBe(false));
    expect(localStorage.getItem('access_token')).toBe(accessToken);
    expect(localStorage.getItem('refresh_token')).toBeTruthy();
    expect(sessionStorage.getItem('individual-learning.graph-session')).toBe(draft);
    expect(ctx?.sessionError).toMatch(/could not verify/i);

    vi.mocked(authApi.getMe).mockResolvedValue(userFor(7));
    await act(async () => {
      await ctx!.retrySession();
    });

    expect(ctx?.user?.id).toBe(7);
    expect(ctx?.sessionError).toBeNull();
    expect(sessionStorage.getItem('individual-learning.graph-session')).toBe(draft);
  });

  it.each([401, 403])('clears credentials and drafts when /users/me returns %s', async (status) => {
    localStorage.setItem('access_token', tokenFor(7));
    localStorage.setItem('refresh_token', tokenFor(7));
    sessionStorage.setItem(
      'individual-learning.graph-session',
      JSON.stringify({ ownerUserId: 7, threadId: 'thread-7' }),
    );
    vi.mocked(authApi.getMe).mockRejectedValue({ response: { status } });

    let ctx: ReturnType<typeof useAuth> | undefined;
    render(
      <AuthProvider>
        <Harness onReady={(value) => { ctx = value; }} />
      </AuthProvider>,
    );

    await waitFor(() => expect(ctx?.isLoading).toBe(false));
    expect(localStorage.getItem('access_token')).toBeNull();
    expect(localStorage.getItem('refresh_token')).toBeNull();
    expect(sessionStorage.getItem('individual-learning.graph-session')).toBeNull();
  });

  it('synchronizes an access-token account switch across tabs and invalidates old work', async () => {
    const tokenA = tokenFor(7);
    const tokenB = tokenFor(8);
    localStorage.setItem('access_token', tokenA);
    localStorage.setItem('refresh_token', tokenA);
    sessionStorage.setItem(
      'individual-learning.graph-session',
      JSON.stringify({
        ownerUserId: 7,
        threadId: 'thread-7',
        graphStatus: 'interrupted',
        targetTitles: [],
        selectedPostingUrls: [],
        selectedSkillNames: ['Private skill'],
      }),
    );
    vi.mocked(authApi.getMe)
      .mockResolvedValueOnce(userFor(7))
      .mockResolvedValueOnce(userFor(8));

    let ctx: ReturnType<typeof useAuth> | undefined;
    render(
      <AuthProvider>
        <Harness onReady={(value) => { ctx = value; }} />
      </AuthProvider>,
    );
    await waitFor(() => expect(ctx?.user?.id).toBe(7));
    const oldSession = captureAuthSession(7);

    localStorage.setItem('access_token', tokenB);
    localStorage.setItem('refresh_token', tokenB);
    act(() => {
      window.dispatchEvent(
        new StorageEvent('storage', {
          key: 'access_token',
          oldValue: tokenA,
          newValue: tokenB,
        }),
      );
    });

    await waitFor(() => expect(ctx?.user?.id).toBe(8));
    expect(() => assertAuthSessionCurrent(oldSession)).toThrow(/authenticated session changed/i);
    expect(sessionStorage.getItem('individual-learning.graph-session')).toBeNull();
  });

  it('preserves same-user drafts and in-flight auth generation on cross-tab token rotation', async () => {
    const tokenA = tokenFor(7);
    const tokenARotated = `${tokenFor(7)}-rotated`;
    localStorage.setItem('access_token', tokenA);
    localStorage.setItem('refresh_token', tokenA);
    const draft = JSON.stringify({
      ownerUserId: 7,
      threadId: 'thread-7',
      graphStatus: 'interrupted',
      targetTitles: ['Data Analyst'],
      selectedPostingUrls: [],
      selectedSkillNames: ['Private skill'],
    });
    sessionStorage.setItem('individual-learning.graph-session', draft);
    vi.mocked(authApi.getMe).mockResolvedValue(userFor(7));

    let ctx: ReturnType<typeof useAuth> | undefined;
    render(
      <AuthProvider>
        <Harness onReady={(value) => { ctx = value; }} />
      </AuthProvider>,
    );
    await waitFor(() => expect(ctx?.user?.id).toBe(7));
    const sessionBeforeRotation = captureAuthSession(7);

    localStorage.setItem('access_token', tokenARotated);
    act(() => {
      window.dispatchEvent(
        new StorageEvent('storage', {
          key: 'access_token',
          oldValue: tokenA,
          newValue: tokenARotated,
        }),
      );
    });

    expect(ctx?.user?.id).toBe(7);
    expect(authApi.getMe).toHaveBeenCalledTimes(1);
    expect(sessionStorage.getItem('individual-learning.graph-session')).toBe(draft);
    expect(() => assertAuthSessionCurrent(sessionBeforeRotation)).not.toThrow();
  });

  it('recognizes same-user cross-tab rotation before /users/me establishes identity', async () => {
    const tokenA = tokenFor(7);
    const tokenARotated = `${tokenFor(7)}-rotated`;
    localStorage.setItem('access_token', tokenA);
    localStorage.setItem('refresh_token', tokenA);
    const draft = JSON.stringify({
      ownerUserId: 7,
      threadId: 'thread-7',
      graphStatus: 'interrupted',
      targetTitles: ['Data Analyst'],
      selectedPostingUrls: [],
      selectedSkillNames: ['Private skill'],
    });
    sessionStorage.setItem('individual-learning.graph-session', draft);
    const getMeRequest = deferred<UserResponse>();
    vi.mocked(authApi.getMe).mockReturnValue(getMeRequest.promise);

    let ctx: ReturnType<typeof useAuth> | undefined;
    render(
      <AuthProvider>
        <Harness onReady={(value) => { ctx = value; }} />
      </AuthProvider>,
    );
    await waitFor(() => expect(authApi.getMe).toHaveBeenCalledTimes(1));
    const stateBeforeRotation = captureAuthSessionState();

    localStorage.setItem('access_token', tokenARotated);
    act(() => {
      window.dispatchEvent(
        new StorageEvent('storage', {
          key: 'access_token',
          oldValue: tokenA,
          newValue: tokenARotated,
        }),
      );
    });

    expect(isAuthSessionStateCurrent(stateBeforeRotation)).toBe(true);
    expect(sessionStorage.getItem('individual-learning.graph-session')).toBe(draft);
    expect(authApi.getMe).toHaveBeenCalledTimes(1);

    await act(async () => {
      getMeRequest.resolve(userFor(7));
      await getMeRequest.promise;
    });
    expect(ctx?.user?.id).toBe(7);
  });

  it('does not mistake another account rotating its own token for the current user', async () => {
    const token8 = tokenFor(8);
    const oldToken7 = tokenFor(7);
    const rotatedToken7 = `${tokenFor(7)}-rotated`;
    localStorage.setItem('access_token', token8);
    localStorage.setItem('refresh_token', token8);
    const draft = JSON.stringify({
      ownerUserId: 8,
      threadId: 'thread-8',
      graphStatus: 'interrupted',
      targetTitles: ['Private role'],
      selectedPostingUrls: [],
      selectedSkillNames: [],
    });
    sessionStorage.setItem('individual-learning.graph-session', draft);
    vi.mocked(authApi.getMe)
      .mockResolvedValueOnce(userFor(8))
      .mockResolvedValueOnce(userFor(7));

    let ctx: ReturnType<typeof useAuth> | undefined;
    render(
      <AuthProvider>
        <Harness onReady={(value) => { ctx = value; }} />
      </AuthProvider>,
    );
    await waitFor(() => expect(ctx?.user?.id).toBe(8));
    const account8Session = captureAuthSession(8);

    localStorage.setItem('access_token', rotatedToken7);
    localStorage.setItem('refresh_token', rotatedToken7);
    act(() => {
      window.dispatchEvent(
        new StorageEvent('storage', {
          key: 'access_token',
          oldValue: oldToken7,
          newValue: rotatedToken7,
        }),
      );
    });

    await waitFor(() => expect(ctx?.user?.id).toBe(7));
    expect(() => assertAuthSessionCurrent(account8Session)).toThrow(/session changed/i);
    expect(sessionStorage.getItem('individual-learning.graph-session')).toBeNull();
  });

  it('does not let a delayed restore refresh overwrite a newly logged-in account', async () => {
    localStorage.setItem('access_token', expiredTokenFor(7));
    localStorage.setItem('refresh_token', tokenFor(7));
    const refreshA = deferred<LoginResponse>();
    vi.mocked(authApi.refresh).mockReturnValue(refreshA.promise);
    vi.mocked(authApi.login).mockResolvedValue({
      access_token: 'access-b',
      refresh_token: 'refresh-b',
      token_type: 'bearer',
    });
    vi.mocked(authApi.getMe).mockResolvedValue(userFor(8));

    let ctx: ReturnType<typeof useAuth> | undefined;
    render(
      <AuthProvider>
        <Harness onReady={(value) => { ctx = value; }} />
      </AuthProvider>,
    );
    await waitFor(() => expect(authApi.refresh).toHaveBeenCalledTimes(1));

    await act(async () => {
      await ctx!.login({ email: 'user-8@example.com', password: 'pw' });
    });
    expect(ctx?.user?.id).toBe(8);

    await act(async () => {
      refreshA.resolve({
        access_token: 'access-a-rotated',
        refresh_token: 'refresh-a-rotated',
        token_type: 'bearer',
      });
      await refreshA.promise;
    });

    expect(localStorage.getItem('access_token')).toBe('access-b');
    expect(localStorage.getItem('refresh_token')).toBe('refresh-b');
    expect(ctx?.user?.id).toBe(8);
  });

  it('does not clear a newly logged-in account when an older restore refresh fails late', async () => {
    localStorage.setItem('access_token', expiredTokenFor(7));
    localStorage.setItem('refresh_token', tokenFor(7));
    const refreshA = deferred<LoginResponse>();
    vi.mocked(authApi.refresh).mockReturnValue(refreshA.promise);
    vi.mocked(authApi.login).mockResolvedValue({
      access_token: 'access-b',
      refresh_token: 'refresh-b',
      token_type: 'bearer',
    });
    vi.mocked(authApi.getMe).mockResolvedValue(userFor(8));

    let ctx: ReturnType<typeof useAuth> | undefined;
    render(
      <AuthProvider>
        <Harness onReady={(value) => { ctx = value; }} />
      </AuthProvider>,
    );
    await waitFor(() => expect(authApi.refresh).toHaveBeenCalledTimes(1));

    await act(async () => {
      await ctx!.login({ email: 'user-8@example.com', password: 'pw' });
    });
    await act(async () => {
      refreshA.reject({ response: { status: 401 } });
      await refreshA.promise.catch(() => undefined);
    });

    expect(localStorage.getItem('access_token')).toBe('access-b');
    expect(localStorage.getItem('refresh_token')).toBe('refresh-b');
    expect(ctx?.user?.id).toBe(8);
  });

  it('does not clear a newly logged-in account when an older /users/me fails late', async () => {
    const tokenA = tokenFor(7);
    localStorage.setItem('access_token', tokenA);
    localStorage.setItem('refresh_token', tokenA);
    const userARequest = deferred<UserResponse>();
    vi.mocked(authApi.getMe)
      .mockReturnValueOnce(userARequest.promise)
      .mockResolvedValueOnce(userFor(8));
    vi.mocked(authApi.login).mockResolvedValue({
      access_token: 'access-b',
      refresh_token: 'refresh-b',
      token_type: 'bearer',
    });

    let ctx: ReturnType<typeof useAuth> | undefined;
    render(
      <AuthProvider>
        <Harness onReady={(value) => { ctx = value; }} />
      </AuthProvider>,
    );
    await waitFor(() => expect(authApi.getMe).toHaveBeenCalledTimes(1));

    await act(async () => {
      await ctx!.login({ email: 'user-8@example.com', password: 'pw' });
    });
    expect(ctx?.user?.id).toBe(8);

    await act(async () => {
      userARequest.reject({ response: { status: 401 } });
      await userARequest.promise.catch(() => undefined);
    });

    expect(localStorage.getItem('access_token')).toBe('access-b');
    expect(localStorage.getItem('refresh_token')).toBe('refresh-b');
    expect(ctx?.user?.id).toBe(8);
  });

  it('clears React auth state promptly when the same-tab API session expires', async () => {
    const accessToken = tokenFor(7);
    localStorage.setItem('access_token', accessToken);
    localStorage.setItem('refresh_token', tokenFor(7));
    sessionStorage.setItem(
      'individual-learning.graph-session',
      JSON.stringify({ ownerUserId: 7, threadId: 'thread-7' }),
    );
    vi.mocked(authApi.getMe).mockResolvedValue(userFor(7));

    let ctx: ReturnType<typeof useAuth> | undefined;
    render(
      <AuthProvider>
        <Harness onReady={(value) => { ctx = value; }} />
      </AuthProvider>,
    );
    await waitFor(() => expect(ctx?.user?.id).toBe(7));

    act(() => {
      window.dispatchEvent(new Event('auth:session-expired'));
    });

    await waitFor(() => expect(ctx?.user).toBeNull());
    expect(ctx?.isAuthenticated).toBe(false);
    expect(sessionStorage.getItem('individual-learning.graph-session')).toBeNull();
  });

  it('ignores an older /users/me response after a cross-tab account switch', async () => {
    const tokenA = tokenFor(7);
    const tokenB = tokenFor(8);
    localStorage.setItem('access_token', tokenA);
    localStorage.setItem('refresh_token', tokenA);
    const firstUser = deferred<UserResponse>();
    vi.mocked(authApi.getMe)
      .mockReturnValueOnce(firstUser.promise)
      .mockResolvedValueOnce(userFor(8));

    let ctx: ReturnType<typeof useAuth> | undefined;
    render(
      <AuthProvider>
        <Harness onReady={(value) => { ctx = value; }} />
      </AuthProvider>,
    );
    await waitFor(() => expect(authApi.getMe).toHaveBeenCalledTimes(1));

    localStorage.setItem('access_token', tokenB);
    localStorage.setItem('refresh_token', tokenB);
    act(() => {
      window.dispatchEvent(
        new StorageEvent('storage', {
          key: 'access_token',
          oldValue: tokenA,
          newValue: tokenB,
        }),
      );
    });

    await waitFor(() => expect(ctx?.user?.id).toBe(8));
    firstUser.resolve(userFor(7));
    await act(async () => {
      await Promise.resolve();
    });
    expect(ctx?.user?.id).toBe(8);
  });
});
