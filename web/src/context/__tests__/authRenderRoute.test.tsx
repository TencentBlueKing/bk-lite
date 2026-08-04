import React from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import AuthProvider from '@/context/auth';

const nativeFetch = vi.fn();

vi.mock('next/navigation', () => ({
  usePathname: () => '/ops-analysis/render/execution/7',
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock('next-auth/react', () => ({
  useSession: () => ({
    status: 'authenticated',
    data: {
      user: {
        id: 'render:7',
        username: 'render:7',
        token: 'scoped-render-session',
      },
    },
  }),
  signIn: vi.fn(),
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

vi.mock('@/app/(core)/auth/signin/SigninClient', () => ({
  default: () => null,
}));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe('AuthProvider render route', () => {
  it('does not probe or replace ordinary login state for a scoped render session', async () => {
    vi.stubGlobal('fetch', nativeFetch);
    vi.stubGlobal('localStorage', {
      getItem: vi.fn(() => 'en'),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
      key: vi.fn(),
      length: 0,
    });

    render(
      <AuthProvider>
        <div>scoped-render-child</div>
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText('scoped-render-child')).toBeTruthy();
    });
    expect(nativeFetch).not.toHaveBeenCalled();
  });

  it('does not open session-expired overlay for 401 on render route', async () => {
    vi.stubGlobal('fetch', nativeFetch);
    vi.stubGlobal('localStorage', {
      getItem: vi.fn(() => 'en'),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
      key: vi.fn(),
      length: 0,
    });

    const { emitSessionExpired, resetSessionExpiredState } = await import(
      '@/utils/sessionExpiry'
    );
    resetSessionExpiredState();

    render(
      <AuthProvider>
        <div>scoped-render-child</div>
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText('scoped-render-child')).toBeTruthy();
    });

    emitSessionExpired({ reason: 'test-render-401', status: 401 });

    expect(screen.queryByText('common.sessionExpiredTitle')).toBeNull();
  });
});
