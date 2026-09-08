import React from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import Cookies from 'js-cookie';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { UserInfoProvider, useUserInfoContext } from '@/context/userInfo';

const mocks = vi.hoisted(() => ({
  getLoginInfo: vi.fn(),
  sessionUser: {
    id: 'admin',
    username: 'admin',
  },
}));

vi.mock('next-auth/react', () => ({
  useSession: () => ({
    status: 'authenticated',
    data: { user: mocks.sessionUser },
  }),
}));

vi.mock('@/context/auth', () => ({
  useAuth: () => ({ isCheckingAuth: false }),
}));

vi.mock('@/utils/request', () => ({
  default: () => ({ get: mocks.getLoginInfo }),
}));

const defaultGroup = { id: '1', name: 'Default' };
const kentGroup = { id: '2', name: 'Kent' };

const loginInfo = (userId: string, username: string, groups = [defaultGroup, kentGroup]) => ({
  group_list: groups,
  group_tree: groups,
  roles: [],
  is_superuser: true,
  is_first_login: false,
  user_id: userId,
  display_name: username,
  username,
});

const Probe = () => {
  const { loading, selectedGroup, username } = useUserInfoContext();

  return (
    <>
      <span data-testid="loading">{String(loading)}</span>
      <span data-testid="selected-group">{selectedGroup?.name || ''}</span>
      <span data-testid="username">{username}</span>
    </>
  );
};

const renderProvider = () => render(
  <UserInfoProvider>
    <Probe />
  </UserInfoProvider>,
);

const clearPreferenceCookies = () => {
  Cookies.remove('current_team');
  Cookies.remove('current_team_owner');
};

beforeEach(() => {
  clearPreferenceCookies();
  mocks.getLoginInfo.mockReset();
  mocks.sessionUser.id = 'admin';
  mocks.sessionUser.username = 'admin';
});

afterEach(() => {
  cleanup();
  clearPreferenceCookies();
  vi.clearAllMocks();
});

describe('UserInfoProvider account-scoped current team', () => {
  it('does not restore the previous account team when the new account can also access it', async () => {
    Cookies.set('current_team', kentGroup.id);
    Cookies.set('current_team_owner', 'kent');
    mocks.getLoginInfo.mockResolvedValue(loginInfo('admin', 'admin'));

    renderProvider();

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false');
    });
    expect(screen.getByTestId('username').textContent).toBe('admin');
    expect(screen.getByTestId('selected-group').textContent).toBe('Default');
    expect(Cookies.get('current_team')).toBe(defaultGroup.id);
    expect(Cookies.get('current_team_owner')).toBe('admin');
  });

  it('restores an accessible team when the preference belongs to the same account', async () => {
    Cookies.set('current_team', kentGroup.id);
    Cookies.set('current_team_owner', 'admin');
    mocks.getLoginInfo.mockResolvedValue(loginInfo('admin', 'admin'));

    renderProvider();

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false');
    });
    expect(screen.getByTestId('selected-group').textContent).toBe('Kent');
    expect(Cookies.get('current_team')).toBe(kentGroup.id);
    expect(Cookies.get('current_team_owner')).toBe('admin');
  });

  it('falls back to the default team when the remembered team is no longer accessible', async () => {
    Cookies.set('current_team', kentGroup.id);
    Cookies.set('current_team_owner', 'admin');
    mocks.getLoginInfo.mockResolvedValue(loginInfo('admin', 'admin', [defaultGroup]));

    renderProvider();

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false');
    });
    expect(screen.getByTestId('selected-group').textContent).toBe('Default');
    expect(Cookies.get('current_team')).toBe(defaultGroup.id);
    expect(Cookies.get('current_team_owner')).toBe('admin');
  });

  it('reloads and hides the old team while an authenticated session changes account', async () => {
    Cookies.set('current_team', kentGroup.id);
    Cookies.set('current_team_owner', 'kent');
    mocks.sessionUser.id = 'kent';
    mocks.sessionUser.username = 'kent';
    mocks.getLoginInfo.mockResolvedValueOnce(loginInfo('kent', 'kent', [kentGroup]));

    const view = renderProvider();

    await waitFor(() => {
      expect(screen.getByTestId('selected-group').textContent).toBe('Kent');
    });

    let resolveAdminLoginInfo: ((value: ReturnType<typeof loginInfo>) => void) | undefined;
    mocks.getLoginInfo.mockImplementationOnce(() => new Promise((resolve) => {
      resolveAdminLoginInfo = resolve;
    }));
    mocks.sessionUser.id = 'admin';
    mocks.sessionUser.username = 'admin';

    view.rerender(
      <UserInfoProvider>
        <Probe />
      </UserInfoProvider>,
    );

    expect(screen.getByTestId('loading').textContent).toBe('true');
    expect(screen.getByTestId('selected-group').textContent).toBe('');

    resolveAdminLoginInfo?.(loginInfo('admin', 'admin'));

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false');
    });
    expect(mocks.getLoginInfo).toHaveBeenCalledTimes(2);
    expect(screen.getByTestId('selected-group').textContent).toBe('Default');
    expect(Cookies.get('current_team_owner')).toBe('admin');
  });

  it('ignores a late login_info response from the previous account', async () => {
    mocks.sessionUser.id = 'kent';
    mocks.sessionUser.username = 'kent';
    let resolveKentLoginInfo: ((value: ReturnType<typeof loginInfo>) => void) | undefined;
    mocks.getLoginInfo.mockImplementationOnce(() => new Promise((resolve) => {
      resolveKentLoginInfo = resolve;
    }));

    const view = renderProvider();

    await waitFor(() => {
      expect(mocks.getLoginInfo).toHaveBeenCalledTimes(1);
    });

    mocks.getLoginInfo.mockResolvedValueOnce(loginInfo('admin', 'admin'));
    mocks.sessionUser.id = 'admin';
    mocks.sessionUser.username = 'admin';
    view.rerender(
      <UserInfoProvider>
        <Probe />
      </UserInfoProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('selected-group').textContent).toBe('Default');
    });

    resolveKentLoginInfo?.(loginInfo('kent', 'kent', [kentGroup]));

    await waitFor(() => {
      expect(screen.getByTestId('username').textContent).toBe('admin');
    });
    expect(screen.getByTestId('selected-group').textContent).toBe('Default');
    expect(Cookies.get('current_team_owner')).toBe('admin');
  });
});
