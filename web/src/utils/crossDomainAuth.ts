interface AuthData {
  id: string;
  username: string;
  token: string;
  locale: string;
  timezone?: string;
  temporary_pwd: boolean;
  enable_otp: boolean;
  qrcode: boolean;
  provider?: string;
  wechatOpenId?: string;
  wechatUnionId?: string;
  wechatWorkId?: string;
}

/**
 * Save authentication token.
 * The bklite_token cookie is now set by the backend via Set-Cookie header (HttpOnly + Secure).
 * This function is retained for call-site compatibility but no longer writes to document.cookie.
 */
// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function saveAuthToken(_userData: AuthData): void {
  // Cookie is now set server-side with HttpOnly; no client-side action needed.
}

/**
 * Clear authentication token from cookie.
 * The backend logout endpoint clears the HttpOnly cookie via Set-Cookie.
 * This function attempts a client-side delete as a fallback for non-HttpOnly cookies
 * that may still exist during the transition period.
 */
export function clearAuthToken(): void {
  try {
    // Fallback: clear any legacy non-HttpOnly bklite_token cookie
    const pastDate = 'Thu, 01 Jan 1970 00:00:00 UTC';
    document.cookie = `bklite_token=; expires=${pastDate}; path=/`;
  } catch {
    // Silent fail: cookie clearing is best-effort
  }
}
