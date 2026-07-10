import type { UserResponse } from '@/features/auth/types';

export function getAuthenticatedLandingPath(user: Pick<UserResponse, 'role'> | null): string {
  return user?.role === 'individual' ? '/individual/profile' : '/home';
}
