import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import SideMenuLayout from '../index';
import type { MenuItem } from '@/types/index';

let pathname = '/cmdb/assetData/detail/baseInfo';
let search = 'model_id=host';

vi.mock('next/navigation', () => ({
  usePathname: () => pathname,
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(search),
}));

vi.mock('next/link', () => ({
  default: ({
    href,
    children,
    ...rest
  }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('@/components/icon', () => ({
  default: ({ type }: { type: string }) => <span data-testid={`icon-${type}`} />,
}));

vi.mock('@/app/cmdb/api', () => ({
  useInstanceApi: () => ({
    getTopoThemes: vi.fn().mockResolvedValue({ themes: [] }),
  }),
}));

const menus: MenuItem[] = [
  {
    name: 'asset_data',
    title: '资产数据',
    url: '/cmdb/assetData',
    icon: 'cmdb',
    operation: [],
    children: [
      {
        name: 'asset_attr',
        title: '属性',
        url: '/cmdb/assetData/detail/baseInfo',
        icon: 'attr',
        operation: [],
      },
      {
        name: 'asset_relationships',
        title: '关系',
        url: '/cmdb/assetData/detail/relationships',
        icon: 'rel',
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
  search = 'model_id=host';
  pathname = '/cmdb/assetData/detail/baseInfo';
});

describe('CMDB asset detail side menu screen mode', () => {
  it('keeps the local side menu without screen', async () => {
    render(
      <SideMenuLayout intro={<span>实例简介</span>} topSection={<span>资产页头</span>} showBackButton>
        实例正文
      </SideMenuLayout>,
    );

    expect(await screen.findByRole('link', { name: /属性/ })).not.toBeNull();
    expect(screen.getByRole('link', { name: /关系/ })).not.toBeNull();
    expect(screen.getByText('实例简介')).not.toBeNull();
    expect(screen.getByText('资产页头')).not.toBeNull();
    expect(screen.getByText('实例正文')).not.toBeNull();
  });

  it('hides the local side column in screen mode and keeps the body', async () => {
    search = 'model_id=host&screen=true';

    render(
      <SideMenuLayout intro={<span>实例简介</span>} topSection={<span>资产页头</span>} showBackButton>
        实例正文
      </SideMenuLayout>,
    );

    expect(await screen.findByText('实例正文')).not.toBeNull();
    expect(screen.getByText('资产页头')).not.toBeNull();
    expect(screen.queryByRole('link', { name: /属性/ })).toBeNull();
    expect(screen.queryByRole('link', { name: /关系/ })).toBeNull();
    expect(screen.queryByText('实例简介')).toBeNull();
  });
});
