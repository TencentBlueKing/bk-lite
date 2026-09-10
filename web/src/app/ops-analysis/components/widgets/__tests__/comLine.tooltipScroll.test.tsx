import React from 'react';
import { act, cleanup, render } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

const chartSpy = vi.hoisted(() => ({
  option: null as {
    tooltip?: {
      enterable?: boolean;
      confine?: boolean;
      hideDelay?: number;
      position?: (
        point: number[],
        params: unknown,
        el: HTMLElement,
        rect: unknown,
        size: { contentSize: number[]; viewSize: number[] },
      ) => number[];
    };
  } | null,
}));

vi.mock('echarts-for-react', () => {
  const MockEcharts = React.forwardRef(
    (
      { option }: { option?: (typeof chartSpy)['option'] },
      _ref: React.ForwardedRef<unknown>,
    ) => {
      React.useEffect(() => {
        chartSpy.option = option ?? null;
      }, [option]);
      return <div data-testid="line-chart" />;
    },
  );
  MockEcharts.displayName = 'MockEcharts';
  return { default: MockEcharts };
});

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
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
});
