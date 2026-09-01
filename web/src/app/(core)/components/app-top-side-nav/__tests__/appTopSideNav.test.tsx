import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { MenuItem } from '@/types/index';
import AppTopSideNav from '../index';

let currentPath = '/job/execution/quick-exec';

vi.mock('next/navigation', () => ({
  usePathname: () => currentPath,
}));

vi.mock('@/components/icon', () => ({
  default: ({ type }: { type: string }) => <span data-testid={`icon-${type}`} />,
}));

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
    expect(screen.getByTestId('app-top-side-nav').style.width).toBe('240px');
    expect(screen.getByTestId('app-top-side-nav').className).toContain('h-full');
    expect(screen.getByTestId('app-top-side-nav').className).toContain('self-stretch');
    expect(screen.getByTestId('app-top-side-nav').className).toContain('color-bg-1');
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
});
