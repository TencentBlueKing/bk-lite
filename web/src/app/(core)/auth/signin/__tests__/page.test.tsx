import { beforeEach, describe, expect, it, vi } from 'vitest';

const {
  authOptions,
  getAuthOptions,
  getServerSession,
  headers,
} = vi.hoisted(() => ({
  authOptions: { session: { strategy: 'jwt' } },
  getAuthOptions: vi.fn(async () => ({ providers: [{ id: 'wechat' }] })),
  getServerSession: vi.fn(async () => null),
  headers: vi.fn(async () => new Headers()),
}));

vi.mock('@/constants/authOptions', () => ({
  authOptions,
  getAuthOptions,
}));
vi.mock('next-auth', () => ({ getServerSession }));
vi.mock('next/headers', () => ({ headers }));
vi.mock('next/navigation', () => ({ redirect: vi.fn() }));
vi.mock('../SigninClient', () => ({ default: () => null }));
vi.mock('../PopupAuthBridge', () => ({ default: () => null }));
vi.mock('@/utils/authRedirect', () => ({
  buildLegacyThirdLoginCallbackUrl: vi.fn(),
  buildThirdLoginCallbackUrl: vi.fn(),
  getLegacyThirdLoginCode: vi.fn(() => null),
  resolveThirdLoginFlag: vi.fn(() => false),
}));

import SigninPage from '../page';

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
});
