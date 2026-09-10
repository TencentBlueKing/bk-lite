export const LEGACY_THIRD_LOGIN_EXCHANGE_PATH = '/api/proxy/core/api/legacy_third_login/exchange';

export function isLegacyThirdLoginExchangePath(pathname: string): boolean {
  const normalized = pathname.endsWith('/') ? pathname.slice(0, -1) : pathname;
  return normalized === LEGACY_THIRD_LOGIN_EXCHANGE_PATH;
}
