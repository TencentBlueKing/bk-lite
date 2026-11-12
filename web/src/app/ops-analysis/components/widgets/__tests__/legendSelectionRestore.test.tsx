import { cleanup, fireEvent, render } from '@testing-library/react';
import * as echarts from 'echarts';
import { afterEach, describe, expect, it, vi } from 'vitest';

import ComBar from '@/app/ops-analysis/components/widgets/comBar';
import ComLine from '@/app/ops-analysis/components/widgets/comLine';
import OpsAnalysisBar from '@/app/ops-analysis/components/ops-analysis-widgets/bar';
import OpsAnalysisLine from '@/app/ops-analysis/components/ops-analysis-widgets/line';

interface ChartUpdate {
  option: echarts.EChartsOption;
  notMerge?: boolean;
  replaceMerge?: string[];
}

const updates: ChartUpdate[] = [];

vi.mock('echarts-for-react', () => ({
  default: ({
    option,
    notMerge,
    replaceMerge,
  }: ChartUpdate) => {
    updates.push({ option, notMerge, replaceMerge });
    return <div data-testid="chart" />;
  },
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const rawData = {
  cpu: [
    ['2026-09-04 09:11', 1],
    ['2026-09-04 09:12', 2],
  ],
  mem: [
    ['2026-09-04 09:11', 3],
    ['2026-09-04 09:12', 4],
  ],
};

const charts = [
  ['comLine', ComLine],
  ['comBar', ComBar],
  ['ops-analysis line', OpsAnalysisLine],
  ['ops-analysis bar', OpsAnalysisBar],
] as const;

const legendSelected = (option: echarts.EChartsOption) => {
  const legend = Array.isArray(option.legend) ? option.legend[0] : option.legend;
  return legend?.selected;
};

const isSeriesSelected = (chart: echarts.ECharts, name: string) => {
  const legend = chart.getModel().getComponent('legend', 0) as { isSelected: (seriesName: string) => boolean };
  return legend.isSelected(name);
};

afterEach(() => {
  cleanup();
  updates.length = 0;
});

describe('line and bar legend restore', () => {
  it.each(charts)('%s selects every series again after legend selection returns to empty', (_name, Chart) => {
    const view = render(<Chart rawData={rawData} loading={false} />);
    const cpu = view.getByText('cpu');

    fireEvent.click(cpu);
    fireEvent.click(cpu);

    const hidden = updates.at(-2);
    const restored = updates.at(-1);
    expect(legendSelected(hidden?.option ?? {})).toMatchObject({ mem: false });
    expect(legendSelected(restored?.option ?? {})).toEqual({});
    expect(restored?.notMerge).toBe(false);
    expect(restored?.replaceMerge).toEqual(['series', 'xAxis', 'yAxis', 'legend']);

    const host = document.createElement('div');
    host.style.width = '400px';
    host.style.height = '300px';
    document.body.appendChild(host);
    const chart = echarts.init(host, undefined, { renderer: 'svg', width: 400, height: 300 });
    try {
      updates.forEach((update) => {
        chart.setOption(update.option, {
          notMerge: update.notMerge,
          replaceMerge: update.replaceMerge,
        });
      });
      expect(isSeriesSelected(chart, 'cpu')).toBe(true);
      expect(isSeriesSelected(chart, 'mem')).toBe(true);
    } finally {
      chart.dispose();
      host.remove();
    }
  });
});
