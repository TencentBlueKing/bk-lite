import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import ChartLegend from '@/app/ops-analysis/components/chartLegend';

const longName = '10.11.27.147[default] (10.11.27.147)';

afterEach(() => {
  cleanup();
});

describe('ops-analysis ChartLegend long labels', () => {
  it('grows the vertical column with the label and still ellipsizes past the cap', () => {
    const { container } = render(
      <ChartLegend
        data={[{ name: longName }, { name: '1111' }]}
        colors={['#1677ff', '#52c41a']}
      />,
    );

    const column = container.firstElementChild as HTMLElement;
    expect(column.className).toMatch(/inline-grid/);
    expect(column.className).toMatch(/\bshrink-0\b/);
    expect(column.style.width).toBe('max-content');
    expect(column.style.minWidth).toBe('120px');
    expect(column.style.maxWidth).toBe('180px');

    const label = screen.getByText(longName);
    expect(label.className).toMatch(/overflow-hidden/);
    expect(label.className).toMatch(/text-ellipsis/);
    expect(label.className).toMatch(/whitespace-nowrap/);
  });

  it('scales the min and max column width with the screen scale', () => {
    const { container } = render(
      <ChartLegend
        data={[{ name: '交换机' }]}
        colors={['#1677ff']}
        scale={2}
      />,
    );

    const column = container.firstElementChild as HTMLElement;
    expect(column.style.minWidth).toBe('240px');
    expect(column.style.maxWidth).toBe('360px');
  });

  it('scrolls the vertical legend when there are more dimensions than the chart height', () => {
    const { getByTestId } = render(
      <ChartLegend
        data={[{ name: longName }, { name: '1111' }]}
        colors={['#1677ff', '#52c41a']}
      />,
    );

    const scroller = getByTestId('chart-legend-scroll');
    expect(scroller.className).toMatch(/overflow-y-auto/);
    expect(scroller.className).toMatch(/min-h-0/);
    expect(scroller.className).toMatch(/min-w-0/);
    expect(scroller.className).toMatch(/max-w-full/);
  });
});
