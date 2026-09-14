import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';
import type { MenuItem } from '@/types';

const replace = vi.fn();
let search = '';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => new URLSearchParams(search),
}));

vi.mock('@/context/permissions', () => ({
  usePermissions: vi.fn(() => ({ menus: [], loading: false })),
}));

import { usePermissions } from '@/context/permissions';
import SettingsRedirect, { findSettingsTargetUrl } from './settings-redirect';

const settingsMenu = (children: MenuItem[]): MenuItem[] => [
  {
    title: 'Settings',
    name: 'patch_settings',
    url: '/patch-manager/settings',
    icon: 'settings-fill',
    operation: [],
    children,
  },
];

const sourceAndScanMenus = settingsMenu([
  { title: 'Sources', name: 'patch_source', url: '/patch-manager/settings/sources', icon: '', operation: [] },
  { title: 'Scan', name: 'patch_scan_setting', url: '/patch-manager/settings/scan', icon: '', operation: [] },
]);

describe('findSettingsTargetUrl', () => {
  it('prefers the first accessible child in menu order', () => {
    expect(findSettingsTargetUrl(sourceAndScanMenus)).toBe('/patch-manager/settings/sources');
  });

  it('redirects scan-only users to scan settings', () => {
    expect(findSettingsTargetUrl(settingsMenu([
      { title: 'Scan', name: 'patch_scan_setting', url: '/patch-manager/settings/scan', icon: '', operation: [] },
    ]))).toBe('/patch-manager/settings/scan');
  });
});

describe('SettingsRedirect', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    search = '';
    vi.mocked(usePermissions).mockReturnValue({
      menus: sourceAndScanMenus,
      loading: false,
      permissions: {},
      hasPermission: () => true,
    });
  });

  it('keeps the assembled target when the current query is ordinary', () => {
    render(<SettingsRedirect />);

    expect(replace).toHaveBeenCalledWith('/patch-manager/settings/sources');
  });

  it('adds screen when redirecting from a screen-mode query', () => {
    search = 'screen=true';

    render(<SettingsRedirect />);

    expect(replace).toHaveBeenCalledWith('/patch-manager/settings/sources?screen=true');
  });
});
