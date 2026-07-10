export interface AuthSessionSnapshot {
  generation: number;
  userId: number;
}

export class StaleAuthSessionError extends Error {
  constructor(message = 'The authenticated session changed before the request completed.') {
    super(message);
    this.name = 'StaleAuthSessionError';
  }
}

let activeUserId: number | null = null;
let generation = 0;

export function establishAuthSession(userId: number): AuthSessionSnapshot {
  if (activeUserId !== userId) {
    generation += 1;
  }
  activeUserId = userId;
  return { generation, userId };
}

export function invalidateAuthSession(): void {
  generation += 1;
  activeUserId = null;
}

export function captureAuthSession(userId: number): AuthSessionSnapshot {
  if (activeUserId !== userId) {
    throw new StaleAuthSessionError();
  }
  return { generation, userId };
}

export function captureCurrentAuthSession(): AuthSessionSnapshot {
  if (activeUserId === null) {
    throw new StaleAuthSessionError();
  }
  return { generation, userId: activeUserId };
}

export function assertAuthSessionCurrent(snapshot: AuthSessionSnapshot): void {
  if (snapshot.generation !== generation || snapshot.userId !== activeUserId) {
    throw new StaleAuthSessionError();
  }
}

export function isAuthSessionCurrent(snapshot: AuthSessionSnapshot): boolean {
  return snapshot.generation === generation && snapshot.userId === activeUserId;
}

export function isStaleAuthSessionError(error: unknown): error is StaleAuthSessionError {
  return error instanceof StaleAuthSessionError;
}

export function resetAuthSessionForTests(): void {
  activeUserId = null;
  generation = 0;
}
