import React from 'react';
import { cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import TimeSeriesComposedChart from '..';

const { chartRender } = vi.hoisted(() => ({ chartRender: vi.fn() }));

vi.mock('echarts-for-react', () => ({
  default: ({ option }: { option: Record<string, unknown> }) => {
    chartRender(option);
    return <div data-testid="echarts" />;
  },
}));

vi.mock('@/hooks/useChartColors', () => ({
  default: () => ({
    axisLine: '#ddd',
    splitLine: '#eee',
    axisLabel: '#777',
    tooltipBg: '#fff',
    tooltipBorder: '#ddd',
    textPrimary: '#111',
    textTertiary: '#777',
  }),
}));

afterEach(() => {
  cleanup();
  chartRender.mockClear();
});

describe('TimeSeriesComposedChart', () => {
  it('保留空序列值，避免把缺失事件点绘制成零值点', () => {
    render(
      <TimeSeriesComposedChart
        data={[
          { timestamp: '2026-08-18T10:00:00Z', event: null },
          { timestamp: '2026-08-18T10:00:20Z', event: 0.2 },
        ]}
        xDataKey="timestamp"
        series={[
          {
            name: '事件发生点',
            type: 'line',
            dataKey: 'event',
            color: '#faad14',
            showSymbol: true,
          },
        ]}
      />,
    );

    const option = chartRender.mock.calls.at(-1)?.[0] as {
      series: Array<{ data: Array<number | null> }>;
    };
    expect(option.series[0].data).toEqual([null, 0.2]);
  });
});
