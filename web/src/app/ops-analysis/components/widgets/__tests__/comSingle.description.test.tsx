import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import ComSingle from '../comSingle';

vi.mock('echarts-for-react', () => ({ default: () => <div data-testid="sparkline" /> }));
vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) =>
      key === 'dashboard.comparePreviousShortLabel' ? '环比' : key,
  }),
}));
vi.mock('@/app/ops-analysis/components/ops-analysis-metric-value', () => ({
  default: ({ main, unit }: { main: React.ReactNode; unit?: React.ReactNode }) => (
    <div data-testid="main-value">
      {main}
      {unit}
    </div>
  ),
}));
vi.mock('@/app/ops-analysis/components/widget-state', () => ({
  default: () => <div data-testid="empty-state">empty</div>,
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

describe('ComSingle description field', () => {
  it.each([
    [0, '0'],
    [false, 'false'],
  ])('renders description value %s as %s', (description, expected) => {
    render(
      <ComSingle
        rawData={{ value: 10, note: description }}
        config={{ chartType: 'single', selectedFields: ['value'], descriptionField: 'note' }}
      />,
    );

    expect(screen.getByText(expected)).toBeTruthy();
  });

  it('keeps the whole card empty when only description has data', () => {
    render(
      <ComSingle
        rawData={{ value: null, note: '说明仍有值' }}
        config={{ chartType: 'single', selectedFields: ['value'], descriptionField: 'note' }}
      />,
    );

    expect(screen.getByTestId('empty-state')).toBeTruthy();
    expect(screen.queryByText('说明仍有值')).toBeNull();
  });

  it('renders raw description before compare without main-value formatting', () => {
    render(
      <ComSingle
        rawData={{ value: 12.345, note: '1.234' }}
        baselineData={{ value: 10 }}
        config={{
          chartType: 'single',
          selectedFields: ['value'],
          descriptionField: 'note',
          compare: true,
          decimalPlaces: 0,
          conversionFactor: 100,
          unit: 'GB',
        }}
      />,
    );

    const description = screen.getByText('1.234');
    const compare = screen.getByText('环比');
    expect(description.compareDocumentPosition(compare)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
    expect(screen.getByTestId('main-value').textContent).not.toContain('1.234');
  });
});
