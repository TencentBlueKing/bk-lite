import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';

const replace = vi.fn();
let search = '';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace }),
  usePathname: vi.fn(() => '/'),
  useSearchParams: () => new URLSearchParams(search),
}));

vi.mock('@/context/permissions', () => ({
  usePermissions: vi.fn(() => ({ menus: [], loading: false })),
}));

const clientState = vi.hoisted(() => ({
  current: undefined as {
    clientData: Array<{ name: string; url: string }>;
    appConfigList: Array<{ name: string; url: string }>;
    loading: boolean;
    appConfigLoading: boolean;
  } | undefined,
}));

vi.mock('@/context/client', () => ({
  useOptionalClientData: () => clientState.current,
}));

import { usePathname } from 'next/navigation';
import { usePermissions } from '@/context/permissions';
import RedirectToFirstMenu from '../index';
import { PORTAL_HOME_PATH } from '@/utils/route';

describe('RedirectToFirstMenu', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    search = '';
    clientState.current = undefined;
    vi.mocked(usePathname).mockReturnValue('/');
    vi.mocked(usePermissions).mockReturnValue({
      menus: [],
      loading: false,
      permissions: {},
      hasPermission: () => false,
    });
  });

  it('redirects the portal root to the console home page', () => {
    render(<RedirectToFirstMenu />);

    expect(replace).toHaveBeenCalledWith(PORTAL_HOME_PATH);
  });

  it('redirects app landing pages to the first accessible menu', () => {
    vi.mocked(usePathname).mockReturnValue('/opspilot');
    vi.mocked(usePermissions).mockReturnValue({
      menus: [{ url: '/opspilot/studio', name: 'studio' } as any],
      loading: false,
      permissions: {},
      hasPermission: () => true,
    });

    render(<RedirectToFirstMenu />);

    expect(replace).toHaveBeenCalledWith('/opspilot/studio');
  });

  it('keeps screen when redirecting from an app landing page', () => {
    search = 'screen=true';
    vi.mocked(usePathname).mockReturnValue('/opspilot');
    vi.mocked(usePermissions).mockReturnValue({
      menus: [{ url: '/opspilot/studio', name: 'studio' } as any],
      loading: false,
      permissions: {},
      hasPermission: () => true,
    });

    render(<RedirectToFirstMenu />);

    expect(replace).toHaveBeenCalledWith('/opspilot/studio?screen=true');
  });

  it('redirects with optimistic menus even while permissions are still loading', () => {
    vi.mocked(usePathname).mockReturnValue('/log');
    vi.mocked(usePermissions).mockReturnValue({
      menus: [{ url: '/log/search', name: 'search' } as any],
      loading: true,
      permissions: {},
      hasPermission: () => false,
    });

    render(<RedirectToFirstMenu />);

    expect(replace).toHaveBeenCalledWith('/log/search');
  });

  it('does not redirect using menus from a different app', () => {
    vi.mocked(usePathname).mockReturnValue('/log');
    vi.mocked(usePermissions).mockReturnValue({
      menus: [{ url: '/cmdb/assetOverview', name: 'asset_views' } as any],
      loading: false,
      permissions: {},
      hasPermission: () => true,
    });

    render(<RedirectToFirstMenu />);

    expect(replace).not.toHaveBeenCalled();
  });

  it('opens the registered page when that page is in the loaded menu', () => {
    vi.mocked(usePathname).mockReturnValue('/cmdb');
    clientState.current = {
      clientData: [{ name: 'cmdb', url: '/cmdb/assetSearch' }],
      appConfigList: [],
      loading: false,
      appConfigLoading: false,
    };
    vi.mocked(usePermissions).mockReturnValue({
      menus: [
        { url: '/cmdb/views/k8s', name: 'k8s' } as any,
        { url: '/cmdb/assetSearch', name: 'search' } as any,
      ],
      loading: false,
      permissions: {},
      hasPermission: () => true,
    });

    render(<RedirectToFirstMenu />);

    expect(replace).toHaveBeenCalledWith('/cmdb/assetSearch');
  });

  it('opens the first menu page when the registered page is absent', () => {
    vi.mocked(usePathname).mockReturnValue('/cmdb');
    clientState.current = {
      clientData: [{ name: 'cmdb', url: '/cmdb/assetSearch' }],
      appConfigList: [],
      loading: false,
      appConfigLoading: false,
    };
    vi.mocked(usePermissions).mockReturnValue({
      menus: [{ url: '/cmdb/views/k8s', name: 'k8s' } as any],
      loading: false,
      permissions: {},
      hasPermission: () => true,
    });

    render(<RedirectToFirstMenu />);

    expect(replace).toHaveBeenCalledWith('/cmdb/views/k8s');
  });
});
