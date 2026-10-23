import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import ComSingle from '../comSingle';

vi.mock('echarts-for-react', () => ({ default: () => <div data-testid="sparkline" /> }));
vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock('@/app/cmdb/utils/modelIcon', () => ({
  getModelIconUrl: ({ icn }: { icn: string }) => `/assets/${icn}.svg`,
}));
vi.mock('@/app/ops-analysis/components/ops-analysis-metric-value', () => ({
  default: ({
    main,
    unit,
    className,
  }: {
    main: React.ReactNode;
    unit?: React.ReactNode;
    className?: string;
  }) => (
    <div data-testid="main-value" className={className}>
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

const valueConfig = {
  chartType: 'single' as const,
  selectedFields: ['value'],
};

describe('ComSingle style', () => {
  it('keeps the legacy card when style is absent', () => {
    render(<ComSingle rawData={{ value: 12 }} config={valueConfig} />);

    expect(screen.queryByTestId('single-value-icon')).toBeNull();
    expect(screen.getByTestId('single-value-body').getAttribute('data-value-align')).toBe('left');
    expect(screen.getByTestId('single-value-body').getAttribute('data-meta-align')).toBe('left');
    expect(screen.getByTestId('main-value').className).not.toMatch(/justify-center/);
  });

  it('keeps a screen-theme value centered until alignment is explicit', () => {
    render(
      <ComSingle
        rawData={{ value: 12, note: '说明' }}
        config={{
          ...valueConfig,
          chartThemeMode: 'screen-dark',
          descriptionField: 'note',
        }}
      />,
    );

    const body = screen.getByTestId('single-value-body');
    expect(body.getAttribute('data-value-align')).toBe('center');
    expect(body.getAttribute('data-meta-align')).toBe('left');
    expect(screen.getByTestId('main-value').className).toMatch(/justify-center/);
    expect(screen.getByTestId('single-description').style.textAlign).toBe('');
  });

  it('aligns the value, description and compare together and keeps the sparkline full width', () => {
    render(
      <ComSingle
        rawData={{ value: 12, note: '说明' }}
        baselineData={{ value: 10 }}
        config={{
          ...valueConfig,
          chartThemeMode: 'screen-dark',
          descriptionField: 'note',
          compare: true,
          singleStyle: { align: 'right' },
        }}
      />,
    );

    expect(screen.getByTestId('single-value-body').getAttribute('data-value-align')).toBe('right');
    expect(screen.getByTestId('single-value-body').getAttribute('data-meta-align')).toBe('right');
    expect(screen.getByTestId('main-value').className).toMatch(/justify-end/);
    expect(screen.getByTestId('single-description').style.textAlign).toBe('right');
    expect(screen.getByTestId('single-compare').className).toMatch(/justify-end/);
    const sparkline = screen.getByTestId('sparkline');
    expect(sparkline.parentElement?.className).toMatch(/w-full/);
    expect(sparkline.closest('[data-testid="single-value-body"]')).toBeNull();
  });

  it('renders a builtin icon on the right and an uploaded image with img', () => {
    const builtin = render(
      <ComSingle
        rawData={{ value: 8 }}
        config={{
          ...valueConfig,
          singleStyle: {
            showIcon: true,
            iconSource: 'builtin',
            iconKey: 'cc-host',
            iconPosition: 'right',
            iconSize: 'small',
          },
        }}
      />,
    );
    const icon = screen.getByTestId('single-value-icon');
    expect(icon.tagName).toBe('IMG');
    expect(icon.getAttribute('src')).toBe('/assets/cc-host.svg');
    expect(screen.getByTestId('main-value').compareDocumentPosition(icon)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
    builtin.unmount();

    render(
      <ComSingle
        rawData={{ value: 8 }}
        config={{
          ...valueConfig,
          chartThemeMode: 'screen-light',
          singleStyle: {
            showIcon: true,
            iconSource: 'upload',
            iconImage: 'data:image/png;base64,abc',
            align: 'center',
          },
        }}
      />,
    );
    expect(screen.getByTestId('single-value-icon').getAttribute('src')).toBe(
      'data:image/png;base64,abc',
    );
    expect(screen.getByTestId('single-value-body').getAttribute('data-value-align')).toBe('center');
  });

  it('ignores a closed icon switch and a non-image upload', () => {
    render(
      <ComSingle
        rawData={{ value: 8 }}
        config={{
          ...valueConfig,
          singleStyle: {
            showIcon: false,
            iconKey: 'cc-host',
            iconImage: 'javascript:alert(1)',
          },
        }}
      />,
    );
    expect(screen.queryByTestId('single-value-icon')).toBeNull();
  });
});
