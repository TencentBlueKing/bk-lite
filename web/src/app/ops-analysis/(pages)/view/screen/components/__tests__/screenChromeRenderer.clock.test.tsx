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
    expect(clock.textContent).toContain('16:07:09');
  });
});
