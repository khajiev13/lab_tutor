/**
 * Lightweight JWT helpers – decode & check expiry on the client side
 * without signature verification (the backend still validates signatures).
 *
 * This avoids wasting a round-trip to `/users/me` when the access token
 * is already expired and lets us go straight to refresh or clear tokens.
 */

interface JwtPayload {
  sub?: string;
  exp?: number;
  type?: string;
  [key: string]: unknown;
}

/** Decode a JWT payload without verifying the signature. */
export function decodeJwtPayload(token: string): JwtPayload | null {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const payload = parts[1];
    const json = atob(payload.replace(/-/g, '+').replace(/_/g, '/'));
    return JSON.parse(json) as JwtPayload;
  } catch {
    return null;
  }
}

/** Returns `true` when the token's `exp` claim is in the past (or unparseable). */
export function isTokenExpired(token: string, clockSkewSeconds = 30): boolean {
  const payload = decodeJwtPayload(token);
  if (!payload?.exp) return true; // treat un-decodable tokens as expired
  const nowSeconds = Math.floor(Date.now() / 1000);
  return payload.exp < nowSeconds + clockSkewSeconds;
}
