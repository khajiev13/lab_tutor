import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, render, waitFor } from '@testing-library/react';
import { AuthProvider, useAuth } from './AuthContext';
import type { LoginResponse, UserResponse } from '../types';

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

describe('AuthContext', () => {
  beforeEach(() => {
    // Some existing tests stub `localStorage` without implementing `.clear()`.
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    sessionStorage.removeItem('individual-learning.graph-session');
    vi.clearAllMocks();
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
});

