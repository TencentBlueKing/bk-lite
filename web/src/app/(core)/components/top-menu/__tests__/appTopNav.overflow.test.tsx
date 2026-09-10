import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

vi.stubGlobal('ResizeObserver', ResizeObserverStub);

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('@/components/icon', () => ({
  default: ({ type }: { type: string }) => <span data-testid={`icon-${type}`} />,
}));

vi.mock('next/link', () => ({
  default: (props: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string; prefetch?: boolean }) => {
    const { children, href, onClick, ...rest } = props;
    delete rest.prefetch;
    return (
      <a href={href} onClick={onClick} {...rest}>
        {children}
      </a>
    );
  },
}));

import AppTopNav from '../appTopNav';
import type { ClientData } from '@/types/index';

const apps = [
  { name: 'opspilot', display_name: 'OpsPilot', url: '/opspilot', icon: 'opspilot', is_build_in: true },
  { name: 'cmdb', display_name: 'CMDB', url: '/cmdb', icon: 'cmdb', is_build_in: true },
  { name: 'monitor', display_name: '监控中心', url: '/monitor', icon: 'monitor', is_build_in: true },
  { name: 'alarm', display_name: '告警中心', url: '/alarm', icon: 'alarm', is_build_in: true },
] as ClientData[];

const navApps = [
  ...apps.slice(0, 2),
  { name: 'node', display_name: '节点管理', url: '/node-manager', icon: 'node', is_build_in: true },
  ...apps.slice(2),
] as ClientData[];

const setStripOverflow = (
  strip: HTMLElement,
  { scrollLeft, clientWidth, scrollWidth }: { scrollLeft: number; clientWidth: number; scrollWidth: number },
) => {
  Object.defineProperty(strip, 'scrollLeft', { configurable: true, value: scrollLeft });
  Object.defineProperty(strip, 'clientWidth', { configurable: true, value: clientWidth });
  Object.defineProperty(strip, 'scrollWidth', { configurable: true, value: scrollWidth });
  act(() => {
    strip.dispatchEvent(new Event('scroll'));
  });
};

afterEach(() => {
  cleanup();
});

describe('AppTopNav overflow arrows', () => {
  it('hides arrows when the strip does not overflow', () => {
    render(<AppTopNav apps={apps} pathname="/cmdb" />);
    expect(screen.queryByRole('button', { name: 'common.scrollAppsLeft' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'common.scrollAppsRight' })).toBeNull();
    expect(screen.queryByText('common.more')).toBeNull();
    expect(screen.queryByText('详情')).toBeNull();
  });

  it('shows a right arrow when more apps sit past the visible edge', async () => {
    const { container } = render(<AppTopNav apps={apps} pathname="/cmdb" />);
    const strip = container.querySelector('[data-app-strip]') as HTMLElement;
    setStripOverflow(strip, { scrollLeft: 0, clientWidth: 320, scrollWidth: 900 });

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'common.scrollAppsRight' })).toBeTruthy();
    });
    expect(screen.queryByRole('button', { name: 'common.scrollAppsLeft' })).toBeNull();
    expect(screen.getByText('告警中心')).toBeTruthy();
  });

  it('scrolls the strip when the right arrow is clicked', async () => {
    const { container } = render(<AppTopNav apps={apps} pathname="/cmdb" />);
    const strip = container.querySelector('[data-app-strip]') as HTMLElement;
    const scrollBy = vi.fn();
    strip.scrollBy = scrollBy;
    setStripOverflow(strip, { scrollLeft: 0, clientWidth: 320, scrollWidth: 900 });

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'common.scrollAppsRight' })).toBeTruthy();
    });
    fireEvent.click(screen.getByRole('button', { name: 'common.scrollAppsRight' }));
    expect(scrollBy).toHaveBeenCalledWith({ left: 224, behavior: 'smooth' });
  });
});

describe('AppTopNav active app click', () => {
  const menus = [
    { title: '搜索', url: '/cmdb/assetSearch', name: 'search', icon: '', operation: [] },
    { title: '视图', url: '/cmdb/assetOverview', name: 'asset_views', icon: '', operation: [] },
  ];

  it('does not re-enter the CMDB landing stub while already inside CMDB', () => {
    render(<AppTopNav apps={navApps} pathname="/cmdb/assetOverview" menus={menus} />);
    const cmdb = screen.getByRole('link', { name: 'CMDB' });
    expect(cmdb.getAttribute('href')).toBe('/cmdb/assetSearch');
    expect(cmdb.getAttribute('aria-current')).toBe('page');

    const event = fireEvent.click(cmdb);
    expect(event).toBe(false);
  });

  it('still navigates when clicking a different app', () => {
    render(<AppTopNav apps={navApps} pathname="/cmdb/assetOverview" menus={menus} />);
    const monitor = screen.getByRole('link', { name: '监控中心' });
    expect(monitor.getAttribute('href')).toBe('/monitor');
    expect(monitor.getAttribute('aria-current')).toBeNull();
    expect(fireEvent.click(monitor)).toBe(true);
  });

  it('does not re-enter 节点管理 while already on a sibling page', () => {
    const nodeMenus = [
      {
        title: '云区域',
        url: '/node-manager/cloudregion',
        name: 'cloud_region_list',
        icon: '',
        operation: [],
        hasDetail: true,
        children: [
          { title: '节点', url: '/node-manager/cloudregion/node', name: 'cloud_region_node', icon: '', operation: [] },
        ],
      },
    ];
    render(<AppTopNav apps={navApps} pathname="/node-manager/collector" menus={nodeMenus} />);
    const node = screen.getByRole('link', { name: '节点管理' });
    expect(node.getAttribute('href')).toBe('/node-manager/cloudregion');
    expect(node.getAttribute('aria-current')).toBe('page');
    expect(fireEvent.click(node)).toBe(false);
  });
});
