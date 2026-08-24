import React, { useEffect, useState } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import AuthProvider from '@/context/auth';
import { emitSessionExpired, resetSessionExpiredState } from '@/utils/sessionExpiry';

const mocks = vi.hoisted(() => ({
  messageSuccess: vi.fn(),
  publishAuthRecovery: vi.fn(() => ({
    version: 1 as const,
    eventId: 'local-login-event',
    occurredAt: Date.now(),
  })),
  recoverAuthWithRetry: vi.fn(),
  routerPush: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  usePathname: () => '/alarm/alarms',
  useRouter: () => ({ push: mocks.routerPush }),
}));

vi.mock('next-auth/react', () => ({
  useSession: () => ({
    status: 'authenticated',
    data: {
      user: {
        id: '1',
        username: 'admin',
        token: 'stale-next-auth-token',
        locale: 'en',
        timezone: 'Asia/Shanghai',
      },
    },
  }),
  signIn: vi.fn(),
}));

vi.mock('antd', () => ({
  App: {
    useApp: () => ({ message: { success: mocks.messageSuccess } }),
  },
  Spin: () => <div>loading-auth</div>,
}));

vi.mock('@/context/locale', () => ({
  useLocale: () => ({ setLocale: vi.fn() }),
}));

vi.mock('@/theme', () => ({
  useThemeMode: () => ({ mode: 'light' }),
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('@/utils/authRecoveryChannel', () => ({
  publishAuthRecovery: mocks.publishAuthRecovery,
  subscribeAuthRecovery: () => () => undefined,
}));

vi.mock('@/utils/authRecovery', async () => {
  const actual = await vi.importActual<typeof import('@/utils/authRecovery')>(
    '@/utils/authRecovery',
  );
  return {
    ...actual,
    recoverAuthWithRetry: mocks.recoverAuthWithRetry,
  };
});

vi.mock('@/app/(core)/auth/signin/SigninClient', () => ({
  default: ({ onAuthenticated }: { onAuthenticated?: () => void }) => (
    <button type="button" onClick={onAuthenticated}>
      complete-login
    </button>
  ),
}));

let businessMountCount = 0;

const BusinessPage = () => {
  const [draft, setDraft] = useState('');

  useEffect(() => {
    businessMountCount += 1;
  }, []);

  return (
    <label>
      business-page
      <input
        aria-label="draft"
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
      />
    </label>
  );
};

const validRecovery = {
  status: 'recovered' as const,
  user: {
    id: '1',
    username: 'admin',
    token: 'fresh-backend-token',
    locale: 'en',
    timezone: 'Asia/Shanghai',
  },
};

beforeEach(() => {
  businessMountCount = 0;
  resetSessionExpiredState();
  mocks.recoverAuthWithRetry.mockReset();
  mocks.messageSuccess.mockReset();
  mocks.publishAuthRecovery.mockClear();
  mocks.routerPush.mockReset();

  vi.stubGlobal('fetch', vi.fn(async () => Response.json({ result: false })));
});

afterEach(() => {
  cleanup();
  resetSessionExpiredState();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe('AuthProvider protected content lifecycle', () => {
  it('keeps a cold page unmounted until backend authentication recovers', async () => {
    mocks.recoverAuthWithRetry
      .mockResolvedValueOnce({ status: 'unavailable' })
      .mockResolvedValueOnce(validRecovery);

    render(
      <AuthProvider>
        <BusinessPage />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText('common.sessionExpiredTitle')).toBeTruthy();
    });
    expect(screen.queryByText('business-page')).toBeNull();
    expect(businessMountCount).toBe(0);

    fireEvent.click(screen.getByRole('button', { name: 'complete-login' }));

    await waitFor(() => {
      expect(screen.getByText('business-page')).toBeTruthy();
    });
    expect(screen.queryByText('common.sessionExpiredTitle')).toBeNull();
    expect(businessMountCount).toBe(1);
    expect(mocks.recoverAuthWithRetry).toHaveBeenCalledTimes(2);
  });

  it('does not let an in-flight expired probe swallow a successful relogin', async () => {
    let resolveStaleProbe: ((value: typeof validRecovery | { status: 'unavailable' }) => void) | undefined;
    const staleProbe = new Promise<typeof validRecovery | { status: 'unavailable' }>((resolve) => {
      resolveStaleProbe = resolve;
    });

    mocks.recoverAuthWithRetry
      .mockImplementationOnce(() => staleProbe)
      .mockResolvedValueOnce(validRecovery);

    render(
      <AuthProvider>
        <BusinessPage />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(mocks.recoverAuthWithRetry).toHaveBeenCalledTimes(1);
    });

    act(() => {
      emitSessionExpired({ reason: 'test-stale-probe-during-relogin', status: 401 });
    });

    await waitFor(() => {
      expect(screen.getByText('common.sessionExpiredTitle')).toBeTruthy();
    });

    fireEvent.click(screen.getByRole('button', { name: 'complete-login' }));

    await waitFor(() => {
      expect(mocks.recoverAuthWithRetry).toHaveBeenCalledTimes(2);
    });

    await waitFor(() => {
      expect(screen.getByText('business-page')).toBeTruthy();
    });
    expect(screen.queryByText('common.sessionExpiredTitle')).toBeNull();

    await act(async () => {
      resolveStaleProbe?.({ status: 'unavailable' });
    });

    expect(screen.getByText('business-page')).toBeTruthy();
    expect(screen.queryByText('common.sessionExpiredTitle')).toBeNull();
  });

  it('keeps an already mounted page and its draft during reauthentication', async () => {
    mocks.recoverAuthWithRetry.mockResolvedValue(validRecovery);

    render(
      <AuthProvider>
        <BusinessPage />
      </AuthProvider>,
    );

    const draft = await screen.findByRole('textbox', { name: 'draft' });
    fireEvent.change(draft, { target: { value: 'unfinished alert filter' } });
    expect(businessMountCount).toBe(1);

    act(() => {
      emitSessionExpired({ reason: 'test-warm-page-expiry', status: 401 });
    });

    await waitFor(() => {
      expect(screen.getByText('common.sessionExpiredTitle')).toBeTruthy();
    });
    expect(
      (screen.getByRole('textbox', { name: 'draft' }) as HTMLInputElement).value,
    ).toBe('unfinished alert filter');

    fireEvent.click(screen.getByRole('button', { name: 'complete-login' }));

    await waitFor(() => {
      expect(screen.queryByText('common.sessionExpiredTitle')).toBeNull();
    });
    expect(
      (screen.getByRole('textbox', { name: 'draft' }) as HTMLInputElement).value,
    ).toBe('unfinished alert filter');
    expect(businessMountCount).toBe(1);
  });
});
