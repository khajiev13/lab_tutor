export const AUTH_SESSION_EXPIRED_EVENT = 'auth:session-expired';

export function dispatchAuthSessionExpired(): void {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(AUTH_SESSION_EXPIRED_EVENT));
  }
}
