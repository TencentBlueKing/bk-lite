// @vitest-environment jsdom

import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import ComponentParamSwitchControl, {
  resolveComponentSwitchPopup,
} from '../componentParamSwitchControl';

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return {
    ...actual,
    Segmented: ({
      options,
      value,
    }: {
      options: Array<{ label: React.ReactNode; value: string | number }>;
      value?: string | number;
    }) => (
      <div data-testid="segmented" data-value={String(value)}>
        {options.map((option) => (
          <span key={String(option.value)}>{option.label}</span>
        ))}
      </div>
    ),
    Select: ({
      value,
      styles,
    }: {
      value?: string | number;
      styles?: { popup?: { root?: { zIndex?: number } } };
    }) => (
      <div
        data-testid="select"
        data-value={String(value)}
        data-popup-z={styles?.popup?.root?.zIndex ?? ''}
      />
    ),
  };
});

afterEach(cleanup);

describe('ComponentParamSwitchControl screen theme', () => {
  const options = [
    { label: 'A', value: 'a' },
    { label: 'B', value: 'b' },
  ];

  it('wraps screen-dark Segmented with provider and no color SCSS class', () => {
    const { container } = render(
      <ComponentParamSwitchControl
        inputConfig={{ control: 'radio', componentSwitch: true }}
        options={options}
        value="a"
        chartThemeMode="screen-dark"
      />,
    );

    expect(
      container.querySelector('[data-screen-widget-theme="screen-dark"]'),
    ).toBeTruthy();
    expect(screen.getByTestId('segmented')).toBeTruthy();
    expect(container.querySelector('[class*="screenControl"]')).toBeNull();
  });

  it('does not add screen wrapper for default theme', () => {
    const { container } = render(
      <ComponentParamSwitchControl
        inputConfig={{ control: 'select', componentSwitch: true }}
        options={options}
        value="a"
      />,
    );

    expect(container.querySelector('[data-screen-widget-theme]')).toBeNull();
    expect(screen.getByTestId('select')).toBeTruthy();
    expect(screen.getByTestId('select').getAttribute('data-popup-z')).toBe('');
  });

  it('keeps the full radio label on the title when the visible text is capped', () => {
    render(
      <ComponentParamSwitchControl
        inputConfig={{ control: 'radio', componentSwitch: true }}
        options={[{ label: 'CPU使用率111111111', value: 'cpu' }]}
        value="cpu"
      />,
    );

    expect(screen.getByTitle('CPU使用率111111111').textContent).toBe('CPU使用率111111111');
  });

  it('lifts the select popup above the dashboard fullscreen shell', () => {
    document.documentElement.setAttribute('data-app-view-fullscreen', '');
    render(
      <ComponentParamSwitchControl
        inputConfig={{ control: 'select', componentSwitch: true }}
        options={options}
        value="a"
      />,
    );

    expect(screen.getByTestId('select').getAttribute('data-popup-z')).toBe('1200');
    document.documentElement.removeAttribute('data-app-view-fullscreen');
  });
});

describe('resolveComponentSwitchPopup', () => {
  afterEach(() => {
    document.documentElement.removeAttribute('data-app-view-fullscreen');
    Object.defineProperty(document, 'fullscreenElement', {
      configurable: true,
      value: null,
    });
  });

  it('stays on the default layer outside fullscreen', () => {
    expect(resolveComponentSwitchPopup()).toEqual({});
  });

  it('raises the popup for the dashboard fullscreen shell', () => {
    document.documentElement.setAttribute('data-app-view-fullscreen', '');
    expect(resolveComponentSwitchPopup().zIndex).toBe(1200);
    expect(resolveComponentSwitchPopup().getPopupContainer).toBeUndefined();
  });
});
