export const SUPPRESS_SILENT_LOGIN_KEY = 'bklite.mobile.suppressSilentLogin';

interface KeyValueStorage {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
  removeItem: (key: string) => void;
}

export function suppressSilentLogin(storage: KeyValueStorage) {
  storage.setItem(SUPPRESS_SILENT_LOGIN_KEY, '1');
}

export function isSilentLoginSuppressed(storage: KeyValueStorage): boolean {
  return storage.getItem(SUPPRESS_SILENT_LOGIN_KEY) === '1';
}

export function clearSilentLoginSuppression(storage: KeyValueStorage) {
  storage.removeItem(SUPPRESS_SILENT_LOGIN_KEY);
}
