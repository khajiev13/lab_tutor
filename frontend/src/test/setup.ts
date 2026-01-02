import '@testing-library/jest-dom';

// Provide a consistent `localStorage` implementation for all tests.
// Some tests may stub/override it, but this ensures required methods exist.
// (Vitest jsdom localStorage can be unavailable/mocked in certain environments.)
import { vi } from 'vitest';

const store = new Map<string, string>();
vi.stubGlobal('localStorage', {
  getItem: (key: string) => (store.has(key) ? store.get(key)! : null),
  setItem: (key: string, value: string) => {
    store.set(key, String(value));
  },
  removeItem: (key: string) => {
    store.delete(key);
  },
  clear: () => {
    store.clear();
  },
});
