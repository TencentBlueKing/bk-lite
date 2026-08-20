import React from 'react';
import { cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import ChartLegend from '@/components/chart-legend';
import OpsChartLegend from '@/app/ops-analysis/components/chartLegend';

const legendItems = [
  { name: '未分派', value: 12 },
  { name: '待响应', value: 8 },
];

afterEach(() => {
  cleanup();
});

describe('ChartLegend mount notification', () => {
  it('does not notify on first mount for the shared legend', () => {
    const onSelectionChange = vi.fn();

    render(
      <ChartLegend
        data={legendItems}
        colors={['#1677ff', '#52c41a']}
        onSelectionChange={onSelectionChange}
      />,
    );

    expect(onSelectionChange).not.toHaveBeenCalled();
  });

  it('notifies when shared legend series names change', () => {
    const onSelectionChange = vi.fn();
    const view = render(
      <ChartLegend
        data={legendItems}
        colors={['#1677ff', '#52c41a']}
        onSelectionChange={onSelectionChange}
      />,
    );

    view.rerender(
      <ChartLegend
        data={[{ name: '已关闭', value: 3 }]}
        colors={['#1677ff', '#52c41a']}
        onSelectionChange={onSelectionChange}
      />,
    );

    expect(onSelectionChange).toHaveBeenCalledTimes(1);
    expect(onSelectionChange).toHaveBeenCalledWith({});
  });

  it('does not notify on first mount for the ops-analysis legend', () => {
    const onSelectionChange = vi.fn();

    render(
      <OpsChartLegend
        data={legendItems}
        colors={['#1677ff', '#52c41a']}
        onSelectionChange={onSelectionChange}
      />,
    );

    expect(onSelectionChange).not.toHaveBeenCalled();
  });

  it('uses dashboard fill token for legend hover', () => {
    const { container } = render(
      <ChartLegend
        data={legendItems}
        colors={['#1677ff', '#52c41a']}
      />,
    );
    const opsView = render(
      <OpsChartLegend
        data={legendItems}
        colors={['#1677ff', '#52c41a']}
      />,
    );

    expect(container.querySelector('button')?.className).toContain(
      'hover:bg-(--color-fill-2)',
    );
    expect(opsView.container.querySelector('div.cursor-pointer')?.className).toContain(
      'hover:bg-(--color-fill-2)',
    );
  });
});
