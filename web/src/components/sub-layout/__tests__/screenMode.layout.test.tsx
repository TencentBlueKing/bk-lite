import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import type { MenuItem } from '@/types/index';
import SubLayout from '@/components/sub-layout';
import LayoutSubLayout from '@/components/layout/sub-layout';

let pathname = '/monitor/integration/list/detail/configure';
let search = '';

vi.mock('next/navigation', () => ({
  usePathname: () => pathname,
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(search),
}));

vi.mock('next/link', () => ({
  default: ({
    href,
    children,
    legacyBehavior,
  }: {
    href: string;
    children: React.ReactNode;
    legacyBehavior?: boolean;
  }) => {
    if (legacyBehavior && React.isValidElement(children)) {
      return React.cloneElement(children as React.ReactElement<{ href?: string }>, { href });
    }
    return <a href={href}>{children}</a>;
  },
}));

vi.mock('@/context/permissions', () => ({
  usePermissions: () => ({ menus: [] }),
}));

vi.mock('@/components/icon', () => ({
  default: ({ type }: { type: string }) => <span data-testid={`icon-${type}`} />,
}));

const MENU_ITEMS: MenuItem[] = [
  {
    name: 'integration_configure',
    title: '配置',
    url: '/monitor/integration/list/detail/configure',
    icon: 'settings-fill',
    operation: [],
  },
  {
    name: 'integration_metric',
    title: '指标',
    url: '/monitor/integration/list/detail/metric',
    icon: 'guanli',
    operation: [],
  },
];

const layouts = [
  ['sub-layout', SubLayout],
  ['layout/sub-layout', LayoutSubLayout],
] as const;

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

afterEach(() => {
  cleanup();
  search = '';
  pathname = '/monitor/integration/list/detail/configure';
});

describe.each(layouts)('%s screen mode', (_label, Layout) => {
  it('keeps the side menu, intro, back control and page header without screen', async () => {
    render(
      <Layout
        layoutType="sideMenu"
        customMenuItems={MENU_ITEMS}
        intro={<span>对象简介</span>}
        topSection={<span>页头标题</span>}
        showBackButton
      >
        页面正文
      </Layout>,
    );

    expect(await screen.findByRole('link', { name: /配置/ })).not.toBeNull();
    expect(screen.getByRole('link', { name: /指标/ })).not.toBeNull();
    expect(screen.getByText('对象简介')).not.toBeNull();
    expect(screen.getByText('页头标题')).not.toBeNull();
    expect(screen.getByText('页面正文')).not.toBeNull();
    expect(screen.getByRole('button')).not.toBeNull();
  });

  it('hides the side column in screen mode but keeps the page header and body', async () => {
    search = 'screen=true';

    render(
      <Layout
        layoutType="sideMenu"
        customMenuItems={MENU_ITEMS}
        intro={<span>对象简介</span>}
        topSection={<span>页头标题</span>}
        showBackButton
      >
        页面正文
      </Layout>,
    );

    expect(await screen.findByText('页面正文')).not.toBeNull();
    expect(screen.getByText('页头标题')).not.toBeNull();
    expect(screen.queryByRole('link', { name: /配置/ })).toBeNull();
    expect(screen.queryByRole('link', { name: /指标/ })).toBeNull();
    expect(screen.queryByText('对象简介')).toBeNull();
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('keeps the segmented menu without screen', async () => {
    render(
      <Layout layoutType="segmented" customMenuItems={MENU_ITEMS}>
        分段正文
      </Layout>,
    );

    expect(await screen.findByText('配置')).not.toBeNull();
    expect(screen.getByText('指标')).not.toBeNull();
    expect(screen.getByText('分段正文')).not.toBeNull();
  });

  it('hides the segmented menu in screen mode and still shows the body', async () => {
    search = 'screen=true';

    render(
      <Layout layoutType="segmented" customMenuItems={MENU_ITEMS}>
        分段正文
      </Layout>,
    );

    expect(await screen.findByText('分段正文')).not.toBeNull();
    expect(screen.queryByText('配置')).toBeNull();
    expect(screen.queryByText('指标')).toBeNull();
  });
});
