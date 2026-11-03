import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type {
  ScreenClockItem,
  ScreenShapeItem,
  ScreenTitleFrameItem,
} from '@/app/ops-analysis/types/screen';
import {
  calculateScreenVisualMetrics,
  resolveChromeFontDensity,
} from '../../utils/metrics';
import { resolveScreenShapeStyle } from '../../utils/screenShape';
import ScreenChromeRenderer from '../screenChromeRenderer';
import { ChromeFontDensityProvider } from '../screenChromeSkins';

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
    expect(clock.classList.contains('screen-uniform-text')).toBe(true);
    expect(clock.getAttribute('data-align')).toBe('left');
    expect(clock.style.color).toBe('var(--screen-chrome-accent)');

    const scaled = render(
      <ChromeFontDensityProvider density={1.2}>
        <ScreenChromeRenderer item={item} />
      </ChromeFontDensityProvider>,
    );
    const scaledClock = scaled.container.querySelector('[data-screen-clock]') as HTMLElement;
    expect(scaledClock.style.fontSize).toBe('34px');
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

  it('keeps shape strokes at design pixels unless a border density is set', () => {
    const item: ScreenShapeItem = {
      id: 'shape-1',
      kind: 'shape',
      shape: 'rect',
      x: 0,
      y: 0,
      w: 400,
      h: 250,
      zIndex: 1,
      shapeStyle: resolveScreenShapeStyle({ borderWidth: 4, shadow: 0 }),
    };
    const design = render(<ScreenChromeRenderer item={item} />);
    const designStroke = design.container.querySelector('.relative > div') as HTMLElement;
    expect(designStroke.style.borderWidth).toBe('4px');
    design.unmount();

    const scaled = render(
      <ChromeFontDensityProvider density={1.16} borderDensity={0.5}>
        <ScreenChromeRenderer item={item} />
      </ChromeFontDensityProvider>,
    );
    const scaledStroke = scaled.container.querySelector('.relative > div') as HTMLElement;
    expect(scaledStroke.style.borderWidth).toBe('2px');
  });

  it('renders the hero title and clock at fitScale on a 4K screen in a 1080p viewport', () => {
    const fitted = calculateScreenVisualMetrics({
      contentWidth: 1920,
      contentHeight: 1080,
      designWidth: 3840,
      designHeight: 2160,
      adapter: 'fill',
    });
    const density = resolveChromeFontDensity('viewportPixels', fitted.fitScale);
    const title: ScreenTitleFrameItem = {
      id: 'legacy-title-frame',
      kind: 'titleFrame',
      preset: 'hero-5',
      content: '告警运营大屏',
      x: 915,
      y: 12,
      w: 1996,
      h: 145,
      zIndex: 20,
      textStyle: { fontSize: 56, fontWeight: 700, align: 'right', color: '#EAF3FF' },
    };
    const clock: ScreenClockItem = {
      id: 'legacy-clock',
      kind: 'clock',
      format: 'YYYY-MM-DD HH:mm:ss',
      x: 3149,
      y: 9,
      w: 475,
      h: 56,
      zIndex: 21,
      textStyle: { fontSize: 34, fontWeight: 600, color: '#EAF3FF' },
    };

    const view = render(
      <ChromeFontDensityProvider density={density}>
        <ScreenChromeRenderer item={title} />
        <ScreenChromeRenderer item={clock} />
      </ChromeFontDensityProvider>,
    );
    expect(view.getByText('告警运营大屏').style.fontSize).toBe('28px');
    const renderedClock = view.container.querySelector('[data-screen-clock]') as HTMLElement;
    expect(renderedClock.style.fontSize).toBe('17px');
  });
});
