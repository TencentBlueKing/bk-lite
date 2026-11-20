// @vitest-environment jsdom

import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import ComponentParamSwitchControl, {
  resolveComponentSwitchPopup,
  resolveComponentSwitchPopupFont,
  resolveComponentSwitchTriggerFont,
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
      mode,
      style,
      popupMatchSelectWidth,
    }: {
      value?: string | number | Array<string | number>;
      styles?: { popup?: { root?: { zIndex?: number; fontSize?: number } } };
      mode?: string;
      style?: { width?: string | number; fontSize?: number };
      popupMatchSelectWidth?: boolean | number;
    }) => (
      <div
        data-testid="select"
        data-mode={mode ?? ''}
        data-value={Array.isArray(value) ? value.join(',') : String(value)}
        data-popup-z={styles?.popup?.root?.zIndex ?? ''}
        data-popup-font={styles?.popup?.root?.fontSize ?? ''}
        data-font={style?.fontSize ?? ''}
        data-width={style?.width ?? ''}
        data-popup-width={String(popupMatchSelectWidth ?? '')}
      />
    ),
  };
});

afterEach(cleanup);

describe('resolveComponentSwitchPopupFont', () => {
  it('keeps the design size on a reference screen and grows with a larger screen', () => {
    expect(resolveComponentSwitchPopupFont(1)).toBe(13);
    expect(resolveComponentSwitchPopupFont(1.16)).toBe(15);
  });

  it('does not go below the minimum font on a small screen', () => {
    expect(resolveComponentSwitchPopupFont(0.72)).toBe(12);
  });

  it('leaves the menu font alone outside a screen', () => {
    expect(resolveComponentSwitchPopupFont(undefined)).toBeUndefined();
  });
});

describe('resolveComponentSwitchTriggerFont', () => {
  it('uses the menu font directly when the canvas has no transform', () => {
    expect(resolveComponentSwitchTriggerFont(1.16, 'viewportPixels', 2)).toBe(15);
    expect(resolveComponentSwitchTriggerFont(0.72, 'viewportPixels', 0.5)).toBe(12);
  });

  it('divides the menu font by the canvas scale on a design canvas', () => {
    expect(resolveComponentSwitchTriggerFont(1.16, 'designTransform', 2)).toBe(7.5);
    expect(resolveComponentSwitchTriggerFont(0.72, 'designTransform', 0.5)).toBe(24);
  });

  it('keeps the menu font when there is no canvas scale to undo', () => {
    expect(resolveComponentSwitchTriggerFont(1)).toBe(13);
    expect(resolveComponentSwitchTriggerFont(undefined, 'designTransform', 2)).toBeUndefined();
  });
});

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

  it('scales the portaled menu font with the screen, not the widget', () => {
    render(
      <ComponentParamSwitchControl
        inputConfig={{ control: 'select', multiple: true }}
        options={options}
        value={['a']}
        scale={2}
        screenDensity={1.16}
      />,
    );

    const select = screen.getByTestId('select');
    expect(select.getAttribute('data-popup-font')).toBe('15');
    expect(select.getAttribute('data-font')).toBe('15');
  });

  it('undoes the canvas scale on the trigger so it matches the menu', () => {
    render(
      <ComponentParamSwitchControl
        inputConfig={{ control: 'select', componentSwitch: true }}
        options={options}
        value="a"
        scale={2}
        screenDensity={1.16}
        layoutMode="designTransform"
        fitScale={2}
      />,
    );

    const select = screen.getByTestId('select');
    expect(select.getAttribute('data-popup-font')).toBe('15');
    expect(select.getAttribute('data-font')).toBe('7.5');
  });

  it('leaves both fonts to the component library outside a screen', () => {
    render(
      <ComponentParamSwitchControl
        inputConfig={{ control: 'select', componentSwitch: true }}
        options={options}
        value="a"
      />,
    );

    const select = screen.getByTestId('select');
    expect(select.getAttribute('data-popup-font')).toBe('');
    expect(select.getAttribute('data-font')).toBe('');
  });

  it('keeps a multiple select trigger at a fixed width and lets the menu follow it', () => {
    const { container } = render(
      <ComponentParamSwitchControl
        inputConfig={{ control: 'select', multiple: true, componentSwitch: true }}
        options={options}
        value={['a', 'b']}
      />,
    );

    const select = screen.getByTestId('select');
    expect(select.getAttribute('data-mode')).toBe('multiple');
    expect(select.getAttribute('data-value')).toBe('a,b');
    expect(select.getAttribute('data-width')).toBe('');
    expect(select.getAttribute('data-popup-width')).toBe('');
    expect(container.querySelector('[style*="--ops-switch-select-multiple: 200px"]')).toBeTruthy();
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
