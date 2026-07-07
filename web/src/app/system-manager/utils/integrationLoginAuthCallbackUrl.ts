const LOGIN_AUTH_CALLBACK_PATH = '/api/v1/core/api/login_auth/callback/';

interface BuildLoginAuthCallbackUrlParams {
  currentOrigin?: string;
  backendCallbackUrl?: string;
}

export function buildLoginAuthCallbackUrl({
  currentOrigin,
  backendCallbackUrl = '',
}: BuildLoginAuthCallbackUrlParams): string {
  const normalizedBackendUrl = backendCallbackUrl.trim();
  if (normalizedBackendUrl) {
    return normalizedBackendUrl;
  }
  const normalizedOrigin = currentOrigin?.trim().replace(/\/+$/, '');
  if (!normalizedOrigin) {
    return '';
  }
  return `${normalizedOrigin}${LOGIN_AUTH_CALLBACK_PATH}`;
}
