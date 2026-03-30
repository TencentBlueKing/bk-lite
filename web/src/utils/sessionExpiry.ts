const SESSION_EXPIRED_EVENT = 'bk-lite:session-expired';

const SESSION_EXPIRY_IGNORED_PATH_PREFIXES = [
  '/auth/',
  '/api/auth/',
  '/api/locales',
  '/api/menu',
  '/api/versions',
  '/api/markdown',
];

const SESSION_EXPIRY_IGNORED_REQUEST_PATHS = [
  '/api/proxy/core/api/get_domain_list/',
  '/api/proxy/core/api/get_bk_settings/',
  '/api/proxy/core/api/get_wechat_settings/',
  '/api/proxy/core/api/login/',
  '/api/proxy/core/api/reset_pwd/',
  '/api/proxy/core/api/verify_otp_code/',
];

let sessionExpiredDispatched = false;

export interface SessionExpiredDetail {
  reason?: string;
  status?: number;
}

export const emitSessionExpired = (detail?: SessionExpiredDetail) => {
  if (typeof window === 'undefined' || sessionExpiredDispatched) {
    return;
  }

  sessionExpiredDispatched = true;
  window.dispatchEvent(new CustomEvent<SessionExpiredDetail>(SESSION_EXPIRED_EVENT, { detail }));
};

export const resetSessionExpiredState = () => {
  sessionExpiredDispatched = false;
};

export const isSessionExpiredState = () => sessionExpiredDispatched;

export const SESSION_EXPIRED_REQUEST_ERROR = 'SESSION_EXPIRED_REQUEST_ERROR';

export const createSessionExpiredRequestError = () => {
  const error = new Error(SESSION_EXPIRED_REQUEST_ERROR);
  error.name = SESSION_EXPIRED_REQUEST_ERROR;
  return error;
};

export const isAuthPath = (pathname?: string | null) => {
  if (!pathname) {
    return false;
  }

  return ['/auth/signin', '/auth/signout', '/auth/callback'].includes(pathname);
};

const resolveRequestUrl = (input?: RequestInfo | URL | string | null) => {
  if (typeof window === 'undefined' || !input) {
    return null;
  }

  const requestUrl = input instanceof Request ? input.url : input.toString();

  try {
    return new URL(requestUrl, window.location.origin);
  } catch {
    return null;
  }
};

export const hasClientAuthToken = () => {
  if (typeof document === 'undefined') {
    return false;
  }

  return document.cookie
    .split(';')
    .some((cookie) => cookie.trim().startsWith('bklite_token='));
};

export const shouldHandleSessionExpiry = (input?: RequestInfo | URL | string | null) => {
  const requestUrl = resolveRequestUrl(input);

  if (!requestUrl || requestUrl.origin !== window.location.origin) {
    return false;
  }

  const { pathname } = requestUrl;

  if (SESSION_EXPIRY_IGNORED_PATH_PREFIXES.some((prefix) => pathname.startsWith(prefix))) {
    return false;
  }

  if (SESSION_EXPIRY_IGNORED_REQUEST_PATHS.some((path) => pathname.startsWith(path))) {
    return false;
  }

  return pathname.startsWith('/api/') || pathname.includes('/api/');
};

export const shouldTriggerSessionExpiry = (input?: RequestInfo | URL | string | null) => {
  if (typeof window === 'undefined') {
    return false;
  }

  return !isAuthPath(window.location.pathname)
    && hasClientAuthToken()
    && shouldHandleSessionExpiry(input);
};

export { SESSION_EXPIRED_EVENT };
