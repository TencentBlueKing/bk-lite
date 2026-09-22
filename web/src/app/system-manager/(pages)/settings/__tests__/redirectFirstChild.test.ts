// @vitest-environment jsdom

import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { MenuItem } from '@/types';

const replace = vi.fn();
let pathname = '/system-manager/settings';
let search = '';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace }),
  usePathname: () => pathname,
  useSearchParams: () => new URLSearchParams(search),
}));

vi.mock('@/context/permissions', () => ({
  usePermissions: vi.fn(() => ({ menus: [], loading: false })),
}));

import { usePermissions } from '@/context/permissions';
import { useRedirectFirstChild } from '@/hooks/useRedirectFirstChild';

const child = (title: string, name: string, url: string): MenuItem => ({
  title,
  name,
  url,
  icon: '',
  operation: ['View'],
});

const settingMenus = (children: MenuItem[]): MenuItem[] => [
  {
    title: '平台管理',
    name: 'Setting',
    url: '/system-manager/settings',
    icon: 'settings-fill',
    operation: ['View'],
    children,
  },
];

describe('访问 /system-manager/settings 时跳转到权限过滤后的第一个子页面', () => {
  beforeEach(() => {
    replace.mockClear();
    pathname = '/system-manager/settings';
    search = '';
  });

  it('拥有审计日志权限时进入审计日志', () => {
    vi.mocked(usePermissions).mockReturnValue({
      menus: settingMenus([
        child('审计日志', 'audit_log', '/system-manager/settings/audit-log'),
        child('错误日志', 'error_logs', '/system-manager/settings/error-logs'),
        child('API 令牌', 'api_secret_key', '/system-manager/settings/key'),
      ]),
      loading: false,
      permissions: {},
      hasPermission: () => true,
    });

    renderHook(() => useRedirectFirstChild());

    expect(replace).toHaveBeenCalledWith('/system-manager/settings/audit-log?');
  });

  it('没有审计日志权限时进入第一个有权子页面', () => {
    vi.mocked(usePermissions).mockReturnValue({
      menus: settingMenus([
        child('错误日志', 'error_logs', '/system-manager/settings/error-logs'),
        child('API 令牌', 'api_secret_key', '/system-manager/settings/key'),
      ]),
      loading: false,
      permissions: {},
      hasPermission: () => true,
    });

    renderHook(() => useRedirectFirstChild());

    expect(replace).toHaveBeenCalledWith('/system-manager/settings/error-logs?');
  });
});
