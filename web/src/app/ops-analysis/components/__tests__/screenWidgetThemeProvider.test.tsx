// @vitest-environment jsdom

import React from 'react';
import { cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { Empty } from 'antd';
import ScreenWidgetThemeProvider from '../screenWidgetThemeProvider';

afterEach(cleanup);

describe('ScreenWidgetThemeProvider', () => {
  it('renders children without a theme wrapper for default mode', () => {
    const { container } = render(
      <ScreenWidgetThemeProvider mode="default">
        <span data-testid="child">ok</span>
      </ScreenWidgetThemeProvider>,
    );

    expect(container.querySelector('[data-screen-widget-theme]')).toBeNull();
    expect(container.querySelector('[data-testid="child"]')).toBeTruthy();
  });

  it('remaps color tokens and does not toggle document dark class', () => {
    const hadDark = document.documentElement.classList.contains('dark');
    document.documentElement.classList.remove('dark');

    const { container } = render(
      <ScreenWidgetThemeProvider mode="screen-dark">
        <span>content</span>
      </ScreenWidgetThemeProvider>,
    );

    const wrap = container.querySelector(
      '[data-screen-widget-theme="screen-dark"]',
    ) as HTMLElement;
    expect(wrap).toBeTruthy();
    expect(wrap.style.getPropertyValue('--color-text-1')).toBe('#e8eef7');
    expect(document.documentElement.classList.contains('dark')).toBe(false);

    if (hadDark) {
      document.documentElement.classList.add('dark');
    }
  });

  it('tints empty-state illustration with the screen text color', () => {
    const { container } = render(
      <ScreenWidgetThemeProvider mode="screen-dark">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />
      </ScreenWidgetThemeProvider>,
    );

    const wrap = container.querySelector(
      '[data-screen-widget-theme="screen-dark"]',
    ) as HTMLElement;
    expect(wrap.className).toMatch(/root/);
    expect(wrap.querySelector('.ant-empty-image svg')).toBeTruthy();
  });
});
