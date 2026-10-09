import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
  DecorationSkin,
  TitleFrameSkin,
  titleFrameThumbSrc,
} from '../screenChromeSkins';

describe('screen chrome skins', () => {
  it('renders locked title-frame copy for hero and section presets', () => {
    const { rerender } = render(
      <TitleFrameSkin item={{ preset: 'hero-1', content: '运营大屏' }} />,
    );
    expect(screen.getByText('运营大屏')).toBeTruthy();

    rerender(
      <TitleFrameSkin item={{ preset: 'section-1', content: '数据概览' }} />,
    );
    expect(screen.getByText('数据概览')).toBeTruthy();
  });

  it('resolves stored frame and divider presets onto the current skins', () => {
    const { container, rerender } = render(
      <DecorationSkin item={{ decorationType: 'panelFrame', preset: 'a' }} />,
    );
    expect(container.querySelector('[data-decoration="border-21"]')).toBeTruthy();

    rerender(<DecorationSkin item={{ decorationType: 'panelFrame', preset: 'b' }} />);
    expect(container.querySelector('[data-decoration="tech"]')).toBeTruthy();

    rerender(
      <DecorationSkin item={{ decorationType: 'panelFrame', preset: 'border-22' }} />,
    );
    expect(container.querySelector('[data-decoration="border-22"]')).toBeTruthy();

    rerender(<DecorationSkin item={{ decorationType: 'divider', preset: 'a' }} />);
    expect(container.querySelector('[data-decoration="line-1"]')).toBeTruthy();

    rerender(<DecorationSkin item={{ decorationType: 'divider', preset: 'b' }} />);
    expect(container.querySelector('[data-decoration="line-dec"]')).toBeTruthy();
  });

  it('uses the composed catalog image for each title preset', () => {
    const hero = titleFrameThumbSrc('hero-1');
    const section = titleFrameThumbSrc('section-1');
    expect(hero).toEqual(expect.any(String));
    expect(hero.length).toBeGreaterThan(0);
    expect(section).not.toBe(hero);
    expect(titleFrameThumbSrc('hero-3')).not.toBe(titleFrameThumbSrc('hero-6'));
  });

  it('fits divider ticks inside a palette thumbnail so the drag preview stays on one card', () => {
    const { container, rerender } = render(
      <DecorationSkin item={{ decorationType: 'divider', preset: 'line-3' }} preview />,
    );
    const previewTicks = container.querySelectorAll('[data-decoration="line-3"] span');
    expect(previewTicks).toHaveLength(8);
    expect(previewTicks[0]?.className).toContain('flex-1');
    expect(previewTicks[0]?.className).not.toContain('shrink-0');

    rerender(<DecorationSkin item={{ decorationType: 'divider', preset: 'line-3' }} />);
    const canvasTicks = container.querySelectorAll('[data-decoration="line-3"] span');
    expect(canvasTicks).toHaveLength(16);
    expect(canvasTicks[0]?.className).toContain('w-2');
  });

  it('keeps the mirrored right corner inside the selection box', () => {
    const { container, rerender } = render(
      <DecorationSkin item={{ decorationType: 'corner', preset: 'a' }} />,
    );
    const left = container.querySelector('img');
    expect(left?.className).toContain('object-left-top');
    expect(left?.className).not.toContain('-scale-x-100');

    rerender(<DecorationSkin item={{ decorationType: 'corner', preset: 'b' }} />);
    const right = container.querySelector('img');
    expect(right?.className).toContain('-scale-x-100');
    expect(right?.className).toContain('origin-top');
    expect(right?.className).not.toContain('origin-top-right');
    expect(right?.className).not.toContain('object-right-top');
  });
});
