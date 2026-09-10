import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import WidgetConfigPreview from '@/app/ops-analysis/components/widgetConfig/widgetConfigPreview';

const rendererProps = vi.hoisted(() => vi.fn());

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('@/app/ops-analysis/components/widgetDataRenderer', () => ({
  default: (props: {
    widgetId: string;
    runtimeActive?: boolean;
    reloadVersion?: string;
    chartType?: string;
  }) => {
    rendererProps(props);
    return (
      <div
        data-testid="mock-preview-renderer"
        data-widget-id={props.widgetId}
        data-runtime-active={String(props.runtimeActive)}
        data-reload-version={props.reloadVersion}
        data-chart-type={props.chartType}
      />
    );
  },
}));

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

beforeEach(() => {
  rendererProps.mockClear();
});

afterEach(cleanup);

const previewConfig = {
  name: 'CPU',
  description: 'saved desc',
  chartType: 'line',
  dataSource: 7,
};

const renderPreview = (
  override: Partial<React.ComponentProps<typeof WidgetConfigPreview>> = {},
) =>
  render(
    <WidgetConfigPreview
      widgetId="config-preview:cpu-1"
      previewed
      stale={false}
      config={previewConfig}
      reloadVersion={3}
      rawData={null}
      onRawData={vi.fn()}
      {...override}
    />,
  );

describe('WidgetConfigPreview pane', () => {
  it('shows empty hint before the first preview', () => {
    renderPreview({ previewed: false, config: null });

    expect(screen.getByTestId('widget-config-preview-empty').textContent).toBe(
      'dashboard.configPreviewEmpty',
    );
    expect(screen.queryByTestId('widget-config-preview-chart')).toBeNull();
    expect(screen.queryByTestId('mock-preview-renderer')).toBeNull();
  });

  it('renders the chart with a distinct preview widget id and live title', async () => {
    renderPreview({
      liveName: '草稿名',
      liveDescription: '草稿描述',
    });

    expect(screen.getByText('草稿名')).toBeTruthy();
    expect(screen.getByText('草稿描述')).toBeTruthy();

    await waitFor(() => {
      expect(screen.getByTestId('mock-preview-renderer').getAttribute('data-widget-id')).toBe(
        'config-preview:cpu-1',
      );
    });
    expect(screen.getByTestId('mock-preview-renderer').getAttribute('data-runtime-active')).toBe(
      'true',
    );
    expect(screen.getByTestId('mock-preview-renderer').getAttribute('data-reload-version')).toBe(
      '3',
    );
    expect(screen.queryByTestId('widget-config-preview-stale')).toBeNull();
  });

  it('shows stale badge and refresh control when the draft diverged', async () => {
    const onRefresh = vi.fn();
    const user = userEvent.setup();
    renderPreview({ stale: true, onRefresh });

    expect(screen.getByTestId('widget-config-preview-stale').textContent).toBe(
      'dashboard.configPreviewStale',
    );

    await user.click(screen.getByTestId('widget-config-preview-refresh'));
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it('shows pretty-printed raw json on the raw data tab', async () => {
    const user = userEvent.setup();
    const rawData = { items: [{ cpu: 1 }] };

    renderPreview({ rawData });

    await user.click(screen.getByText('dashboard.configPreviewRawJson'));

    expect(screen.getByTestId('widget-config-preview-json').textContent).toBe(
      JSON.stringify(rawData, null, 2),
    );
    expect(screen.getByTestId('widget-config-preview-copy-json')).toBeTruthy();
  });
});
