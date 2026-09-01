import React from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { PermissionsProvider, usePermissions } from '@/context/permissions';

let pathname = '/cmdb/assetOverview';

vi.mock('next/navigation', () => ({
  usePathname: () => pathname,
}));

const { configMenus, getUserMenus, menuFetch } = vi.hoisted(() => {
  const menuFetch = { count: 0 };
  return {
    menuFetch,
    configMenus: [
      {
        title: '视图',
        name: 'asset_views',
        url: '/cmdb/assetOverview',
        icon: '',
        operation: ['View'],
      },
      {
        title: '搜索',
        name: 'asset_search',
        url: '/cmdb/assetSearch',
        icon: '',
        operation: ['View'],
      },
      {
        title: '用户',
        name: 'User&Group',
        url: '/system-manager/user',
        icon: '',
        operation: ['View'],
      },
    ],
    getUserMenus: async (url: string, config?: { params?: { name?: string } }) => {
      if (url.includes('get_user_menus')) {
        menuFetch.count += 1;
        const name = config?.params?.name;
        if (name === 'cmdb') {
          return [
            { name: 'asset_views', operation: ['View'] },
            { name: 'asset_search', operation: ['View'] },
          ];
        }
        if (name === 'system-manager') {
          return [{ name: 'User&Group', operation: ['View'] }];
        }
        return [];
      }
      if (url.includes('custom_menu_group')) {
        return { is_build_in: true };
      }
      throw new Error(`unexpected ${url}`);
    },
  };
});

vi.mock('@/context/menus', () => ({
  useMenus: () => ({
    loading: false,
    configMenus,
  }),
}));

vi.mock('@/utils/request', () => ({
  default: () => ({
    isLoading: false,
    get: getUserMenus,
  }),
}));

const Probe = () => {
  const { loading, hasPermission } = usePermissions();
  return (
    <>
      <span data-testid="loading">{String(loading)}</span>
      <span data-testid="cmdb">{String(hasPermission('/cmdb/assetOverview'))}</span>
      <span data-testid="setting">{String(hasPermission('/system-manager/user'))}</span>
    </>
  );
};

afterEach(() => {
  cleanup();
  pathname = '/cmdb/assetOverview';
  menuFetch.count = 0;
});

describe('PermissionsProvider same-tab app switch', () => {
  it('does not expose the previous app permissions as a finished deny while switching to Setting', async () => {
    const { rerender } = render(
      <PermissionsProvider>
        <Probe />
      </PermissionsProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false');
    });
    expect(screen.getByTestId('cmdb').textContent).toBe('true');
    expect(screen.getByTestId('setting').textContent).toBe('false');

    pathname = '/system-manager/user';
    rerender(
      <PermissionsProvider>
        <Probe />
      </PermissionsProvider>,
    );

    expect(screen.getByTestId('loading').textContent).toBe('true');

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false');
    });
    expect(screen.getByTestId('setting').textContent).toBe('true');
  });

  it('does not go back to loading when switching menus inside the same app', async () => {
    const { rerender } = render(
      <PermissionsProvider>
        <Probe />
      </PermissionsProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false');
    });
    const fetchesAfterFirstApp = menuFetch.count;
    expect(fetchesAfterFirstApp).toBeGreaterThan(0);

    pathname = '/cmdb/assetSearch';
    rerender(
      <PermissionsProvider>
        <Probe />
      </PermissionsProvider>,
    );

    expect(screen.getByTestId('loading').textContent).toBe('false');
    expect(menuFetch.count).toBe(fetchesAfterFirstApp);
    expect(screen.getByTestId('cmdb').textContent).toBe('true');
  });

  it('does not keep the console spinning on the no-permission page', async () => {
    pathname = '/no-permission';
    render(
      <PermissionsProvider>
        <Probe />
      </PermissionsProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false');
    });
  });
});
