import type { ExternalLoginResult } from './types';

export const PENDING_LOGIN_STORAGE_KEY = 'bklite.mobile.pendingLogin';

export type LoginContinuation = 'otp' | 'reset' | 'session' | 'invalid';

interface KeyValueStorage {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
  removeItem: (key: string) => void;
}

function stringList(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const apps = value.filter((item): item is string => typeof item === 'string' && item.trim() !== '');
  return apps.length > 0 ? apps : undefined;
}

export function pendingFromLoginData(data: ExternalLoginResult | null | undefined): ExternalLoginResult {
  if (!data) return {};
  return {
    id: data.id,
    username: typeof data.username === 'string' ? data.username : undefined,
    token: typeof data.token === 'string' ? data.token : undefined,
    locale: typeof data.locale === 'string' ? data.locale : undefined,
    timezone: typeof data.timezone === 'string' ? data.timezone : undefined,
    domain: typeof data.domain === 'string' ? data.domain : undefined,
    temporary_pwd: data.temporary_pwd === true,
    enable_otp: data.enable_otp === true,
    require_otp: data.require_otp === true,
    challenge_id: typeof data.challenge_id === 'string' ? data.challenge_id : undefined,
    qr_code: typeof data.qr_code === 'string' ? data.qr_code : undefined,
    need_binding: data.need_binding === true,
    otp_setup_key: typeof data.otp_setup_key === 'string' && data.otp_setup_key ? data.otp_setup_key : undefined,
    otp_recommended_apps: stringList(data.otp_recommended_apps),
    qrcode: data.qrcode === true,
  };
}

/** Same order as the PC sign-in page: OTP before temporary password. */
export function continuationOfLoginData(data: ExternalLoginResult | null | undefined): LoginContinuation {
  if (!data) return 'invalid';
  if (data.require_otp && data.challenge_id) return 'otp';
  if (data.temporary_pwd) return 'reset';
  if (data.token && (data.id || data.username)) return 'session';
  return 'invalid';
}

export function savePendingLogin(storage: KeyValueStorage, pending: ExternalLoginResult) {
  storage.setItem(PENDING_LOGIN_STORAGE_KEY, JSON.stringify(pendingFromLoginData(pending)));
}

export function readPendingLogin(storage: KeyValueStorage): ExternalLoginResult | null {
  const raw = storage.getItem(PENDING_LOGIN_STORAGE_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== 'object') return null;
    return pendingFromLoginData(parsed as ExternalLoginResult);
  } catch {
    return null;
  }
}

export function clearPendingLogin(storage: KeyValueStorage) {
  storage.removeItem(PENDING_LOGIN_STORAGE_KEY);
}
