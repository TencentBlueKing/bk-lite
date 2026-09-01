import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

let chromeLayout: 'classic' | 'app-top' = 'classic';
const setLayout = vi.fn();

vi.mock('@/console-layout', () => ({
  useConsoleLayout: () => ({ layout: chromeLayout, setLayout }),
}));

import LayoutSwitcher, { LayoutSwitcherPanel, getLayoutPanelPosition } from '../layoutSwitcher';

afterEach(() => {
  cleanup();
  chromeLayout = 'classic';
  setLayout.mockClear();
});

describe('LayoutSwitcher', () => {
  it('shows the current layout on a compact row like the organization item', () => {
    render(<LayoutSwitcher />);
    expect(screen.getByTestId('layout-switcher-row').textContent).toContain('common.layout');
    expect(screen.getByTestId('layout-switcher-row').textContent).toContain('common.layoutClassic');
    expect(screen.queryByTestId('layout-switcher-panel')).toBeNull();
  });

  it('opens the picker on click, like the organization item', () => {
    const onToggle = vi.fn();
    render(<LayoutSwitcher onToggle={onToggle} />);
    fireEvent.mouseEnter(screen.getByTestId('layout-switcher-row'));
    expect(onToggle).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('layout-switcher-row'));
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it('applies a layout from the left-side panel', () => {
    chromeLayout = 'classic';
    const onApplied = vi.fn();
    render(<LayoutSwitcherPanel onApplied={onApplied} />);
    fireEvent.click(screen.getByText('common.layoutAppTop'));
    expect(setLayout).toHaveBeenCalledWith('app-top');
    expect(onApplied).toHaveBeenCalledTimes(1);
  });

  it('places the picker to the left of the dropdown so the menu does not cover it', () => {
    const dropdown = document.createElement('div');
    dropdown.className = 'ant-dropdown';
    Object.defineProperty(dropdown, 'getBoundingClientRect', {
      value: () => ({ top: 80, left: 900, right: 1100, bottom: 200, width: 200, height: 120 }),
    });
    const item = document.createElement('div');
    dropdown.appendChild(item);
    Object.defineProperty(item, 'getBoundingClientRect', {
      value: () => ({ top: 120, left: 920, right: 1080, bottom: 152, width: 160, height: 32 }),
    });
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1280 });

    expect(getLayoutPanelPosition(item)).toEqual({ top: 120, right: 388 });
  });
});
