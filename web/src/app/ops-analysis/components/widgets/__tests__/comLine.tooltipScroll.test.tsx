import { act, cleanup, render } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

const chartSpy = vi.hoisted(() => ({
  option: null as {
    tooltip?: {
      enterable?: boolean;
      confine?: boolean;
      hideDelay?: number;
      trigger?: string;
      position?: (
        point: number[],
        params: unknown,
        el: HTMLElement,
        rect: unknown,
        size: { contentSize: number[]; viewSize: number[] },
      ) => number[];
    };
    series?: Array<{
      symbol?: string;
      symbolSize?: number;
      showSymbol?: boolean;
      smooth?: number;
      areaStyle?: unknown;
      type?: string;
    }>;
  } | null,
  notMerge: undefined as boolean | undefined,
  replaceMerge: undefined as string[] | undefined,
}));

vi.mock('echarts-for-react', () => {
  const MockEcharts = ({
    option,
    notMerge,
    replaceMerge,
  }: {
    option?: (typeof chartSpy)['option'];
    notMerge?: boolean;
    replaceMerge?: string[];
  }) => {
    chartSpy.option = option ?? null;
    chartSpy.notMerge = notMerge;
    chartSpy.replaceMerge = replaceMerge;
    return <div data-testid="line-chart" />;
  };
  MockEcharts.displayName = 'MockEcharts';
  return { default: MockEcharts };
});

const translate = (key: string) => key;

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: translate }),
}));

vi.mock('@/app/ops-analysis/components/widget-state', () => ({
  default: () => <div data-testid="empty-state">empty</div>,
}));

import ComLine from '../comLine';

const multiSeriesData = {
  'host-ecom-inventory-01': [['2026-09-04 09:11', 64.64]],
  'host-ecom-inventory-02': [['2026-09-04 09:11', 61.27]],
  'host-ecom-order-01': [['2026-09-04 09:11', 27.94]],
};

beforeAll(() => {
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
    callback(0);
    return 1;
  });
  vi.stubGlobal('cancelAnimationFrame', () => undefined);
});

afterEach(() => {
  cleanup();
  chartSpy.option = null;
  chartSpy.notMerge = undefined;
  chartSpy.replaceMerge = undefined;
});

describe('ComLine multi-series tooltip', () => {
  it('lets the hover tooltip scroll instead of covering the whole chart', async () => {
    render(<ComLine rawData={multiSeriesData} loading={false} />);

    await act(async () => {
      await Promise.resolve();
    });

    expect(chartSpy.option?.tooltip?.enterable).toBe(true);
    expect(chartSpy.option?.tooltip?.confine).toBe(true);

    const tooltipEl = document.createElement('div');
    chartSpy.option?.tooltip?.position?.(
      [120, 40],
      null,
      tooltipEl,
      null,
      { contentSize: [220, 420], viewSize: [480, 260] },
    );

    expect(tooltipEl.style.maxHeight).toBe('156px');
    expect(tooltipEl.style.overflowY).toBe('auto');
  });

  it('draws a circle when each series has only one sample', async () => {
    render(<ComLine rawData={multiSeriesData} loading={false} />);

    await act(async () => {
      await Promise.resolve();
    });

    expect(chartSpy.option?.series?.length).toBeGreaterThan(0);
    chartSpy.option?.series?.forEach((series) => {
      expect(series).toMatchObject({
        showSymbol: true,
        symbol: 'circle',
        symbolSize: 8,
      });
    });
  });

  it('hides point marks once a series can form a line', async () => {
    render(
      <ComLine
        rawData={{
          '整体健康度': [
            ['2026-09-27', 1.2],
            ['2026-09-28', 1.75],
          ],
        }}
        loading={false}
      />,
    );

    await act(async () => {
      await Promise.resolve();
    });

    expect(chartSpy.option?.series?.[0]).toMatchObject({
      showSymbol: false,
      symbol: 'none',
      symbolSize: 0,
    });
  });

  it('keeps the line option stable and merges series instead of replacing the chart', () => {
    const { rerender } = render(<ComLine rawData={multiSeriesData} loading={false} />);
    const first = chartSpy.option;

    expect(first?.tooltip?.trigger).toBe('axis');
    expect(first?.tooltip?.enterable).toBe(true);
    expect(first?.series?.[0]).toMatchObject({
      type: 'line',
      smooth: 0.36,
    });
    expect(first?.series?.[0]?.areaStyle).toBeTruthy();
    expect(chartSpy.notMerge).toBe(false);
    expect(chartSpy.replaceMerge).toEqual(['series', 'xAxis', 'yAxis', 'legend']);

    rerender(<ComLine rawData={multiSeriesData} loading={false} />);

    expect(chartSpy.option).toBe(first);
  });
});
