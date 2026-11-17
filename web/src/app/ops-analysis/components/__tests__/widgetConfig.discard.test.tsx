import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import type { LayoutItem, UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import ViewConfig from '@/app/ops-analysis/components/widgetConfig';

const guardCalls = vi.hoisted(() => [] as boolean[]);

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
  default: () => (dirty: boolean | (() => boolean), onClose?: () => void) => {
    const value = typeof dirty === 'function' ? dirty() : dirty;
    guardCalls.push(value);
    if (!value) onClose?.();
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
    handleAddFilterField: vi.fn(),
    handleDeleteFilterField: vi.fn(),
    handleFilterFieldChange: vi.fn(),
    handleAddDisplayColumn: vi.fn(),
    handleDeleteDisplayColumn: vi.fn(),
    handleDisplayColumnChange: vi.fn(),
    handleDisplayColumnStyleChange: vi.fn(),
    handleDisplayColumnKeyBlur: vi.fn(),
    handleDisplayColumnDragEnd: vi.fn(),
    handleReProbeColumns: vi.fn(),
    createDefaultFilterField: vi.fn(),
    createDefaultDisplayColumn: vi.fn(),
  }),
}));

vi.mock('@/app/ops-analysis/components/widgetDataRenderer', () => ({
  default: () => <div data-testid="mock-preview-renderer" />,
}));

afterEach(() => {
  guardCalls.length = 0;
  cleanup();
});

const filterDataSource = {
  id: 7,
  name: 'Line Mock',
  chart_type: ['line'],
  field_schema: [{ key: 'cpu', title: 'CPU', value_type: 'number' }],
  params: [
    { name: 'env', type: 'string', filterType: 'filter', alias_name: '环境' },
  ],
} as DatasourceItem;

const filterDefinitions: UnifiedFilterDefinition[] = [
  {
    id: 'env__string',
    key: 'env',
    name: '环境',
    type: 'string',
    order: 0,
    enabled: true,
  },
];

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

const buildManager = () => ({
  selectedDataSource: filterDataSource,
  setSelectedDataSource: vi.fn(),
  ensureDataSource: async () => filterDataSource,
  setDefaultParamValues: vi.fn(),
  restoreUserParamValues: vi.fn(),
  processFormParamsForSubmit: () => [],
  dataSources: [filterDataSource],
  dataSourcesLoading: false,
  fetchDataSources: vi.fn(),
  loadCanvasDataSources: vi.fn(),
  findDataSource: () => filterDataSource,
});

const renderScreenConfig = (onClose = vi.fn()) => render(
  <ViewConfig
    open
    variant="panel"
    surface="screen"
    item={lineItem()}
    onClose={onClose}
    dataSourceManager={buildManager() as never}
    filterDefinitions={filterDefinitions}
  />,
);

describe('screen widget config cancel', () => {
  it('closes immediately when nothing was edited', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    renderScreenConfig(onClose);

    expect(await screen.findByRole('button', { name: 'opsAnalysis.screen.applyConfig' })).toBeTruthy();
    await user.click(screen.getByTestId('widget-config-cancel'));

    expect(guardCalls).toEqual([false]);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('asks before leaving after the filter linkage switch changes', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    renderScreenConfig(onClose);

    const linkage = await screen.findByRole('switch');
    await waitFor(() => {
      expect(screen.getByDisplayValue('CPU')).toBeTruthy();
    });
    await user.click(linkage);
    await user.click(screen.getByTestId('widget-config-cancel'));

    expect(guardCalls.at(-1)).toBe(true);
    expect(onClose).not.toHaveBeenCalled();
  });

  it('keeps the drawer confirm label', async () => {
    render(
      <ViewConfig
        open
        item={lineItem()}
        onClose={() => undefined}
        dataSourceManager={buildManager() as never}
      />,
    );

    expect(await screen.findByRole('button', { name: 'common.confirm' })).toBeTruthy();
  });
});
