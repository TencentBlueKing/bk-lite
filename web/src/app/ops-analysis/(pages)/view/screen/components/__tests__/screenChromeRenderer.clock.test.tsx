import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ScreenClockItem } from '@/app/ops-analysis/types/screen';
import ScreenChromeRenderer from '../screenChromeRenderer';

vi.useFakeTimers();
vi.setSystemTime(new Date('2026-09-30T16:07:09'));

describe('screen chrome clock style', () => {
  it('applies configured font size and color token', () => {
    const item: ScreenClockItem = {
      id: 'clock-1',
      kind: 'clock',
      format: 'HH:mm:ss',
      x: 0,
      y: 0,
      w: 240,
      h: 48,
      zIndex: 1,
      textStyle: { fontSize: 28, color: 'accent' },
    };

    const { container } = render(<ScreenChromeRenderer item={item} />);
    const clock = container.querySelector('[data-screen-clock]') as HTMLElement;
    expect(clock).toBeTruthy();
    expect(clock.style.fontSize).toBe('28px');
    expect(clock.style.color).toBe('var(--screen-chrome-accent)');
    expect(clock.style.textShadow).toBe('');
    expect(clock.textContent).toContain('16:07:09');
  });

  it('paints a chosen hex color as that color', () => {
    const item: ScreenClockItem = {
      id: 'clock-2',
      kind: 'clock',
      format: 'HH:mm:ss',
      x: 0,
      y: 0,
      w: 240,
      h: 48,
      zIndex: 1,
      textStyle: { fontSize: 20, color: '#FF00AA' },
    };

    const { container } = render(<ScreenChromeRenderer item={item} />);
    const clock = container.querySelector('[data-screen-clock]') as HTMLElement;
    expect(clock.style.color).toBe('rgb(255, 0, 170)');
  });

  it('ignores a color that is neither a theme token nor a hex value', () => {
    const item: ScreenClockItem = {
      id: 'clock-3',
      kind: 'clock',
      format: 'HH:mm:ss',
      x: 0,
      y: 0,
      w: 240,
      h: 48,
      zIndex: 1,
      textStyle: { color: 'red' },
    };

    const { container } = render(<ScreenChromeRenderer item={item} />);
    const clock = container.querySelector('[data-screen-clock]') as HTMLElement;
    expect(clock.style.color).toBe('var(--screen-title-color)');
  });
});
