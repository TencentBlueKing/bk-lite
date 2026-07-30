import type { RecoveredAuthUser } from '@/utils/authRecovery';

interface RecoverySessionToken {
  id?: unknown;
  username?: unknown;
  token?: unknown;
  locale?: unknown;
  timezone?: unknown;
}

type RecoveryFetch = (
  input: RequestInfo | URL,
  init?: RequestInit,
) => Promise<Response>;

export const validateRecoverySession = async (
  sessionToken: RecoverySessionToken | null,
  request: RecoveryFetch = fetch,
  apiUrl = process.env.NEXTAPI_URL,
): Promise<RecoveredAuthUser | null> => {
  const backendToken = typeof sessionToken?.token === 'string'
    ? sessionToken.token
    : '';
  const sessionUsername = typeof sessionToken?.username === 'string'
    ? sessionToken.username
    : '';
  const sessionId = sessionToken?.id;

  if (!backendToken || (!sessionId && !sessionUsername) || !apiUrl) {
    return null;
  }

  const response = await request(
    new URL('/api/v1/core/api/login_info/', apiUrl),
    {
      method: 'GET',
      headers: {
        Accept: 'application/json',
        Authorization: `Bearer ${backendToken}`,
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        Pragma: 'no-cache',
      },
      cache: 'no-store',
    },
  );

  if (!response.ok) {
    return null;
  }

  const payload = await response.json();
  const verifiedUsername = payload?.data?.username;
  if (
    !payload?.result
    || !verifiedUsername
    || (sessionUsername && verifiedUsername !== sessionUsername)
  ) {
    return null;
  }

  return {
    id: String(sessionId || verifiedUsername),
    username: verifiedUsername,
    token: backendToken,
    locale: typeof sessionToken?.locale === 'string' ? sessionToken.locale : undefined,
    timezone: typeof sessionToken?.timezone === 'string' ? sessionToken.timezone : undefined,
  };
};
