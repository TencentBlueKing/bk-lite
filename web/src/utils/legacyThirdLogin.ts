import { PORTAL_HOME_PATH } from '@/utils/route';

interface AuthorizeLegacyThirdLoginOptions {
  callbackUrl: string;
  thirdLoginCode: string;
  token: string;
}

export async function requestLegacyThirdLoginAuthorize({
  callbackUrl,
  thirdLoginCode,
  token,
}: AuthorizeLegacyThirdLoginOptions): Promise<string> {
  if (!callbackUrl || !thirdLoginCode || !token) {
    return PORTAL_HOME_PATH;
  }

  try {
    const response = await fetch('/api/proxy/core/api/legacy_third_login/authorize/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        callback_url: callbackUrl,
        third_login_code: thirdLoginCode,
      }),
    });
    if (!response.ok) {
      return PORTAL_HOME_PATH;
    }

    const payload: unknown = await response.json();
    const redirectUrl =
      payload && typeof payload === 'object' && 'redirect_url' in payload
        ? (payload as { redirect_url?: unknown }).redirect_url
        : undefined;
    if (typeof redirectUrl !== 'string' || !redirectUrl) {
      return PORTAL_HOME_PATH;
    }
    return redirectUrl;
  } catch {
    return PORTAL_HOME_PATH;
  }
}
