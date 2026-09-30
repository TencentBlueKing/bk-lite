import React, { useEffect, useState } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import AuthProvider, { useAuth } from '@/context/auth';
import { emitSessionExpired, isSessionExpiredState, resetSessionExpiredState } from '@/utils/sessionExpiry';

const mocks = vi.hoisted(() => ({
  messageSuccess: vi.fn(),
  publishAuthRecovery: vi.fn(() => ({
    version: 1 as const,
    eventId: 'local-login-event',
    occurredAt: Date.now(),
  })),
  recoverAuthWithRetry: vi.fn(),
  confirmAuthStillValid: vi.fn(),
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
    confirmAuthStillValid: mocks.confirmAuthStillValid,
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

const TokenProbe = () => {
  const { token } = useAuth();
  return <span>token:{token}</span>;
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
  mocks.confirmAuthStillValid.mockReset();
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
    expect(mocks.confirmAuthStillValid).not.toHaveBeenCalled();
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
    expect(mocks.confirmAuthStillValid).not.toHaveBeenCalled();

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

  it('keeps an already mounted page and its draft when the session is actually expired', async () => {
    mocks.recoverAuthWithRetry.mockResolvedValue(validRecovery);
    mocks.confirmAuthStillValid.mockResolvedValue({ status: 'unavailable' });

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
    expect(isSessionExpiredState()).toBe(true);
    expect(mocks.confirmAuthStillValid).toHaveBeenCalledTimes(1);
    expect(
      (screen.getByRole('textbox', { name: 'draft' }) as HTMLInputElement).value,
    ).toBe('unfinished alert filter');

    fireEvent.click(screen.getByRole('button', { name: 'complete-login' }));

    await waitFor(() => {
      expect(screen.queryByText('common.sessionExpiredTitle')).toBeNull();
    });
    expect(mocks.messageSuccess).toHaveBeenCalledTimes(1);
    expect(
      (screen.getByRole('textbox', { name: 'draft' }) as HTMLInputElement).value,
    ).toBe('unfinished alert filter');
    expect(businessMountCount).toBe(1);
  });

  it('does not open the login overlay when a warm 401 still has a valid session', async () => {
    mocks.recoverAuthWithRetry.mockResolvedValue(validRecovery);
    mocks.confirmAuthStillValid.mockResolvedValue({
      status: 'recovered',
      user: {
        ...validRecovery.user,
        token: 'probed-token',
      },
    });

    render(
      <AuthProvider>
        <BusinessPage />
        <TokenProbe />
      </AuthProvider>,
    );

    const draft = await screen.findByRole('textbox', { name: 'draft' });
    fireEvent.change(draft, { target: { value: 'unfinished alert filter' } });
    expect(screen.getByText('token:fresh-backend-token')).toBeTruthy();

    act(() => {
      emitSessionExpired({ reason: 'test-warm-spurious-401', status: 401 });
    });

    await waitFor(() => {
      expect(screen.getByText('token:probed-token')).toBeTruthy();
    });
    expect(mocks.confirmAuthStillValid).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('common.sessionExpiredTitle')).toBeNull();
    expect(isSessionExpiredState()).toBe(false);
    expect(mocks.messageSuccess).not.toHaveBeenCalled();
    expect(
      (screen.getByRole('textbox', { name: 'draft' }) as HTMLInputElement).value,
    ).toBe('unfinished alert filter');
    expect(businessMountCount).toBe(1);
  });

  it('coalesces concurrent warm 401s into one probe before opening the overlay', async () => {
    mocks.recoverAuthWithRetry.mockResolvedValue(validRecovery);
    let resolveConfirm: ((value: { status: 'unavailable' }) => void) | undefined;
    mocks.confirmAuthStillValid.mockImplementation(
      () => new Promise((resolve) => {
        resolveConfirm = resolve;
      }),
    );

    render(
      <AuthProvider>
        <BusinessPage />
      </AuthProvider>,
    );

    await screen.findByRole('textbox', { name: 'draft' });

    act(() => {
      emitSessionExpired({ reason: 'test-warm-401-a', status: 401 });
      emitSessionExpired({ reason: 'test-warm-401-b', status: 401 });
    });

    await waitFor(() => {
      expect(mocks.confirmAuthStillValid).toHaveBeenCalledTimes(1);
    });
    expect(screen.queryByText('common.sessionExpiredTitle')).toBeNull();
    expect(isSessionExpiredState()).toBe(false);

    await act(async () => {
      resolveConfirm?.({ status: 'unavailable' });
    });

    await waitFor(() => {
      expect(screen.getByText('common.sessionExpiredTitle')).toBeTruthy();
    });
    expect(mocks.confirmAuthStillValid).toHaveBeenCalledTimes(1);
    expect(isSessionExpiredState()).toBe(true);
  });

  it('opens the login overlay when the warm probe sees a different account', async () => {
    mocks.recoverAuthWithRetry.mockResolvedValue(validRecovery);
    mocks.confirmAuthStillValid.mockResolvedValue({ status: 'account-changed' });

    render(
      <AuthProvider>
        <BusinessPage />
        <TokenProbe />
      </AuthProvider>,
    );

    await screen.findByText('token:fresh-backend-token');

    act(() => {
      emitSessionExpired({ reason: 'test-warm-account-changed', status: 401 });
    });

    await waitFor(() => {
      expect(screen.getByText('common.sessionExpiredTitle')).toBeTruthy();
    });
    expect(screen.getByText('token:fresh-backend-token')).toBeTruthy();
    expect(mocks.messageSuccess).not.toHaveBeenCalled();
    expect(businessMountCount).toBe(1);
  });
});
