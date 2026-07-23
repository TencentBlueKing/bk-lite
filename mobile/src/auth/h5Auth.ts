export type H5LoginStatus =
  | 'success'
  | 'invalid-credentials'
  | 'otp-required'
  | 'password-reset-required'
  | 'service-unavailable';

export interface H5LoginCredentials {
  username: string;
  password: string;
  domain: string;
}

interface SignInResponseLike {
  ok?: boolean;
  error?: string | null;
}

interface H5LoginDependencies {
  signIn: (
    provider: string,
    options: Record<string, unknown>,
  ) => Promise<SignInResponseLike | undefined>;
  getSession: () => Promise<unknown>;
}

interface H5RestoreDependencies {
  getSession: () => Promise<unknown>;
  clearSession: () => Promise<unknown>;
}

interface H5LogoutDependencies {
  federatedLogout: () => Promise<{ ok?: boolean }>;
  signOut: (options: { redirect: false }) => Promise<unknown>;
}

interface H5RejectedSessionDependencies {
  clearSession: () => Promise<unknown>;
  resetLocalState: () => Promise<unknown>;
}

type H5LoginResult =
  | { status: 'success'; token: string }
  | { status: Exclude<H5LoginStatus, 'success'> };

function extractSessionToken(session: unknown): string | null {
  if (!session || typeof session !== 'object') {
    return null;
  }

  const user = (session as { user?: unknown }).user;
  if (!user || typeof user !== 'object') {
    return null;
  }

  const token = (user as { token?: unknown }).token;
  return typeof token === 'string' && token ? token : null;
}

function mapSignInError(error?: string | null): Exclude<H5LoginStatus, 'success'> {
  void error;
  return 'invalid-credentials';
}

function isTemporaryPasswordSession(session: unknown): boolean {
  if (!session || typeof session !== 'object') return false;
  const user = (session as { user?: unknown }).user;
  if (!user || typeof user !== 'object') return false;
  return (user as { temporary_pwd?: unknown }).temporary_pwd === true;
}

export async function loginWithH5Session(
  credentials: H5LoginCredentials,
  dependencies: H5LoginDependencies,
): Promise<H5LoginResult> {
  try {
    const response = await dependencies.signIn('credentials', {
      ...credentials,
      redirect: false,
    });

    if (!response?.ok) {
      return { status: mapSignInError(response?.error) };
    }

    const session = await dependencies.getSession();
    if (isTemporaryPasswordSession(session)) {
      return { status: 'password-reset-required' };
    }

    const token = extractSessionToken(session);
    return token ? { status: 'success', token } : { status: 'otp-required' };
  } catch {
    return { status: 'service-unavailable' };
  }
}

export async function restoreH5Session(
  dependencies: H5RestoreDependencies,
): Promise<string | null> {
  const session = await dependencies.getSession();
  if (!session) return null;

  const token = extractSessionToken(session);
  if (isTemporaryPasswordSession(session) || !token) {
    await dependencies.clearSession();
    return null;
  }

  return token;
}

export async function clearRejectedH5Session(
  dependencies: H5RejectedSessionDependencies,
): Promise<void> {
  try {
    await dependencies.clearSession();
  } finally {
    await dependencies.resetLocalState();
  }
}

export async function logoutH5Session(
  dependencies: H5LogoutDependencies,
): Promise<{ backendLogoutAccepted: boolean }> {
  let backendLogoutAccepted = false;
  try {
    const response = await dependencies.federatedLogout();
    backendLogoutAccepted = response.ok === true;
  } catch {
    backendLogoutAccepted = false;
  } finally {
    await dependencies.signOut({ redirect: false });
  }

  return { backendLogoutAccepted };
}
