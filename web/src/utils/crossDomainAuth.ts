interface AuthData {
  id: string;
  username: string;
  token: string;
  locale: string;
  temporary_pwd: boolean;
  enable_otp: boolean;
  qrcode: boolean;
  provider?: string;
  wechatOpenId?: string;
  wechatUnionId?: string;
  wechatWorkId?: string;
}

const AUTH_EXPIRY_HOURS = 24;

/**
 * Set cookie
 */
function setCookie(name: string, value: string, hours: number = AUTH_EXPIRY_HOURS): void {
  const expires = new Date();
  expires.setTime(expires.getTime() + (hours * 60 * 60 * 1000));
  
  const cookieOptions = `expires=${expires.toUTCString()}; path=/; SameSite=Lax`;
  document.cookie = `${name}=${value}; ${cookieOptions}`;
}

/**
 * Delete cookie
 */
function deleteCookie(name: string): void {
  const pastDate = 'Thu, 01 Jan 1970 00:00:00 UTC';
  document.cookie = `${name}=; expires=${pastDate}; path=/`;
}

/**
 * Save authentication token to cookie
 */
export function saveAuthToken(userData: AuthData): void {
  try {
    setCookie('bklite_token', userData.token, AUTH_EXPIRY_HOURS);
  } catch (error) {
    console.error('Failed to save auth token:', error);
  }
}

/**
 * Clear authentication token from cookie
 */
export function clearAuthToken(): void {
  try {
    deleteCookie('bklite_token');
  } catch (error) {
    console.error('Failed to clear auth token:', error);
  }
}