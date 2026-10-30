import React from 'react';
import { cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { presentScreenRenderContext, calculateScreenVisualMetrics } from '@/app/ops-analysis/(pages)/view/screen/utils/metrics';
import { scaleScreenMetric } from '@/app/ops-analysis/components/widgets/shared/screenMetrics';
import type { ScreenRenderContext } from '@/app/ops-analysis/types/dashBoard';

const chartSpy = vi.hoisted(() => ({
  lastOption: null as {
    series?: Array<{ label?: { rich?: { title?: { fontSize?: number }; value?: { fontSize?: number } } } }>;
    xAxis?: { axisLabel?: { textStyle?: { fontSize?: number } } };
    yAxis?: { axisLabel?: { textStyle?: { fontSize?: number } } };
  } | null,
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('echarts-for-react', () => {
  const MockEcharts = React.forwardRef(
    (
      { option }: { option: typeof chartSpy.lastOption },
      ref: React.ForwardedRef<unknown>,
    ) => {
      chartSpy.lastOption = option;
      React.useImperativeHandle(ref, () => ({
        getEchartsInstance: () => ({
          resize: () => undefined,
          dispatchAction: () => undefined,
          getOption: () => ({ dataZoom: [{ start: 0, end: 100 }] }),
          on: () => undefined,
          off: () => undefined,
          getZr: () => ({ on: () => undefined, off: () => undefined }),
        }),
      }));
      return <div data-testid="echarts" />;
    },
  );
  MockEcharts.displayName = 'MockEcharts';
  return { default: MockEcharts };
});

import ComPie from '@/app/ops-analysis/components/widgets/comPie';
import ComBar from '@/app/ops-analysis/components/widgets/comBar';
import ComLine from '@/app/ops-analysis/components/widgets/comLine';

const rows = [
  { name: '未分派', value: 12 },
  { name: '待响应', value: 8 },
];

const viewportContext = (): ScreenRenderContext => {
  const fitted = calculateScreenVisualMetrics({
    contentWidth: 1920,
    contentHeight: 1080,
    designWidth: 3840,
    designHeight: 2160,
    adapter: 'fill',
  });
  return presentScreenRenderContext({
    layoutMode: 'viewportPixels',
    fitScale: fitted.fitScale,
    scaleX: fitted.scaleX,
    scaleY: fitted.scaleY,
    screenDensity: fitted.screenDensity,
    transformUiScale: fitted.screenUiScale,
  }).context;
};

const legendFontSize = (container: HTMLElement) => {
  const label = container.querySelector(
    '[data-testid="chart-legend-scroll"] span[style*="font-size"]',
  ) as HTMLElement | null;
  return label?.style.fontSize ?? '';
};

describe('viewport pixel chart fonts', () => {
  afterEach(() => {
    cleanup();
    chartSpy.lastOption = null;
  });

  it('multiplies pie center, bar and line axis, and legend text by widgetUiScale', () => {
    const context = viewportContext();
    expect(context.layoutMode).toBe('viewportPixels');
    expect(context.fitScale).toBeCloseTo(0.5);
    expect(context.widgetUiScale).toBeGreaterThan(1);

    const pie = render(<ComPie rawData={rows} screenRenderContext={context} />);
    expect(chartSpy.lastOption?.series?.[0]?.label?.rich?.title?.fontSize).toBe(
      scaleScreenMetric(14, context),
    );
    expect(chartSpy.lastOption?.series?.[0]?.label?.rich?.value?.fontSize).toBe(
      scaleScreenMetric(24, context),
    );
    expect(chartSpy.lastOption?.series?.[0]?.label?.rich?.value?.fontSize).not.toBe(24);
    expect(legendFontSize(pie.container)).toBe(`${12 * context.widgetUiScale}px`);
    expect(legendFontSize(pie.container)).not.toBe('12px');
    pie.unmount();

    render(<ComBar rawData={rows} screenRenderContext={context} />);
    expect(chartSpy.lastOption?.xAxis?.axisLabel?.textStyle?.fontSize).toBe(
      scaleScreenMetric(11, context),
    );
    expect(chartSpy.lastOption?.yAxis?.axisLabel?.textStyle?.fontSize).toBe(
      scaleScreenMetric(11, context),
    );
    expect(chartSpy.lastOption?.xAxis?.axisLabel?.textStyle?.fontSize).not.toBe(11);

    render(<ComLine rawData={rows} screenRenderContext={context} />);
    expect(chartSpy.lastOption?.xAxis?.axisLabel?.textStyle?.fontSize).toBe(
      scaleScreenMetric(11, context),
    );
    expect(chartSpy.lastOption?.xAxis?.axisLabel?.textStyle?.fontSize).not.toBe(11);
  });
});
