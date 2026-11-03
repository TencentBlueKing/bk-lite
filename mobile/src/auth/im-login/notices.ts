import type { LoginNotice } from './types';

export const LOGIN_NOTICE_STORAGE_KEY = 'bklite.mobile.loginNotice';

interface KeyValueStorage {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
  removeItem: (key: string) => void;
}

export function writeLoginNotice(storage: KeyValueStorage, notice: LoginNotice) {
  storage.setItem(LOGIN_NOTICE_STORAGE_KEY, JSON.stringify(notice));
}

export function consumeLoginNotice(storage: KeyValueStorage): LoginNotice | null {
  const raw = storage.getItem(LOGIN_NOTICE_STORAGE_KEY);
  if (!raw) return null;
  storage.removeItem(LOGIN_NOTICE_STORAGE_KEY);
  try {
    const parsed = JSON.parse(raw) as LoginNotice;
    if (!parsed || typeof parsed.reason !== 'string') return null;
    return { reason: parsed.reason, name: parsed.name || '' };
  } catch {
    return null;
  }
}
