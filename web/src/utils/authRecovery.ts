export interface RecoveredAuthUser {
  id: string;
  username?: string;
  token: string;
  locale?: string;
  timezone?: string;
}

export type AuthRecoveryResult =
  | { status: 'recovered'; user: RecoveredAuthUser }
  | { status: 'account-changed' }
  | { status: 'unavailable' };

type RecoveryFetch = (
  input: RequestInfo | URL,
  init?: RequestInit,
) => Promise<Response>;

export const fetchRecoveredAuth = async (
  request: RecoveryFetch = fetch,
): Promise<RecoveredAuthUser | null> => {
  const response = await request('/api/auth/session', {
    method: 'GET',
    headers: {
      'Cache-Control': 'no-cache, no-store, must-revalidate',
      Pragma: 'no-cache',
    },
    credentials: 'include',
    cache: 'no-store',
  });

  if (!response.ok) {
    return null;
  }

  const payload = await response.json();
  const user = payload?.user;
  if (!user?.token || (!user.id && !user.username)) {
    return null;
  }

  return {
    id: String(user.id || user.username),
    username: user.username,
    token: user.token,
    locale: user.locale,
    timezone: user.timezone,
  };
};

export const resolveAuthToken = (
  recoveredToken: string | null | undefined,
  sessionToken: string | null | undefined,
) => recoveredToken || sessionToken || null;

export const getAuthUserIdentity = (
  user: { id?: string | null; username?: string | null } | null | undefined,
) => {
  const identity = user?.id || user?.username;
  return identity ? String(identity) : null;
};

const wait = (milliseconds: number) => new Promise<void>((resolve) => {
  window.setTimeout(resolve, milliseconds);
});

export const recoverAuthWithRetry = async (
  expectedUserIdentity: string | null,
  checkAuth: () => Promise<RecoveredAuthUser | null> = fetchRecoveredAuth,
  retryDelays: readonly number[] = [0, 1000, 3000],
  waitForDelay: (milliseconds: number) => Promise<void> = wait,
): Promise<AuthRecoveryResult> => {
  if (!expectedUserIdentity) {
    return { status: 'unavailable' };
  }

  let previousDelay = 0;
  for (const delay of retryDelays) {
    const waitTime = Math.max(0, delay - previousDelay);
    previousDelay = delay;
    if (waitTime > 0) {
      await waitForDelay(waitTime);
    }

    try {
      const recoveredUser = await checkAuth();
      if (!recoveredUser) {
        continue;
      }

      if (getAuthUserIdentity(recoveredUser) !== expectedUserIdentity) {
        return { status: 'account-changed' };
      }

      return { status: 'recovered', user: recoveredUser };
    } catch {
      // Only the authentication check is retried; business requests are never replayed.
    }
  }

  return { status: 'unavailable' };
};
