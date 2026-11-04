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

const LOGIN_NOTICE_TOAST_KEYS: Partial<Record<LoginNotice['reason'], string>> = {
  jsapi_failed: 'login.silentFailed',
  exchange_failed: 'login.silentFailed',
  session_failed: 'login.sessionFailed',
  oauth_failed: 'login.oauthFailed',
  oauth_cancelled: 'login.oauthCancelled',
};

export type LoginNoticePresentation =
  | { type: 'otp' }
  | { type: 'password-reset' }
  | { type: 'toast'; messageKey: string };

export function presentationForLoginNotice(reason: string): LoginNoticePresentation {
  if (reason === 'otp_required') return { type: 'otp' };
  if (reason === 'password_reset_required') return { type: 'password-reset' };
  return {
    type: 'toast',
    messageKey: LOGIN_NOTICE_TOAST_KEYS[reason as LoginNotice['reason']] || 'login.oauthFailed',
  };
}

function parseLoginNotice(value: unknown): LoginNotice | null {
  if (!value || typeof value !== 'object') return null;
  const reason = (value as { reason?: unknown }).reason;
  if (typeof reason !== 'string') return null;
  const name = (value as { name?: unknown }).name;
  return {
    reason: reason as LoginNotice['reason'],
    name: typeof name === 'string' ? name : '',
  };
}

export function consumeLoginNotice(storage: KeyValueStorage): LoginNotice | null {
  const raw = storage.getItem(LOGIN_NOTICE_STORAGE_KEY);
  if (!raw) return null;
  storage.removeItem(LOGIN_NOTICE_STORAGE_KEY);
  try {
    return parseLoginNotice(JSON.parse(raw) as unknown);
  } catch {
    return null;
  }
}
