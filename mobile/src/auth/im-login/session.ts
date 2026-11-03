import type { ExternalLoginResult } from './types';

interface SignInResponseLike {
  ok?: boolean;
}

interface SessionDependencies {
  signIn: (provider: string, options: Record<string, unknown>) => Promise<SignInResponseLike | undefined>;
  getSession: () => Promise<unknown>;
  signOut: (options: { redirect: false }) => Promise<unknown>;
}

export type ExternalSessionStatus =
  | { status: 'success'; token: string }
  | { status: 'otp-required' }
  | { status: 'password-reset-required' }
  | { status: 'invalid-credentials' }
  | { status: 'service-unavailable' };

function sessionToken(session: unknown): string | null {
  if (!session || typeof session !== 'object') return null;
  const user = (session as { user?: unknown }).user;
  if (!user || typeof user !== 'object') return null;
  const token = (user as { token?: unknown }).token;
  return typeof token === 'string' && token ? token : null;
}

export async function establishH5SessionFromLoginResult(
  loginResult: ExternalLoginResult,
  dependencies: SessionDependencies,
): Promise<ExternalSessionStatus> {
  if (loginResult.temporary_pwd) {
    await dependencies.signOut({ redirect: false });
    return { status: 'password-reset-required' };
  }
  if (loginResult.require_otp || loginResult.enable_otp) {
    await dependencies.signOut({ redirect: false });
    return { status: 'otp-required' };
  }
  if (!loginResult.token || !(loginResult.id || loginResult.username)) {
    return { status: 'invalid-credentials' };
  }

  const userData = {
    id: loginResult.id || loginResult.username,
    username: loginResult.username || '',
    token: loginResult.token,
    locale: loginResult.locale || 'zh-CN',
    timezone: loginResult.timezone || 'Asia/Shanghai',
    temporary_pwd: false,
    enable_otp: false,
    qrcode: Boolean(loginResult.qrcode),
  };

  try {
    const response = await dependencies.signIn('credentials', {
      redirect: false,
      username: userData.username,
      password: '',
      domain: loginResult.domain || 'domain.com',
      skipValidation: 'true',
      userData: JSON.stringify(userData),
    });
    if (!response?.ok) return { status: 'service-unavailable' };
    const token = sessionToken(await dependencies.getSession());
    return token ? { status: 'success', token } : { status: 'service-unavailable' };
  } catch {
    return { status: 'service-unavailable' };
  }
}
