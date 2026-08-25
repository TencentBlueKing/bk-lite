import { describe, expect, it } from 'vitest';
import type { MenuItem } from '@/types';
import { findSettingsTargetUrl } from './settings-redirect';

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

describe('findSettingsTargetUrl', () => {
  it('prefers the first accessible child in menu order', () => {
    expect(findSettingsTargetUrl(settingsMenu([
      { title: 'Sources', name: 'patch_source', url: '/patch-manager/settings/sources', icon: '', operation: [] },
      { title: 'Scan', name: 'patch_scan_setting', url: '/patch-manager/settings/scan', icon: '', operation: [] },
    ]))).toBe('/patch-manager/settings/sources');
  });

  it('redirects scan-only users to scan settings', () => {
    expect(findSettingsTargetUrl(settingsMenu([
      { title: 'Scan', name: 'patch_scan_setting', url: '/patch-manager/settings/scan', icon: '', operation: [] },
    ]))).toBe('/patch-manager/settings/scan');
  });
});
