import { noticeForExternalSession } from './session';
import type { LoginNotice, OAuthPending } from './types';

export const OAUTH_PENDING_STORAGE_KEY = 'bklite.mobile.oauthPending';
export const OAUTH_LOGIN_CHANNEL = 'oauth';

export function buildExternalLoginStartBody(input: {
  bindingId: number;
  callbackUrl: string;
  redirectOrigin: string;
  resultPath: string;
}) {
  return {
    binding_id: input.bindingId,
    callback_url: input.callbackUrl,
    redirect_origin: input.redirectOrigin,
    result_path: input.resultPath,
    login_channel: OAUTH_LOGIN_CHANNEL,
  };
}

interface KeyValueStorage {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
  removeItem: (key: string) => void;
}

export interface OAuthStatusPayload {
  status?: string;
  login_result?: {
    id?: string | number;
    username?: string;
    token?: string;
    locale?: string;
    timezone?: string;
    domain?: string;
    temporary_pwd?: boolean;
    enable_otp?: boolean;
    require_otp?: boolean;
    qrcode?: boolean;
  };
}

export function saveOAuthPending(storage: KeyValueStorage, pending: OAuthPending) {
  storage.setItem(OAUTH_PENDING_STORAGE_KEY, JSON.stringify(pending));
}

function parseOAuthPending(value: unknown): OAuthPending | null {
  if (!value || typeof value !== 'object') return null;
  const authRequestId = (value as { authRequestId?: unknown }).authRequestId;
  const pollToken = (value as { pollToken?: unknown }).pollToken;
  if (typeof authRequestId !== 'string' || !authRequestId) return null;
  if (typeof pollToken !== 'string' || !pollToken) return null;
  const bindingName = (value as { bindingName?: unknown }).bindingName;
  return {
    authRequestId,
    pollToken,
    bindingName: typeof bindingName === 'string' ? bindingName : '',
  };
}

export function readOAuthPending(storage: KeyValueStorage): OAuthPending | null {
  const raw = storage.getItem(OAUTH_PENDING_STORAGE_KEY);
  if (!raw) return null;
  try {
    return parseOAuthPending(JSON.parse(raw) as unknown);
  } catch {
    return null;
  }
}

export function clearOAuthPending(storage: KeyValueStorage) {
  storage.removeItem(OAUTH_PENDING_STORAGE_KEY);
}

export function readOAuthReturnStatus(search: string): string {
  const value = new URLSearchParams(search).get('status') || '';
  return value.trim();
}

export function noticeForOAuthStatus(status: string, name: string): LoginNotice {
  if (status === 'cancelled') return { reason: 'oauth_cancelled', name };
  return { reason: 'oauth_failed', name };
}

export async function completeOAuthReturn(input: {
  pending: OAuthPending | null;
  returnStatus: string;
  fetchStatus: (pending: OAuthPending) => Promise<OAuthStatusPayload | null>;
  establishSession: (loginResult: NonNullable<OAuthStatusPayload['login_result']>) => Promise<{ status: string; token?: string }>;
}): Promise<{ status: 'success'; token: string } | { status: 'degraded'; notice: LoginNotice }> {
  const name = input.pending?.bindingName || '';
  if (!input.pending) {
    return { status: 'degraded', notice: noticeForOAuthStatus(input.returnStatus, name) };
  }
  if (input.returnStatus && input.returnStatus !== 'success' && input.returnStatus !== 'pending') {
    return { status: 'degraded', notice: noticeForOAuthStatus(input.returnStatus, name) };
  }

  let payload: OAuthStatusPayload | null;
  try {
    payload = await input.fetchStatus(input.pending);
  } catch {
    return { status: 'degraded', notice: { reason: 'oauth_failed', name } };
  }
  if (!payload || payload.status !== 'success' || !payload.login_result) {
    return {
      status: 'degraded',
      notice: noticeForOAuthStatus(payload?.status || input.returnStatus, name),
    };
  }

  const session = await input.establishSession(payload.login_result);
  if (session.status === 'success' && session.token) {
    return { status: 'success', token: session.token };
  }
  return { status: 'degraded', notice: noticeForExternalSession(session.status, name) };
}
