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

  it('父分组去掉后，原来的页面还在菜单里时进入该页面', () => {
    pathname = '/system-manager/user';
    vi.mocked(usePermissions).mockReturnValue({
      menus: [
        child('集成实例', 'integration_instance', '/system-manager/integration-center'),
        child('组织架构', 'user_group', '/system-manager/user/structure'),
      ],
      loading: false,
      permissions: {},
      hasPermission: () => true,
    });

    renderHook(() => useRedirectFirstChild());

    expect(replace).toHaveBeenCalledWith('/system-manager/user/structure?');
  });

  it('页面被拍成一级菜单后，直接打开该页面时留在原地', () => {
    pathname = '/system-manager/user/structure';
    vi.mocked(usePermissions).mockReturnValue({
      menus: [
        child('集成实例', 'integration_instance', '/system-manager/integration-center'),
        child('组织架构', 'user_group', '/system-manager/user/structure'),
      ],
      loading: false,
      permissions: {},
      hasPermission: () => true,
    });

    renderHook(() => useRedirectFirstChild());

    expect(replace).not.toHaveBeenCalled();
  });

  it('原来的页面挂在其它目录下时仍然进入该页面', () => {
    pathname = '/system-manager/user';
    vi.mocked(usePermissions).mockReturnValue({
      menus: [
        child('集成实例', 'integration_instance', '/system-manager/integration-center'),
        {
          title: '其它',
          name: 'other',
          url: '',
          icon: '',
          operation: ['View'],
          isDirectory: true,
          children: [child('组织架构', 'user_group', '/system-manager/user/structure')],
        },
      ],
      loading: false,
      permissions: {},
      hasPermission: () => true,
    });

    renderHook(() => useRedirectFirstChild());

    expect(replace).toHaveBeenCalledWith('/system-manager/user/structure?');
  });

  it('当前地址在仍存在的页面下面时留在原地', () => {
    pathname = '/system-manager/channel/detail/settings';
    vi.mocked(usePermissions).mockReturnValue({
      menus: [child('通知渠道', 'channel_list', '/system-manager/channel')],
      loading: false,
      permissions: {},
      hasPermission: () => true,
    });

    renderHook(() => useRedirectFirstChild());

    expect(replace).not.toHaveBeenCalled();
  });

  it('请求的页面已经不在菜单里时进入当前应用的第一个页面', () => {
    pathname = '/system-manager/user';
    vi.mocked(usePermissions).mockReturnValue({
      menus: [
        child('集成实例', 'integration_instance', '/system-manager/integration-center'),
        child('凭据管理', 'credential', '/system-manager/credential'),
      ],
      loading: false,
      permissions: {},
      hasPermission: () => true,
    });

    renderHook(() => useRedirectFirstChild());

    expect(replace).toHaveBeenCalledWith('/system-manager/integration-center?');
  });

  it('菜单还没加载时停在当前地址', () => {
    pathname = '/system-manager/user';
    vi.mocked(usePermissions).mockReturnValue({
      menus: [],
      loading: true,
      permissions: {},
      hasPermission: () => true,
    });

    renderHook(() => useRedirectFirstChild());

    expect(replace).not.toHaveBeenCalled();
  });
});
