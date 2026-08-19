import React from 'react';
import { act, cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const chartSpy = vi.hoisted(() => ({
  onEvents: null as { finished?: () => void } | null,
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('echarts-for-react', () => {
  const MockEcharts = React.forwardRef(
    (
      { onEvents }: { onEvents?: { finished?: () => void } },
      _ref: React.ForwardedRef<unknown>,
    ) => {
      React.useEffect(() => {
        chartSpy.onEvents = onEvents ?? null;
      }, [onEvents]);
      return <div data-testid="radar-chart" />;
    },
  );
  MockEcharts.displayName = 'MockEcharts';
  return { default: MockEcharts };
});

import OpsAnalysisRadar from '@/app/ops-analysis/components/ops-analysis-widgets/radar';

const radarData = [
  { name: 'CPU', value: 42 },
  { name: '内存', value: 68 },
  { name: '磁盘', value: 31 },
];

describe('OpsAnalysisRadar report onReady timing', () => {
  afterEach(() => {
    cleanup();
    chartSpy.onEvents = null;
  });

  it('does not mark ready until the radar animation finished event', async () => {
    const onReady = vi.fn();
    render(
      <OpsAnalysisRadar rawData={radarData} loading={false} onReady={onReady} />,
    );

    await act(async () => {
      await Promise.resolve();
    });

    expect(onReady).not.toHaveBeenCalled();

    act(() => {
      chartSpy.onEvents?.finished?.();
    });

    expect(onReady).toHaveBeenCalledTimes(1);
    expect(onReady).toHaveBeenCalledWith(true);
  });
});
