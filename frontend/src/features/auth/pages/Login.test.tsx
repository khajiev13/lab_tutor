import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { UserResponse } from '@/features/auth/types';

const authMocks = vi.hoisted(() => ({
  login: vi.fn(),
}));

vi.mock('@/features/auth/context/AuthContext', () => ({
  useAuth: () => ({ login: authMocks.login }),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import Login from '@/features/auth/pages/Login';

function Location() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

function renderLogin() {
  render(
    <MemoryRouter initialEntries={['/login']}>
      <Routes>
        <Route path="*" element={<><Login /><Location /></>} />
      </Routes>
    </MemoryRouter>,
  );
}

async function submitLogin() {
  const user = userEvent.setup();
  await user.type(screen.getByPlaceholderText('you@example.com'), 'person@example.com');
  await user.type(screen.getByPlaceholderText('Enter your password'), 'secret');
  await user.click(screen.getByRole('button', { name: /sign in/i }));
}

function authenticatedUser(role: UserResponse['role']): UserResponse {
  return {
    id: 7,
    first_name: 'Test',
    last_name: 'Person',
    email: 'person@example.com',
    role,
    created_at: '2026-07-10T00:00:00Z',
  };
}

describe('Login', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('sends an individual login into the recovery-gated workflow', async () => {
    authMocks.login.mockResolvedValue(authenticatedUser('individual'));
    renderLogin();

    await submitLogin();

    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent('/individual/profile');
    });
  });

  it.each(['student', 'teacher'] as const)('keeps %s logins on the shared home route', async (role) => {
    authMocks.login.mockResolvedValue(authenticatedUser(role));
    renderLogin();

    await submitLogin();

    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent('/home');
    });
  });
});
