import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import ComSingle from '../comSingle';

vi.mock('echarts-for-react', () => ({ default: () => <div data-testid="sparkline" /> }));
vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => (
      key === 'dashboard.noComputableValue' ? '没有可计算的数值' : key
    ),
  }),
}));
vi.mock('@/app/ops-analysis/components/ops-analysis-metric-value', () => ({
  default: ({ main }: { main: React.ReactNode }) => (
    <div data-testid="main-value">{main}</div>
  ),
}));
vi.mock('@/app/ops-analysis/components/widget-state', () => ({
  default: ({ description }: { description?: string }) => (
    <div data-testid="widget-state">{description ?? 'empty'}</div>
  ),
}));

beforeAll(() => {
  class ResizeObserverMock {
    observe() {}
    disconnect() {}
  }
  vi.stubGlobal('ResizeObserver', ResizeObserverMock);
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
    callback(0);
    return 1;
  });
  vi.stubGlobal('cancelAnimationFrame', () => undefined);
});

afterEach(cleanup);

describe('ComSingle scalar calculation', () => {
  it('shows the average and keeps the description from the raw result', () => {
    render(
      <ComSingle
        rawData={{
          note: '四台主机',
          items: [
            { cpu: 10 },
            { cpu: null },
            { cpu: '30' },
          ],
        }}
        config={{
          chartType: 'single',
          selectedFields: ['cpu'],
          descriptionField: 'note',
          scalarCalc: { method: 'avg', field: 'cpu' },
        }}
      />,
    );

    expect(screen.getByTestId('main-value').textContent).toBe('20');
    expect(screen.getByText('四台主机')).toBeTruthy();
  });

  it('shows zero for a count of no records', () => {
    render(
      <ComSingle
        rawData={[]}
        config={{ chartType: 'single', scalarCalc: { method: 'count' } }}
      />,
    );

    expect(screen.getByTestId('main-value').textContent).toBe('0');
  });

  it('uses the empty state when a non-count calculation has no records', () => {
    render(
      <ComSingle
        rawData={[]}
        config={{ chartType: 'single', scalarCalc: { method: 'sum', field: 'cpu' } }}
      />,
    );

    expect(screen.getByTestId('widget-state').textContent).toBe('empty');
  });

  it('uses the formal message when no value can be calculated', () => {
    render(
      <ComSingle
        rawData={[{ cpu: '高' }]}
        config={{ chartType: 'single', scalarCalc: { method: 'max', field: 'cpu' } }}
      />,
    );

    expect(screen.getByTestId('widget-state').textContent).toBe('没有可计算的数值');
  });
});
