import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { MenuItem } from '@/types/index';
import AppManageLayout from '../layout';

let pathname = '/system-manager/application/manage/basic';
let search = 'clientId=demo';

vi.mock('next/navigation', () => ({
  usePathname: () => pathname,
  useSearchParams: () => new URLSearchParams(search),
}));

vi.mock('next/link', () => ({
  default: ({
    href,
    children,
  }: {
    href: string;
    children: React.ReactNode;
  }) => <a href={href}>{children}</a>,
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('@/components/icon', () => ({
  default: ({ type }: { type: string }) => <span data-testid={`icon-${type}`} />,
}));

vi.mock('@/components/ellipsis-with-tooltip', () => ({
  default: ({ text }: { text: React.ReactNode }) => <span>{text}</span>,
}));

vi.mock('@/app/system-manager/api/user', () => ({
  useUserApi: () => ({
    getClientDetail: vi.fn().mockResolvedValue({
      name: 'demo',
      display_name: '演示应用',
      description: '应用说明',
    }),
  }),
}));

const menus: MenuItem[] = [
  {
    name: 'application_manage',
    title: '应用管理',
    url: '/system-manager/application/manage',
    icon: 'app',
    operation: [],
    children: [
      {
        name: 'basic',
        title: '基本信息',
        url: '/system-manager/application/manage/basic',
        icon: 'info',
        operation: [],
      },
      {
        name: 'oauth',
        title: 'OAuth',
        url: '/system-manager/application/manage/oauth',
        icon: 'key',
        operation: [],
      },
    ],
  },
];

vi.mock('@/context/permissions', () => ({
  usePermissions: () => ({ menus }),
}));

afterEach(() => {
  cleanup();
  search = 'clientId=demo';
  pathname = '/system-manager/application/manage/basic';
});

describe('system-manager application manage screen mode', () => {
  it('keeps the self-mounted side menu and page header without screen', async () => {
    render(
      <AppManageLayout>
        管理正文
      </AppManageLayout>,
    );

    expect(await screen.findByRole('link', { name: /基本信息/ })).not.toBeNull();
    expect(screen.getByRole('link', { name: /OAuth/ })).not.toBeNull();
    expect(await screen.findByText('演示应用')).not.toBeNull();
    expect(screen.getByText('管理正文')).not.toBeNull();
  });

  it('hides the self-mounted side menu in screen mode and keeps the page header', async () => {
    search = 'clientId=demo&screen=true';

    render(
      <AppManageLayout>
        管理正文
      </AppManageLayout>,
    );

    expect(await screen.findByText('管理正文')).not.toBeNull();
    expect(await screen.findByText('演示应用')).not.toBeNull();
    expect(screen.queryByRole('link', { name: /基本信息/ })).toBeNull();
    expect(screen.queryByRole('link', { name: /OAuth/ })).toBeNull();
  });
});
