import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import ChartLegend from '@/components/chart-legend';

const longName = '10.11.27.147[default] (10.11.27.147)';

afterEach(() => {
  cleanup();
});

describe('ChartLegend long labels', () => {
  it('keeps the vertical legend at a fixed width and ellipsizes long names', () => {
    const { container } = render(
      <ChartLegend
        data={[{ name: longName }, { name: '1111' }]}
        colors={['#1677ff', '#52c41a']}
      />,
    );

    const column = container.firstElementChild as HTMLElement;
    expect(column.className).toMatch(/w-\[120px\]/);
    expect(column.className).toMatch(/\bshrink-0\b/);

    const label = screen.getByText(longName);
    expect(label.className).toMatch(/overflow-hidden/);
    expect(label.className).toMatch(/text-ellipsis/);
    expect(label.className).toMatch(/whitespace-nowrap/);
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
  });
});
