import React from 'react';
import { act, cleanup, render } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import ComGauge from '../comGauge';
import OpsAnalysisGauge from '@/app/ops-analysis/components/ops-analysis-widgets/gauge';

interface GaugeSeriesOption {
  min?: number;
  max?: number;
  splitNumber?: number;
  axisLine?: { lineStyle?: { width?: number } };
  splitLine?: { length?: number; distance?: number };
  axisLabel?: { distance?: number };
  detail?: { offsetCenter?: [number, string]; fontSize?: number };
}

let lastOption: { series?: GaugeSeriesOption[] } | null = null;
let mockContainerSize = { width: 180, height: 180 };
const resizeSpy = vi.fn();

const resizeCallbacks = new Map<Element, ResizeObserverCallback>();

beforeAll(() => {
  vi.stubGlobal(
    'ResizeObserver',
    class {
      constructor(private callback: ResizeObserverCallback) {}

      observe(element: Element) {
        resizeCallbacks.set(element, this.callback);
      }

      disconnect() {
        resizeCallbacks.delete(
          [...resizeCallbacks.entries()].find(([, cb]) => cb === this.callback)?.[0] as Element,
        );
      }
    },
  );

  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function mockRect(
    this: HTMLElement,
  ) {
    return {
      width: mockContainerSize.width,
      height: mockContainerSize.height,
      top: 0,
      left: 0,
      right: mockContainerSize.width,
      bottom: mockContainerSize.height,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    };
  });

  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
    callback(0);
    return 1;
  });
  vi.stubGlobal('cancelAnimationFrame', () => undefined);
});

vi.mock('echarts-for-react', () => {
  const MockEcharts = React.forwardRef(
    ({ option }: { option: { series?: GaugeSeriesOption[] } }, ref) => {
      lastOption = option;
      React.useImperativeHandle(ref, () => ({
        getEchartsInstance: () => ({ resize: resizeSpy }),
      }));
      return <div data-testid="gauge-chart" />;
    },
  );
  MockEcharts.displayName = 'MockEcharts';
  return { default: MockEcharts };
});

vi.mock('@/app/ops-analysis/components/widget-state', () => ({
  default: () => <div data-testid="empty-state">empty</div>,
}));

vi.mock('@/components/chart-surface', () => {
  const MockChartSurface = React.forwardRef(
    (
      {
        children,
        hasData,
        loading,
      }: {
        children: React.ReactNode;
        hasData: boolean;
        loading?: boolean;
      },
      ref: React.ForwardedRef<HTMLDivElement>,
    ) => {
      if (loading || !hasData) {
        return <div data-testid="chart-surface-empty" />;
      }
      return <div ref={ref}>{children}</div>;
    },
  );
  MockChartSurface.displayName = 'MockChartSurface';
  return { default: MockChartSurface };
});

afterEach(() => {
  cleanup();
  lastOption = null;
  mockContainerSize = { width: 180, height: 180 };
  resizeCallbacks.clear();
  resizeSpy.mockClear();
});

const renderGaugeAtSize = (
  width: number,
  height: number,
  config: Record<string, unknown> = {},
) => {
  mockContainerSize = { width, height };
  const result = render(
    <ComGauge
      rawData={{ score: 86 }}
      config={{
        chartType: 'gauge',
        selectedFields: ['score'],
        gaugeMin: 0,
        gaugeMax: 100,
        gaugeShape: 'semicircle',
        ...config,
      }}
    />,
  );
  act(() => {
    resizeCallbacks.forEach((callback) => {
      callback([], {} as ResizeObserver);
    });
  });
  return result;
};

const expectLabelsClearArc = (series: GaugeSeriesOption) => {
  const arcWidth = series.axisLine?.lineStyle?.width ?? 0;
  const splitLineLength = series.splitLine?.length ?? 0;
  const splitLineDistance = series.splitLine?.distance ?? 0;
  const axisLabelDistance = series.axisLabel?.distance ?? 0;
  const inset = splitLineLength + axisLabelDistance + splitLineDistance;
  expect(inset).toBeGreaterThanOrEqual(arcWidth + 5);
};

describe('Gauge responsive scale layout', () => {
  it('uses sparse labels for small containers', () => {
    renderGaugeAtSize(120, 120);
    const series = lastOption?.series?.[0];
    expect(series?.splitNumber).toBe(2);
    expect(series?.axisLabel?.distance).toBe(27);
    expect(series?.detail?.offsetCenter?.[1]).toBe('50%');
    expectLabelsClearArc(series!);
  });

  it('uses medium density for regular dashboard widgets', () => {
    renderGaugeAtSize(180, 180);
    const series = lastOption?.series?.[0];
    expect(series?.splitNumber).toBe(5);
    expect(series?.axisLabel?.distance).toBe(26);
    expect(series?.detail?.offsetCenter?.[1]).toBe('42%');
    expectLabelsClearArc(series!);
  });

  it('uses dense labels for large containers', () => {
    renderGaugeAtSize(320, 320);
    const series = lastOption?.series?.[0];
    expect(series?.splitNumber).toBe(10);
    expect(series?.axisLabel?.distance).toBe(25);
    expect(series?.detail?.offsetCenter?.[1]).toBe('38%');
    expectLabelsClearArc(series!);
  });

  it('treats wide-but-short widgets as small based on height', () => {
    renderGaugeAtSize(320, 100);
    expect(lastOption?.series?.[0]?.splitNumber).toBe(2);
  });

  it('preserves custom min/max contract', () => {
    renderGaugeAtSize(180, 180, {
      gaugeMin: 20,
      gaugeMax: 80,
    });
    const series = lastOption?.series?.[0];
    expect(series?.min).toBe(20);
    expect(series?.max).toBe(80);
    expect(series?.splitNumber).toBe(5);
  });

  it('attaches observer after loading finishes and resizes ECharts instance', () => {
    const { rerender } = render(
      <ComGauge
        rawData={{ score: 86 }}
        loading
        config={{
          chartType: 'gauge',
          selectedFields: ['score'],
          gaugeMin: 0,
          gaugeMax: 100,
          gaugeShape: 'semicircle',
        }}
      />,
    );

    expect(resizeCallbacks.size).toBe(0);

    rerender(
      <ComGauge
        rawData={{ score: 86 }}
        loading={false}
        config={{
          chartType: 'gauge',
          selectedFields: ['score'],
          gaugeMin: 0,
          gaugeMax: 100,
          gaugeShape: 'semicircle',
        }}
      />,
    );

    act(() => {
      resizeCallbacks.forEach((callback) => {
        callback([], {} as ResizeObserver);
      });
    });

    expect(resizeCallbacks.size).toBeGreaterThan(0);
    expect(resizeSpy).toHaveBeenCalled();
    expect(lastOption?.series?.[0]?.splitNumber).toBe(5);
  });

  it('applies the same responsive layout contract in OpsAnalysisGauge', () => {
    mockContainerSize = { width: 120, height: 120 };
    render(
      <OpsAnalysisGauge
        rawData={{ score: 86 }}
        config={{
          chartType: 'gauge',
          selectedFields: ['score'],
          gaugeMin: 0,
          gaugeMax: 100,
          gaugeShape: 'semicircle',
        }}
      />,
    );
    act(() => {
      resizeCallbacks.forEach((callback) => {
        callback([], {} as ResizeObserver);
      });
    });

    const series = lastOption?.series?.[0];
    expect(series?.splitNumber).toBe(2);
    expect(series?.axisLabel?.distance).toBe(27);
    expect(series?.detail?.offsetCenter?.[1]).toBe('50%');
  });
});
