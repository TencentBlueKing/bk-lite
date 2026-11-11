import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import AlertMetricTrend from '@/app/rum/alert-events/alert-metric-trend';

const EMPTY = '该时间窗内暂无样本';

function tip(atMs: number, value: number | null): string {
  if (value == null || !Number.isFinite(value)) return `${atMs} · —`;
  return `${atMs} · ${Math.round(value)}ms`;
}

function moveTo(track: HTMLElement, clientX: number, width: number) {
  track.getBoundingClientRect = () =>
    ({
      x: 0,
      y: 0,
      top: 0,
      left: 0,
      right: width,
      bottom: 96,
      width,
      height: 96,
      toJSON: () => ({}),
    }) as DOMRect;
  fireEvent.mouseMove(track, { clientX, clientY: 8 });
}

describe('alert metric trend', () => {
  it('breaks the line at a null sample and shows an em dash on that point', () => {
    const { container } = render(
      <AlertMetricTrend
        points={[
          { atMs: 1000, value: 10 },
          { atMs: 2000, value: 20 },
          { atMs: 3000, value: null },
          { atMs: 4000, value: 0 },
          { atMs: 5000, value: 0 },
        ]}
        emptyLabel={EMPTY}
        hoverHint="移入查看数值"
        formatPoint={tip}
      />,
    );

    expect(container.querySelectorAll('path')).toHaveLength(4);
    expect(container.querySelectorAll('circle')).toHaveLength(0);
    expect(screen.queryByText(EMPTY)).toBeNull();

    const track = container.querySelector('.cursor-crosshair');
    expect(track).toBeInstanceOf(HTMLElement);
    moveTo(track as HTMLElement, 200, 400);
    expect(screen.getByText('3000 · —').textContent).toBe('3000 · —');
    moveTo(track as HTMLElement, 300, 400);
    expect(screen.getByText('4000 · 0ms').textContent).toBe('4000 · 0ms');
  });

  it('draws a series of real zeros', () => {
    const { container } = render(
      <AlertMetricTrend
        points={[
          { atMs: 1000, value: 0 },
          { atMs: 2000, value: 0 },
        ]}
        emptyLabel={EMPTY}
        hoverHint="移入查看数值"
        formatPoint={tip}
      />,
    );

    expect(screen.queryByText(EMPTY)).toBeNull();
    expect(container.querySelectorAll('path')).toHaveLength(2);
    const track = container.querySelector('.cursor-crosshair');
    moveTo(track as HTMLElement, 0, 400);
    expect(screen.getByText('1000 · 0ms').textContent).toBe('1000 · 0ms');
  });

  it('shows the empty copy when every bucket is null', () => {
    const { container } = render(
      <AlertMetricTrend
        points={[
          { atMs: 1000, value: null },
          { atMs: 2000, value: null },
        ]}
        emptyLabel={EMPTY}
        hoverHint="移入查看数值"
        formatPoint={tip}
      />,
    );

    expect(screen.getByText(EMPTY).textContent).toBe(EMPTY);
    expect(container.querySelector('svg')).toBeNull();
  });
});
