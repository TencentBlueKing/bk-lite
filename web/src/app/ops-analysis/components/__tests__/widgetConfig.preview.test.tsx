import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { message } from 'antd';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import type { LayoutItem } from '@/app/ops-analysis/types/dashBoard';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import ViewConfig from '@/app/ops-analysis/components/widgetConfig';

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

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('@/hooks/useUnsavedConfirm', () => ({
  default: () => (_dirty: boolean, onClose?: () => void) => {
    onClose?.();
  },
}));

vi.mock('@/app/ops-analysis/api/dataSource', () => ({
  useDataSourceApi: () => ({
    getSourceDataByApiId: vi.fn(async () => ({ data: [] })),
    getDataSourceDetail: vi.fn(),
  }),
}));

vi.mock('@/app/ops-analysis/components/widgetSelector', () => ({
  default: () => null,
}));

vi.mock('@/app/ops-analysis/components/paramInputConfigEditor', () => ({
  ParamInputConfigEditor: () => null,
}));

vi.mock('@/app/ops-analysis/components/paramsConfig', () => ({
  default: () => null,
}));

vi.mock('@/app/ops-analysis/components/unifiedFilter', () => ({
  FilterBindingPanel: () => null,
}));

vi.mock(
  '@/app/ops-analysis/components/widgetConfig/hooks/useNetworkStatusTopologyConfig',
  () => ({
    useNetworkStatusTopologyConfig: () => ({
      instanceOptions: [],
      instanceOptionsLoading: false,
      resetInstanceOptions: vi.fn(),
      loadInstanceOptions: vi.fn(),
    }),
  }),
);

vi.mock('@/app/ops-analysis/hooks/useSingleValueConfig', () => ({
  useSingleValueConfig: () => ({
    thresholdColors: [],
    setThresholdColors: vi.fn(),
    selectedFields: [],
    setSelectedFields: vi.fn(),
    resetSingleValueConfig: vi.fn(),
  }),
}));

vi.mock('@/app/ops-analysis/components/widgetConfig/hooks/useTableConfig', () => ({
  useTableConfig: () => ({
    displayColumns: [],
    filterFields: [],
    detectedDisplayColumns: [],
    displayColumnsError: '',
    setDisplayColumns: vi.fn(),
    setFilterFields: vi.fn(),
    setDetectedDisplayColumns: vi.fn(),
    setDisplayColumnsError: vi.fn(),
    setParamsChangedAfterProbe: vi.fn(),
    resetTableConfig: vi.fn(),
    handleChartTypeChange: vi.fn(),
    probeDefaultDisplayColumns: vi.fn(async () => []),
  }),
}));

vi.mock('@/app/ops-analysis/components/widgetDataRenderer', () => ({
  default: (props: { widgetId: string; runtimeActive?: boolean }) => (
    <div
      data-testid="mock-preview-renderer"
      data-widget-id={props.widgetId}
      data-runtime-active={String(props.runtimeActive)}
    />
  ),
}));

afterEach(cleanup);

const lineDataSource: DatasourceItem = {
  id: 7,
  name: 'Line Mock',
  chart_type: ['line'],
  field_schema: [{ key: 'cpu', title: 'CPU', value_type: 'number' }],
  params: [],
} as DatasourceItem;

const lineItem = (): LayoutItem => ({
  i: 'cpu-1',
  x: 0,
  y: 0,
  w: 4,
  h: 3,
  name: 'CPU',
  description: '',
  valueConfig: {
    dataSource: 7,
    chartType: 'line',
    dataSourceParams: [],
  },
});

const sceneItem = (): LayoutItem => ({
  i: 'topo-1',
  x: 0,
  y: 0,
  w: 8,
  h: 6,
  name: '拓扑',
  description: '',
  valueConfig: {
    chartType: 'networkStatusTopology',
    sceneWidgetType: 'networkStatusTopology',
    networkStatusTopology: { instUuids: ['n-1'], nodeLimit: 100 },
  },
});

const buildManager = (dataSource?: DatasourceItem) => {
  let selectedDataSource: DatasourceItem | undefined = dataSource;
  return {
    selectedDataSource,
    setSelectedDataSource: (next?: DatasourceItem) => {
      selectedDataSource = next;
    },
    ensureDataSource: async () => dataSource,
    setDefaultParamValues: vi.fn(),
    restoreUserParamValues: vi.fn(),
    processFormParamsForSubmit: (params: Record<string, unknown>) => params,
    dataSources: dataSource ? [dataSource] : [],
    dataSourcesLoading: false,
    fetchDataSources: vi.fn(),
    loadCanvasDataSources: vi.fn(),
    findDataSource: () => dataSource,
  };
};

describe('ViewConfig preview drawer', () => {
  it('switches data and interaction with underline tabs', async () => {
    const user = userEvent.setup();
    render(
      <ViewConfig
        open
        item={lineItem()}
        onClose={() => undefined}
        dataSourceManager={buildManager(lineDataSource) as never}
      />,
    );

    const interactionTab = await screen.findByRole('tab', { name: 'dashboard.interactionTab' });
    const dataTab = screen.getByRole('tab', { name: 'dashboard.interactionDataTab' });
    expect(interactionTab.closest('.ant-tabs-nav')).toBeTruthy();
    expect(dataTab.querySelector('svg')).toBeTruthy();
    expect(interactionTab.querySelector('svg')).toBeTruthy();
    expect(dataTab.getAttribute('aria-selected')).toBe('true');

    await user.click(interactionTab);
    expect(interactionTab.getAttribute('aria-selected')).toBe('true');
    expect(screen.getByText('dashboard.interactionLinkType')).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'dashboard.interactionSection' })).toBeNull();
    expect(screen.queryByRole('heading', { name: '交互' })).toBeNull();
  });

  it('opens a preview pane keyed by the widget, then collapses it', async () => {
    const user = userEvent.setup();
    render(
      <ViewConfig
        open
        item={lineItem()}
        onClose={() => undefined}
        dataSourceManager={buildManager(lineDataSource) as never}
      />,
    );

    const previewButton = await screen.findByTestId('widget-config-preview-button');
    expect(screen.queryByTestId('widget-config-preview-aside')).toBeNull();

    await user.click(previewButton);

    const aside = await screen.findByTestId('widget-config-preview-aside');
    expect(aside).toBeTruthy();
    await waitFor(() => {
      expect(screen.getByTestId('mock-preview-renderer').getAttribute('data-widget-id')).toBe(
        'config-preview:cpu-1',
      );
    });
    expect(screen.getByTestId('mock-preview-renderer').getAttribute('data-runtime-active')).toBe(
      'true',
    );
    expect(previewButton.textContent).toBe('dashboard.configPreviewCollapse');

    await user.click(previewButton);
    await waitFor(() => {
      expect(screen.queryByTestId('widget-config-preview-aside')).toBeNull();
    });
  });

  it('does not open preview for a data widget without a data source', async () => {
    const user = userEvent.setup();
    render(
      <ViewConfig
        open
        item={{
          ...lineItem(),
          valueConfig: { chartType: 'line' },
        }}
        onClose={() => undefined}
        dataSourceManager={buildManager(undefined) as never}
      />,
    );

    await user.click(await screen.findByTestId('widget-config-preview-button'));
    expect(screen.queryByTestId('widget-config-preview-aside')).toBeNull();
  });

  it('allows scene widgets to preview without a data source', async () => {
    const user = userEvent.setup();
    render(
      <ViewConfig
        open
        item={sceneItem()}
        onClose={() => undefined}
        dataSourceManager={buildManager(undefined) as never}
      />,
    );

    await user.click(await screen.findByTestId('widget-config-preview-button'));
    await waitFor(() => {
      expect(screen.getByTestId('mock-preview-renderer').getAttribute('data-widget-id')).toBe(
        'config-preview:topo-1',
      );
    });
  });
});

describe('ViewConfig screen panel', () => {
  it('embeds the form without a drawer or preview button', async () => {
    render(
      <ViewConfig
        open
        variant="panel"
        item={lineItem()}
        onClose={() => undefined}
        dataSourceManager={buildManager(lineDataSource) as never}
        surface="screen"
      />,
    );

    expect(await screen.findByTestId('widget-config-panel')).toBeTruthy();
    expect(screen.queryByTestId('widget-config-preview-button')).toBeNull();
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.getByText('common.confirm')).toBeTruthy();
  });

  it('does not reload the data form when only widget appearance changes', async () => {
    const ensureDataSource = vi.fn(async () => lineDataSource);
    const manager = {
      ...buildManager(lineDataSource),
      ensureDataSource,
    };
    const item = lineItem();
    const view = render(
      <ViewConfig
        open
        variant="panel"
        item={item}
        onClose={() => undefined}
        dataSourceManager={manager as never}
        surface="screen"
      />,
    );

    await waitFor(() => {
      expect(ensureDataSource).toHaveBeenCalledTimes(1);
    });

    view.rerender(
      <ViewConfig
        open
        variant="panel"
        item={{
          ...item,
          x: 40,
          y: 80,
          valueConfig: {
            ...item.valueConfig,
            appearance: { frame: 'bare' },
          },
        }}
        onClose={() => undefined}
        dataSourceManager={manager as never}
        surface="screen"
      />,
    );

    await waitFor(() => {
      expect(ensureDataSource).toHaveBeenCalledTimes(1);
    });

    view.rerender(
      <ViewConfig
        open
        variant="panel"
        item={{
          ...item,
          valueConfig: {
            ...item.valueConfig,
            dataSource: 8,
          },
        }}
        onClose={() => undefined}
        dataSourceManager={manager as never}
        surface="screen"
      />,
    );

    await waitFor(() => {
      expect(ensureDataSource).toHaveBeenCalledTimes(2);
    });
  });
});

const waitForOpenedWidget = async () => {
  await waitFor(() => {
    expect(screen.getByDisplayValue('CPU')).toBeTruthy();
  });
};

describe('ViewConfig interaction validation', () => {
  it('数据页保存时缺 URL，切回交互页并显示错误', async () => {
    const user = userEvent.setup();
    const errorSpy = vi.spyOn(message, 'error').mockImplementation(() => ({}) as never);
    render(
      <ViewConfig
        open
        item={lineItem()}
        onClose={() => undefined}
        dataSourceManager={buildManager(lineDataSource) as never}
      />,
    );

    await waitForOpenedWidget();
    await user.click(screen.getByRole('tab', { name: 'dashboard.interactionTab' }));
    await user.click(screen.getByText('dashboard.interactionTitleLink'));
    await user.click(screen.getByRole('tab', { name: 'dashboard.interactionDataTab' }));
    await user.click(screen.getByRole('button', { name: 'common.confirm' }));

    await waitFor(() => {
      expect(
        screen.getByRole('tab', { name: 'dashboard.interactionTab' }).getAttribute('aria-selected'),
      ).toBe('true');
    });
    expect(await screen.findByText('dashboard.interactionUrlRequired')).toBeTruthy();
    expect(errorSpy.mock.calls.map((call) => call[0])).not.toContain('common.saveFailed');
    errorSpy.mockRestore();
  });

  it('大屏样式或数据页保存失败时切到交互页', async () => {
    const user = userEvent.setup();
    const errorSpy = vi.spyOn(message, 'error').mockImplementation(() => ({}) as never);
    const onConfigSectionChange = vi.fn();
    const view = render(
      <ViewConfig
        open
        variant="panel"
        configSection="interaction"
        onConfigSectionChange={onConfigSectionChange}
        item={lineItem()}
        onClose={() => undefined}
        dataSourceManager={buildManager(lineDataSource) as never}
        surface="screen"
      />,
    );

    await waitForOpenedWidget();
    await user.click(screen.getByText('dashboard.interactionTitleLink'));
    view.rerender(
      <ViewConfig
        open
        variant="panel"
        configSection="data"
        onConfigSectionChange={onConfigSectionChange}
        item={lineItem()}
        onClose={() => undefined}
        dataSourceManager={buildManager(lineDataSource) as never}
        surface="screen"
      />,
    );
    await user.click(screen.getByRole('button', { name: 'common.confirm' }));

    await waitFor(() => {
      expect(onConfigSectionChange).toHaveBeenCalledWith('interaction');
    });
    expect(errorSpy.mock.calls.map((call) => call[0])).not.toContain('common.saveFailed');
    errorSpy.mockRestore();
  });
});
