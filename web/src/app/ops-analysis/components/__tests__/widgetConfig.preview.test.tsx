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
    selectedFields: ['value'],
    setSelectedFields: vi.fn(),
    resetSingleValueConfig: vi.fn(),
    singleValueTreeData: [],
    loadingSingleValueData: false,
    compareAvailable: false,
    handleSingleValueFieldChange: vi.fn(),
    handleThresholdChange: vi.fn(),
    handleThresholdBlur: vi.fn(),
    addThreshold: vi.fn(),
    removeThreshold: vi.fn(),
  }),
}));

vi.mock('@/app/cmdb/(pages)/assetManage/management/list/selectIcon', () => ({
  default: () => null,
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
  default: (props: {
    widgetId: string;
    runtimeActive?: boolean;
    config?: { chartThemeMode?: string; singleStyle?: unknown };
    screenRenderContext?: unknown;
    onTopologyLayoutChange?: unknown;
  }) => (
    <div
      data-testid="mock-preview-renderer"
      data-widget-id={props.widgetId}
      data-runtime-active={String(props.runtimeActive)}
      data-chart-theme={props.config?.chartThemeMode ?? ''}
      data-single-style={
        props.config?.singleStyle ? JSON.stringify(props.config.singleStyle) : ''
      }
      data-screen-context={props.screenRenderContext ? 'yes' : 'no'}
      data-topology-change={props.onTopologyLayoutChange ? 'yes' : 'no'}
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

const singleItem = (): LayoutItem => ({
  i: 'single-1',
  x: 0,
  y: 0,
  w: 4,
  h: 3,
  name: '在线数',
  description: '',
  valueConfig: {
    dataSource: 7,
    chartType: 'single',
    dataSourceParams: [],
    selectedFields: ['value'],
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
    expect(document.querySelector('[data-screen-widget-theme]')).toBeNull();

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
  it('embeds the form with a preview button and no drawer', async () => {
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
    expect(screen.getByTestId('widget-config-preview-button')).toBeTruthy();
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.getByText('common.confirm')).toBeTruthy();
  });

  it('opens a light dashboard preview into the external host', async () => {
    const user = userEvent.setup();
    const host = document.createElement('div');
    document.body.appendChild(host);
    const ensureDataSource = vi.fn(async () => lineDataSource);
    const manager = {
      ...buildManager(lineDataSource),
      ensureDataSource,
    };
    const singleStyle = { showIcon: true, align: 'center' as const };
    const item = singleItem();
    item.valueConfig = { ...item.valueConfig, chartThemeMode: 'screen-dark' };
    const view = render(
      <ViewConfig
        open
        variant="panel"
        item={item}
        onClose={() => undefined}
        dataSourceManager={manager as never}
        surface="screen"
        showSingleValueStyle={false}
        previewHost={host}
        previewSingleStyle={singleStyle}
      />,
    );

    const previewButton = await screen.findByTestId('widget-config-preview-button');
    expect(host.querySelector('[data-testid="widget-config-preview-aside"]')).toBeNull();
    expect(
      screen.getByTestId('widget-config-panel').querySelector(
        '[data-testid="widget-config-preview-aside"]',
      ),
    ).toBeNull();

    await user.click(previewButton);

    await waitFor(() => {
      expect(host.querySelector('[data-testid="widget-config-preview-aside"]')).toBeTruthy();
    });
    expect(
      screen.getByTestId('widget-config-panel').querySelector(
        '[data-testid="widget-config-preview-aside"]',
      ),
    ).toBeNull();
    const aside = host.querySelector('[data-testid="widget-config-preview-aside"]') as HTMLElement;
    expect(document.querySelector('[data-screen-widget-theme]')).toBeNull();
    expect(aside.style.background).toBe('');
    expect(aside.className).toContain('bg-(--color-bg)');
    expect(aside.className).toContain('border-(--color-border-1)');
    const renderer = screen.getByTestId('mock-preview-renderer');
    expect(renderer.getAttribute('data-chart-theme')).toBe('');
    expect(renderer.getAttribute('data-single-style')).toBe(JSON.stringify(singleStyle));
    expect(renderer.getAttribute('data-screen-context')).toBe('no');
    expect(renderer.getAttribute('data-topology-change')).toBe('no');
    expect(previewButton.textContent).toBe('dashboard.configPreviewCollapse');

    view.rerender(
      <ViewConfig
        open
        variant="panel"
        item={item}
        onClose={() => undefined}
        dataSourceManager={manager as never}
        surface="screen"
        showSingleValueStyle={false}
        previewHost={host}
        previewSingleStyle={{ showIcon: true, align: 'right' }}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('mock-preview-renderer').getAttribute('data-single-style')).toBe(
        JSON.stringify({ showIcon: true, align: 'right' }),
      );
    });
    expect(screen.getByTestId('mock-preview-renderer').getAttribute('data-chart-theme')).toBe('');
    expect(document.querySelector('[data-screen-widget-theme]')).toBeNull();
    expect(ensureDataSource).toHaveBeenCalledTimes(1);

    await user.click(screen.getByTestId('widget-config-preview-button'));
    await waitFor(() => {
      expect(host.querySelector('[data-testid="widget-config-preview-aside"]')).toBeNull();
    });
    host.remove();
  });

  it('collapses the preview when the selected widget changes', async () => {
    const user = userEvent.setup();
    const host = document.createElement('div');
    document.body.appendChild(host);
    const view = render(
      <ViewConfig
        open
        variant="panel"
        item={lineItem()}
        onClose={() => undefined}
        dataSourceManager={buildManager(lineDataSource) as never}
        surface="screen"
        previewHost={host}
      />,
    );

    await user.click(await screen.findByTestId('widget-config-preview-button'));
    await waitFor(() => {
      expect(host.querySelector('[data-testid="widget-config-preview-aside"]')).toBeTruthy();
    });

    view.rerender(
      <ViewConfig
        open
        variant="panel"
        item={{ ...lineItem(), i: 'mem-1', name: '内存' }}
        onClose={() => undefined}
        dataSourceManager={buildManager(lineDataSource) as never}
        surface="screen"
        previewHost={host}
      />,
    );

    await waitFor(() => {
      expect(host.querySelector('[data-testid="widget-config-preview-aside"]')).toBeNull();
    });
    expect(screen.getByTestId('widget-config-preview-button').textContent).toBe('common.preview');

    view.unmount();
    expect(host.querySelector('[data-testid="widget-config-preview-aside"]')).toBeNull();
    host.remove();
  });

  it('collapses the preview when a pending widget switches chart type', async () => {
    const user = userEvent.setup();
    const host = document.createElement('div');
    document.body.appendChild(host);
    const pendingLine = { ...lineItem(), i: 'pending:line:' };
    const view = render(
      <ViewConfig
        open
        variant="panel"
        item={pendingLine}
        onClose={() => undefined}
        dataSourceManager={buildManager(lineDataSource) as never}
        surface="screen"
        previewHost={host}
      />,
    );

    await user.click(await screen.findByTestId('widget-config-preview-button'));
    await waitFor(() => {
      expect(host.querySelector('[data-testid="widget-config-preview-aside"]')).toBeTruthy();
    });

    view.rerender(
      <ViewConfig
        open
        variant="panel"
        item={{ ...lineItem(), i: 'pending:pie:', name: '分布' }}
        onClose={() => undefined}
        dataSourceManager={buildManager(lineDataSource) as never}
        surface="screen"
        previewHost={host}
      />,
    );

    await waitFor(() => {
      expect(host.querySelector('[data-testid="widget-config-preview-aside"]')).toBeNull();
    });
    expect(screen.getByTestId('widget-config-preview-button').textContent).toBe('common.preview');
    host.remove();
  });

  it('keeps the preview open when the same widget data changes', async () => {
    const user = userEvent.setup();
    const host = document.createElement('div');
    document.body.appendChild(host);
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
        previewHost={host}
      />,
    );

    await waitFor(() => {
      expect(ensureDataSource).toHaveBeenCalledTimes(1);
    });
    await user.click(await screen.findByTestId('widget-config-preview-button'));
    await waitFor(() => {
      expect(host.querySelector('[data-testid="widget-config-preview-aside"]')).toBeTruthy();
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
        previewHost={host}
      />,
    );

    await waitFor(() => {
      expect(ensureDataSource).toHaveBeenCalledTimes(2);
    });
    expect(host.querySelector('[data-testid="widget-config-preview-aside"]')).toBeTruthy();
    expect(screen.getByTestId('widget-config-preview-button').textContent).toBe(
      'dashboard.configPreviewCollapse',
    );
    host.remove();
  });

  it('does not write preview theme or single style into the saved config', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(
      <ViewConfig
        open
        variant="panel"
        item={singleItem()}
        onClose={() => undefined}
        onConfirm={onConfirm}
        dataSourceManager={buildManager(lineDataSource) as never}
        surface="screen"
        showSingleValueStyle={false}
        previewSingleStyle={{ showIcon: true, align: 'center' }}
      />,
    );

    await waitFor(() => {
      expect(screen.getByDisplayValue('在线数')).toBeTruthy();
    });
    await user.click(screen.getByTestId('widget-config-preview-button'));
    await user.click(screen.getByRole('button', { name: 'common.confirm' }));

    await waitFor(() => {
      expect(onConfirm).toHaveBeenCalledTimes(1);
    });
    const saved = onConfirm.mock.calls[0][0] as {
      chartThemeMode?: string;
      singleStyle?: unknown;
    };
    expect(saved.chartThemeMode).toBeUndefined();
    expect(saved.singleStyle).toBeUndefined();
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

  it('does not reload the data form when only single-value style changes', async () => {
    const ensureDataSource = vi.fn(async () => lineDataSource);
    const manager = {
      ...buildManager(lineDataSource),
      ensureDataSource,
    };
    const item = singleItem();
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
          valueConfig: {
            ...item.valueConfig,
            singleStyle: { showIcon: true, align: 'center' },
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
            descriptionField: 'note',
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

describe('ViewConfig single style tab', () => {
  it('places style between data and interaction only for single widgets', async () => {
    const user = userEvent.setup();
    const view = render(
      <ViewConfig
        open
        item={singleItem()}
        onClose={() => undefined}
        dataSourceManager={buildManager(lineDataSource) as never}
      />,
    );

    const styleTab = await screen.findByRole('tab', { name: 'dashboard.singleStyleTab' });
    const dataTab = screen.getByRole('tab', { name: 'dashboard.interactionDataTab' });
    const interactionTab = screen.getByRole('tab', { name: 'dashboard.interactionTab' });
    expect(dataTab.compareDocumentPosition(styleTab)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    expect(styleTab.compareDocumentPosition(interactionTab)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);

    await user.click(styleTab);
    expect(styleTab.getAttribute('aria-selected')).toBe('true');
    expect(screen.getByText('dashboard.singleStyleIcon')).toBeTruthy();
    expect(screen.getByText('dashboard.singleStyleAlign')).toBeTruthy();
    expect(screen.queryByText('dashboard.singleStylePreviewHint')).toBeNull();
    expect(screen.queryByText('dashboard.singleStyleIconSource')).toBeNull();
    expect(screen.getByText('topology.nodeConfig.valueMappings')).toBeTruthy();

    await user.click(screen.getByRole('switch', { name: 'dashboard.singleStyleIcon' }));
    expect(await screen.findByText('dashboard.singleStyleIconSource')).toBeTruthy();
    expect(
      screen.getByRole('radio', { name: 'dashboard.singleStyleIconBuiltin' }).closest('label')?.className,
    ).toContain('ant-radio-button-wrapper-checked');
    expect(screen.queryByTestId('single-style-file-input')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'dashboard.singleStyleAlignRight' }));
    expect(screen.getByRole('button', { name: 'dashboard.singleStyleAlignRight' }).getAttribute('aria-pressed')).toBe('true');

    view.rerender(
      <ViewConfig
        open
        item={lineItem()}
        onClose={() => undefined}
        dataSourceManager={buildManager(lineDataSource) as never}
      />,
    );
    await waitFor(() => {
      expect(screen.queryByRole('tab', { name: 'dashboard.singleStyleTab' })).toBeNull();
    });
  });

  it('hides the style tab when topology turns single value style off', async () => {
    render(
      <ViewConfig
        open
        showSingleValueStyle={false}
        item={singleItem()}
        onClose={() => undefined}
        dataSourceManager={buildManager(lineDataSource) as never}
      />,
    );

    expect(await screen.findByRole('tab', { name: 'dashboard.interactionDataTab' })).toBeTruthy();
    expect(screen.getByRole('tab', { name: 'dashboard.interactionTab' })).toBeTruthy();
    expect(screen.queryByRole('tab', { name: 'dashboard.singleStyleTab' })).toBeNull();
    expect(screen.queryByText('dashboard.singleStyleIcon')).toBeNull();
  });

  it('keeps style controls out of the screen data panel', async () => {
    render(
      <ViewConfig
        open
        variant="panel"
        configSection="data"
        surface="screen"
        showSingleValueStyle={false}
        item={singleItem()}
        onClose={() => undefined}
        dataSourceManager={buildManager(lineDataSource) as never}
      />,
    );

    expect(await screen.findByText('topology.nodeConfig.valueMappings')).toBeTruthy();
    expect(screen.queryByText('dashboard.singleStyleIcon')).toBeNull();
    expect(screen.queryByText('dashboard.singleStylePreviewHint')).toBeNull();
    expect(screen.queryByRole('tab', { name: 'dashboard.singleStyleTab' })).toBeNull();
  });
});
