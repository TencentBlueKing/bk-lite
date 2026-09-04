import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { MenuItem } from '@/types/index';
import AppTopSideNav from '../index';

let currentPath = '/job/execution/quick-exec';
let sideNavMode: 'expanded' | 'collapsed' = 'expanded';
const setSideNav = vi.fn();

vi.mock('next/navigation', () => ({
  usePathname: () => currentPath,
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('@/components/icon', () => ({
  default: ({ type }: { type: string }) => <span data-testid={`icon-${type}`} />,
}));

vi.mock('@/console-layout', async () => {
  const actual = await vi.importActual<typeof import('@/console-layout')>('@/console-layout');
  return {
    ...actual,
    useConsoleLayout: () => ({
      layout: 'app-top',
      setLayout: vi.fn(),
      sideNav: sideNavMode,
      setSideNav,
    }),
  };
});

const menu = (item: Partial<MenuItem> & Pick<MenuItem, 'name' | 'url'>): MenuItem => ({
  title: item.title || item.name,
  icon: item.icon || '',
  operation: [],
  ...item,
});

const menus: MenuItem[] = [
  menu({ title: '首页', url: '/job/home', name: 'home' }),
  menu({
    title: '作业执行',
    url: '/job/execution',
    name: 'execution',
    children: [
      menu({ title: '快速执行', url: '/job/execution/quick-exec', name: 'quick_exec' }),
      menu({ title: '文件分发', url: '/job/execution/file-dist', name: 'file_dist' }),
    ],
  }),
];

const opspilotMenus: MenuItem[] = [
  menu({ title: '工作台', url: '/opspilot/studio', name: 'bot_list', icon: 'jiqiren2' }),
  menu({ title: '知识库', url: '/opspilot/wiki', name: 'wiki_list', icon: 'zhishiku' }),
];

afterEach(() => {
  cleanup();
  currentPath = '/job/execution/quick-exec';
  sideNavMode = 'expanded';
  setSideNav.mockReset();
});

describe('AppTopSideNav', () => {
  it('lists first-layer items without nesting children', () => {
    render(<AppTopSideNav menus={menus} pathname="/job/execution/quick-exec" />);
    expect(screen.getByText('首页')).toBeTruthy();
    expect(screen.getByText('作业执行')).toBeTruthy();
    expect(screen.queryByText('快速执行')).toBeNull();
    expect(screen.queryByText('文件分发')).toBeNull();
  });

  it('fills the column below the top bar and does not own portal branding', () => {
    render(<AppTopSideNav menus={menus} pathname="/job/execution/quick-exec" />);
    expect(screen.queryByText('作业管理')).toBeNull();
    expect(screen.queryByAltText('logo')).toBeNull();
    expect(screen.getByTestId('app-top-side-nav').style.width).toBe('200px');
    expect(screen.getByTestId('app-top-side-nav').className).toContain('h-full');
    expect(screen.getByTestId('app-top-side-nav').className).toContain('self-stretch');
    expect(screen.getByTestId('app-top-side-nav-panel').className).toContain('color-bg-1');
    expect(screen.getByTestId('app-top-side-nav').className).not.toContain('border-r');
    expect(screen.getByTestId('app-top-side-nav-menu').className).not.toContain('border-r');
    expect(screen.getByTestId('app-top-side-nav-menu').className).toContain('main-content');
    expect(screen.getByTestId('app-top-side-nav-menu').className).not.toContain('shadow-');
  });

  it('highlights the current item as a raised surface on the wallpaper, not an in-page side card', () => {
    render(<AppTopSideNav menus={menus} pathname="/job/execution/quick-exec" />);
    const activeItem = screen.getByRole('link', { name: '作业执行' });
    expect(activeItem.className).toContain('rounded-[10px]');
    expect(activeItem.className).toContain('nav-button-bg-active');
    expect(screen.getByTestId('app-top-side-nav').className).not.toContain('side-nav-bg');
  });

  it('renders the knowledge-base item with the line-style nav icon', () => {
    render(<AppTopSideNav menus={opspilotMenus} pathname="/opspilot/wiki" />);
    expect(screen.getByTestId('icon-zhishiku1')).toBeTruthy();
    expect(screen.queryByTestId('icon-zhishiku')).toBeNull();
  });

  it('keeps the first-layer item active on a detail route', () => {
    currentPath = '/opspilot/studio/detail/settings';
    render(<AppTopSideNav menus={opspilotMenus} pathname={currentPath} />);
    expect(screen.getByRole('link', { name: '工作台' }).className).toContain('nav-button-bg-active');
    expect(screen.getByRole('link', { name: '知识库' }).className).not.toContain('nav-button-bg-active');
  });

  it('links container menus to the first leaf instead of a redirect stub', () => {
    render(<AppTopSideNav menus={menus} pathname="/job/execution/quick-exec" />);
    expect(screen.getByRole('link', { name: '作业执行' }).getAttribute('href')).toBe(
      '/job/execution/quick-exec',
    );
    expect(screen.getByRole('link', { name: '首页' }).getAttribute('href')).toBe('/job/home');
  });

  it('collapses from the footer toggle and persists through the console layout', () => {
    render(<AppTopSideNav menus={opspilotMenus} pathname="/opspilot/wiki" />);
    fireEvent.click(screen.getByRole('button', { name: 'common.collapseSideNav' }));
    expect(setSideNav).toHaveBeenCalledWith('collapsed');
  });

  it('keeps only icons in the collapsed rail and labels the links for assistive tech', () => {
    sideNavMode = 'collapsed';
    render(<AppTopSideNav menus={opspilotMenus} pathname="/opspilot/wiki" />);
    const rail = screen.getByTestId('app-top-side-nav');
    expect(rail.style.width).toBe('56px');
    expect(rail.dataset.sideNav).toBe('collapsed');
    expect(screen.getByTestId('app-top-side-nav-panel').style.width).toBe('56px');
    expect(screen.queryByText('工作台')).toBeNull();
    expect(screen.getByRole('link', { name: '工作台' })).toBeTruthy();
    expect(screen.getByTestId('icon-jiqiren2')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'common.expandSideNav' })).toBeTruthy();
  });

  it('flies out on hover without widening the rail, then hides again on leave', () => {
    sideNavMode = 'collapsed';
    render(<AppTopSideNav menus={opspilotMenus} pathname="/opspilot/wiki" />);
    const rail = screen.getByTestId('app-top-side-nav');
    fireEvent.mouseEnter(rail);
    const panel = screen.getByTestId('app-top-side-nav-panel');
    expect(rail.style.width).toBe('56px');
    expect(panel.style.width).toBe('200px');
    expect(panel.dataset.flyout).toBe('true');
    expect(panel.className).toContain('absolute');
    expect(panel.className).toContain('4px_0_6px');
    expect(panel.className).not.toContain('0_4px_12px');
    expect(screen.getByText('工作台')).toBeTruthy();
    expect(setSideNav).not.toHaveBeenCalled();

    fireEvent.mouseLeave(rail);
    expect(screen.getByTestId('app-top-side-nav-panel').style.width).toBe('56px');
    expect(screen.queryByText('工作台')).toBeNull();
  });

  it('opens the flyout when the pointer moves onto another icon after collapsing in place', () => {
    sideNavMode = 'collapsed';
    render(<AppTopSideNav menus={opspilotMenus} pathname="/opspilot/wiki" />);
    expect(screen.getByTestId('app-top-side-nav-panel').style.width).toBe('56px');
    fireEvent.mouseMove(screen.getByRole('link', { name: '知识库' }));
    expect(screen.getByTestId('app-top-side-nav-panel').style.width).toBe('200px');
    expect(screen.getByText('知识库')).toBeTruthy();
  });

  it('expands for real when the flyout toggle is clicked', () => {
    sideNavMode = 'collapsed';
    render(<AppTopSideNav menus={opspilotMenus} pathname="/opspilot/wiki" />);
    fireEvent.mouseEnter(screen.getByTestId('app-top-side-nav'));
    fireEvent.click(screen.getByRole('button', { name: 'common.expandSideNav' }));
    expect(setSideNav).toHaveBeenCalledWith('expanded');
  });
});
