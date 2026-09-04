import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

vi.stubGlobal('ResizeObserver', ResizeObserverStub);

let chromeLayout: 'classic' | 'app-top' = 'classic';
let pathname = '/cmdb/assetOverview';

vi.mock('next/navigation', () => ({
  usePathname: () => pathname,
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('@/context/permissions', () => ({
  usePermissions: () => ({
    menus: [
      { title: '搜索', url: '/cmdb/assetSearch', name: 'search', icon: 'search-f' },
      { title: '视图', url: '/cmdb/assetOverview', name: 'asset_views', icon: 'mulu' },
    ],
  }),
}));

vi.mock('@/context/client', () => ({
  useClientData: () => ({
    clientData: [
      { name: 'opspilot', display_name: 'OpsPilot', url: '/opspilot', icon: 'opspilot', is_build_in: true },
      { name: 'ops-console', display_name: '控制台', url: '/ops-console', icon: 'ops-console', is_build_in: true },
      { name: 'cmdb', display_name: 'CMDB', url: '/cmdb', icon: 'cmdb', is_build_in: true },
      { name: 'monitor', display_name: '监控中心', url: '/monitor', icon: 'monitor', is_build_in: true },
      { name: 'log', display_name: '日志中心', url: '/log', icon: 'log', is_build_in: true },
      { name: 'alarm', display_name: '告警中心', url: '/alarm', icon: 'alarm', is_build_in: true },
    ],
    appConfigList: [],
    loading: false,
    appConfigLoading: false,
  }),
}));

vi.mock('@/context/userInfo', () => ({
  useUserInfoContext: () => ({ userId: 'u1' }),
}));

vi.mock('@/hooks/usePortalBranding', () => ({
  usePortalBranding: () => ({ portalName: 'BlueKing Lite', logoUrl: '/logo.png' }),
}));

vi.mock('@/console-layout', async () => {
  const actual = await vi.importActual<typeof import('@/console-layout')>('@/console-layout');
  return {
    ...actual,
    useConsoleLayout: () => ({ layout: chromeLayout, setLayout: vi.fn() }),
  };
});

vi.mock('@/components/icon', () => ({
  default: ({ type }: { type: string }) => <span data-testid={`icon-${type}`} />,
}));

vi.mock('@/components/notifications', () => ({
  default: () => <div data-testid="notifications" />,
}));

vi.mock('../user-info', () => ({
  default: () => <div data-testid="user-info" />,
}));

import TopMenu from '../index';

afterEach(() => {
  cleanup();
  chromeLayout = 'classic';
  pathname = '/cmdb/assetOverview';
});

describe('TopMenu chrome layouts', () => {
  it('keeps the app grid in classic layout and shows the current app menu', () => {
    render(<TopMenu />);
    expect(screen.getByTestId('icon-caidandaohang')).toBeTruthy();
    expect(screen.getByText('搜索')).toBeTruthy();
    expect(screen.getByText('视图')).toBeTruthy();
  });

  it('lists apps on the top bar and hides the grid in app-top layout', () => {
    chromeLayout = 'app-top';
    render(<TopMenu />);
    expect(screen.queryByTestId('icon-caidandaohang')).toBeNull();
    expect(screen.getByText('OpsPilot')).toBeTruthy();
    expect(screen.getByText('控制台')).toBeTruthy();
    expect(screen.getByText('CMDB')).toBeTruthy();
    expect(screen.getByText('监控中心')).toBeTruthy();
    expect(screen.getByText('日志中心')).toBeTruthy();
    expect(screen.getByText('告警中心')).toBeTruthy();
    expect(screen.getByTestId('icon-cmdb')).toBeTruthy();
    expect(screen.getByTestId('icon-monitor')).toBeTruthy();
    expect(screen.queryByText('搜索')).toBeNull();
    expect(screen.queryByText('common.more')).toBeNull();
    expect(screen.queryByText('详情')).toBeNull();
    expect(screen.getByRole('link', { name: 'CMDB' }).className).toMatch(/active/);
    expect(screen.getByRole('link', { name: '监控中心' }).className).not.toMatch(/active/);
  });

  it('keeps the stored app-top header on no-permission instead of falling back to classic', () => {
    chromeLayout = 'app-top';
    pathname = '/no-permission';
    render(<TopMenu />);
    expect(screen.queryByTestId('icon-caidandaohang')).toBeNull();
    expect(screen.getByText('CMDB')).toBeTruthy();
    expect(screen.getByText('监控中心')).toBeTruthy();
  });

  it('reserves a 200px brand column in app-top so the app strip aligns with the left rail', () => {
    chromeLayout = 'app-top';
    render(<TopMenu />);
    const brand = screen.getByTestId('app-top-brand');
    expect(brand.style.width).toBe('200px');
    expect(screen.getByText('BlueKing Lite')).toBeTruthy();
    expect(screen.getByAltText('logo')).toBeTruthy();
    expect(screen.getByText('CMDB')).toBeTruthy();
    expect(screen.getByText('监控中心')).toBeTruthy();
  });

  it('can hide portal branding when hideBrand is passed', () => {
    chromeLayout = 'app-top';
    render(<TopMenu hideBrand />);
    expect(screen.queryByText('BlueKing Lite')).toBeNull();
    expect(screen.queryByAltText('logo')).toBeNull();
    expect(screen.queryByTestId('app-top-brand')).toBeNull();
    expect(screen.getByText('CMDB')).toBeTruthy();
  });
});
