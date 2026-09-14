import { beforeEach, describe, expect, it, vi } from 'vitest';

const {
  authOptions,
  getAuthOptions,
  nextAuth,
  getServerSession,
  headers,
} = vi.hoisted(() => ({
  authOptions: { session: { strategy: 'jwt' } },
  getAuthOptions: vi.fn(async () => ({ providers: [{ id: 'wechat' }] })),
  nextAuth: vi.fn(),
  getServerSession: vi.fn(async () => null),
  headers: vi.fn(async () => new Headers()),
}));

vi.mock('@/constants/authOptions', () => ({
  authOptions,
  getAuthOptions,
}));
vi.mock('next-auth', () => ({ default: nextAuth, getServerSession }));
vi.mock('next/headers', () => ({ headers }));
vi.mock('next/navigation', () => ({ redirect: vi.fn() }));
vi.mock('../SigninClient', () => ({ default: () => null }));
vi.mock('../PopupAuthBridge', () => ({ default: () => null }));
vi.mock('../LegacyThirdLoginAuthorizeBridge', () => ({ default: () => null }));
vi.mock('@/utils/authRedirect', () => ({
  buildThirdLoginCallbackUrl: vi.fn(),
  getLegacyThirdLoginCode: vi.fn(() => null),
  resolveThirdLoginFlag: vi.fn(() => false),
}));
vi.mock('@/utils/userPreferences', () => ({
  normalizeLocale: (value: string) => value,
  normalizeTimezone: (value: string) => value,
}));

import SigninPage from '../page';
import { redirect } from 'next/navigation';
import { getLegacyThirdLoginCode } from '@/utils/authRedirect';
import LegacyThirdLoginAuthorizeBridge from '../LegacyThirdLoginAuthorizeBridge';

describe('SigninPage session configuration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('reads the session without rebuilding dynamic WeChat providers', async () => {
    await SigninPage({
      searchParams: Promise.resolve({
        callbackUrl: '/',
        error: '',
      }),
    });

    expect(getAuthOptions).not.toHaveBeenCalled();
    expect(getServerSession).toHaveBeenCalledWith(authOptions);
  });

  it('keeps screen query when redirecting an already authenticated user', async () => {
    const { buildThirdLoginCallbackUrl } = await import('@/utils/authRedirect');
    vi.mocked(buildThirdLoginCallbackUrl).mockReturnValue('/ops-console/home');
    getServerSession.mockResolvedValueOnce({
      user: { id: 'u1', token: 'jwt-token' },
    });

    await SigninPage({
      searchParams: Promise.resolve({
        callbackUrl: '/ops-console/home',
        error: '',
        screen: 'true',
      }),
    });

    expect(redirect).toHaveBeenCalledWith('/ops-console/home?screen=true');
  });

  it('does not send authenticated users to an external token callback', async () => {
    vi.mocked(getLegacyThirdLoginCode).mockReturnValue('attacker-state');
    getServerSession.mockResolvedValueOnce({
      user: { id: 'u1', token: 'jwt-token-sentinel-value' },
    });

    const result = await SigninPage({
      searchParams: Promise.resolve({
        callbackUrl: 'http://attacker.example/cb?third_login_code=attacker-state',
        error: '',
      }),
    });

    expect(redirect).not.toHaveBeenCalled();
    expect(result).toEqual(expect.objectContaining({ type: LegacyThirdLoginAuthorizeBridge }));
  });

  it('keeps the NextAuth route on the dynamic provider configuration', async () => {
    const dynamicOptions = { providers: [{ id: 'wechat' }] };
    getAuthOptions.mockResolvedValueOnce(dynamicOptions);

    await import('../../../api/auth/[...nextauth]/route');

    expect(getAuthOptions).toHaveBeenCalledOnce();
    expect(nextAuth).toHaveBeenCalledWith(dynamicOptions);
  });

  it('keeps static and dynamic JWT/session callback behavior equivalent', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      result: true,
      data: { app_id: 'wechat-app', redirect_uri: 'https://example.test' },
    }))));
    const actual = await vi.importActual<typeof import('../../../../../constants/authOptions')>(
      '../../../../../constants/authOptions',
    );
    const dynamicOptions = await actual.getAuthOptions();
    const jwtArgs = {
      token: {},
      user: { id: 'u1', username: 'tester', token: 'token' },
      account: { provider: 'credentials' },
    };
    const sessionArgs = {
      session: { user: {} },
      token: {
        id: 'u1',
        username: 'tester',
        token: 'token',
        locale: 'en',
        timezone: 'Asia/Shanghai',
      },
    };

    expect(await Reflect.apply(
      dynamicOptions.callbacks!.jwt!,
      undefined,
      [structuredClone(jwtArgs)],
    )).toEqual(await Reflect.apply(
      actual.authOptions.callbacks!.jwt!,
      undefined,
      [structuredClone(jwtArgs)],
    ));
    expect(await Reflect.apply(
      dynamicOptions.callbacks!.session!,
      undefined,
      [structuredClone(sessionArgs)],
    )).toEqual(await Reflect.apply(
      actual.authOptions.callbacks!.session!,
      undefined,
      [structuredClone(sessionArgs)],
    ));
  });
});
