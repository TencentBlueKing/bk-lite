import React from 'react';
import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { EChartsOption } from 'echarts';

vi.mock('./layered.module.scss', () => ({
  default: new Proxy({}, { get: (_target, key) => String(key) })
}));

vi.mock('../index.module.scss', () => ({
  default: new Proxy({}, { get: (_target, key) => String(key) })
}));

vi.mock('./theme-color', () => ({
  useThemeColors: () => ({
    '--color-border': '#e5e6eb',
    '--color-text-3': '#86909c',
    '--color-text-1': '#1d2129',
    '--color-bg': '#ffffff'
  })
}));

let chartOption: EChartsOption | null = null;

vi.mock('../../../shared/widgets/useECharts', () => ({
  useECharts: (option: EChartsOption | null) => {
    chartOption = option;
    return { containerRef: () => undefined };
  }
}));

import ThinTimeSeries from './thin-time-series';

describe('focus line chart', () => {
  it('draws one hoverable line and no area', () => {
    chartOption = null;
    render(
      <ThinTimeSeries
        bare
        title=""
        unit="percent"
        data={[
          { time: 1, value1: 20 },
          { time: 2, value1: 40 },
          { time: 3, value1: 35 }
        ]}
        legends={[{ label: '使用率', color: '#722ED1' }]}
      />
    );

    const series = chartOption?.series;
    expect(Array.isArray(series)).toBe(true);
    const line = Array.isArray(series) ? series[0] : undefined;
    expect(line && 'type' in line ? line.type : undefined).toBe('line');
    expect(line && 'areaStyle' in line ? line.areaStyle : undefined).toBeUndefined();
    expect(line && 'lineStyle' in line ? line.lineStyle?.width : undefined).toBeLessThanOrEqual(1.6);
    expect(chartOption?.tooltip && !Array.isArray(chartOption.tooltip)
      ? chartOption.tooltip.show
      : undefined).toBe(true);
    expect(document.querySelector('.chartLegend')).toBeNull();
  });
});
