import React from 'react';
import { act, cleanup, render } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import OpsAnalysisGauge from '@/app/ops-analysis/components/ops-analysis-widgets/gauge';

interface GaugeSeriesOption {
  splitNumber?: number;
}

let lastOption: { series?: GaugeSeriesOption[] } | null = null;
let lastOnEvents: { finished?: () => void } | null = null;
let mockContainerSize = { width: 320, height: 320 };

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
    (
      {
        option,
        onEvents,
      }: {
        option: { series?: GaugeSeriesOption[] };
        onEvents?: { finished?: () => void };
      },
      ref,
    ) => {
      lastOption = option;
      lastOnEvents = onEvents ?? null;
      React.useImperativeHandle(ref, () => ({
        getEchartsInstance: () => ({ resize: vi.fn() }),
      }));
      return <div data-testid="gauge-chart" />;
    },
  );
  MockEcharts.displayName = 'MockEcharts';
  return { default: MockEcharts };
});

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
  lastOnEvents = null;
  mockContainerSize = { width: 320, height: 320 };
  resizeCallbacks.clear();
});

const renderReportGauge = (size: { width: number; height: number }) => {
  mockContainerSize = size;
  let splitNumberAtReady: number | undefined;
  const onReady = vi.fn(() => {
    splitNumberAtReady = lastOption?.series?.[0]?.splitNumber;
  });

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
      onReady={onReady}
    />,
  );

  act(() => {
    resizeCallbacks.forEach((callback) => {
      callback([], {} as ResizeObserver);
    });
  });

  expect(onReady).not.toHaveBeenCalled();

  act(() => {
    lastOnEvents?.finished?.();
  });

  return { onReady, getSplitNumberAtReady: () => splitNumberAtReady };
};

describe('OpsAnalysisGauge report onReady layout timing', () => {
  it('calls onReady only after Large container measurement resolves layout', () => {
    const { onReady, getSplitNumberAtReady } = renderReportGauge({ width: 320, height: 320 });

    expect(onReady).toHaveBeenCalledTimes(1);
    expect(getSplitNumberAtReady()).toBe(10);
    expect(lastOption?.series?.[0]?.splitNumber).toBe(10);
  });

  it('calls onReady only after Small container measurement resolves layout', () => {
    const { onReady, getSplitNumberAtReady } = renderReportGauge({ width: 120, height: 120 });

    expect(onReady).toHaveBeenCalledTimes(1);
    expect(getSplitNumberAtReady()).toBe(2);
    expect(lastOption?.series?.[0]?.splitNumber).toBe(2);
  });
});
