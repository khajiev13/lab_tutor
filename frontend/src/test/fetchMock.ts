/**
 * Lightweight fetch mock helper for Vitest.
 *
 * Usage:
 *   import { mockFetch, mockFetchError } from './fetchMock';
 *
 *   const restore = mockFetch({ data: 'ok' });
 *   // ... run test ...
 *   restore();
 */

import { vi } from 'vitest';

type FetchMockResponse = {
  ok?: boolean;
  status?: number;
  json?: unknown;
  text?: string;
};

/**
 * Stub `globalThis.fetch` so the next call returns the given payload.
 * Returns a restore function that un-stubs fetch.
 */
export function mockFetch(response: FetchMockResponse, once = false) {
  const ok = response.ok !== undefined ? response.ok : true;
  const status = response.status ?? (ok ? 200 : 500);
  const jsonPayload = response.json !== undefined ? response.json : {};
  const textPayload = response.text ?? '';

  const mockFn = vi.fn().mockImplementation(() =>
    Promise.resolve({
      ok,
      status,
      json: () => Promise.resolve(jsonPayload),
      text: () => Promise.resolve(textPayload),
    }),
  );

  if (once) {
    mockFn.mockImplementationOnce(() =>
      Promise.resolve({
        ok,
        status,
        json: () => Promise.resolve(jsonPayload),
        text: () => Promise.resolve(textPayload),
      }),
    );
  }

  vi.stubGlobal('fetch', mockFn);
  return () => vi.unstubAllGlobals();
}

/**
 * Stub `globalThis.fetch` to reject with the given error.
 */
export function mockFetchError(errorMessage = 'Network error') {
  const mockFn = vi.fn().mockRejectedValue(new Error(errorMessage));
  vi.stubGlobal('fetch', mockFn);
  return () => vi.unstubAllGlobals();
}

/**
 * Stub `globalThis.fetch` to return an HTTP error response.
 */
export function mockFetchHttpError(status = 500, body = 'Internal Server Error') {
  const mockFn = vi.fn().mockResolvedValue({
    ok: false,
    status,
    json: () => Promise.resolve({ detail: body }),
    text: () => Promise.resolve(body),
  });
  vi.stubGlobal('fetch', mockFn);
  return () => vi.unstubAllGlobals();
}
