import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import ViewConfig from '@/app/ops-analysis/components/widgetConfig';
import type { LayoutItem, TableColumnConfigItem } from '@/app/ops-analysis/types/dashBoard';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';

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
    getSourceDataByApiId: vi.fn(async () => ({
      data: { items: [{ host: 'web-1', status: 'up' }] },
    })),
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

afterEach(cleanup);

const tableDataSource = {
  id: 7,
  name: 'Hosts',
  chart_type: ['table'],
  field_schema: [
    { key: 'host', title: '主机', value_type: 'string' },
    { key: 'status', title: '状态', value_type: 'string' },
  ],
  params: [],
} as DatasourceItem;

const probedDataSource = {
  ...tableDataSource,
  field_schema: [],
} as DatasourceItem;

const actionColumn: TableColumnConfigItem = {
  key: '__interaction',
  title: '操作',
  visible: true,
  order: 0,
  columnType: 'actions',
};

const buildManager = (dataSource?: DatasourceItem) => ({
  selectedDataSource: dataSource,
  setSelectedDataSource: vi.fn(),
  ensureDataSource: async () => dataSource,
  setDefaultParamValues: vi.fn(),
  restoreUserParamValues: vi.fn(),
  processFormParamsForSubmit: () => [],
  dataSources: dataSource ? [dataSource] : [],
  dataSourcesLoading: false,
  fetchDataSources: vi.fn(),
  loadCanvasDataSources: vi.fn(),
  findDataSource: () => dataSource,
});

const tableItem = (columns?: TableColumnConfigItem[]): LayoutItem => ({
  i: 'table-1',
  x: 0,
  y: 0,
  w: 6,
  h: 4,
  name: '主机表',
  description: '',
  valueConfig: {
    dataSource: 7,
    chartType: 'table',
    dataSourceParams: [],
    tableConfig: columns ? { columns } : undefined,
  },
});

const renderTable = (dataSource: DatasourceItem, columns?: TableColumnConfigItem[]) => {
  render(
    <ViewConfig
      open
      item={tableItem(columns)}
      onClose={() => undefined}
      dataSourceManager={buildManager(dataSource) as never}
    />,
  );
};

describe('ViewConfig table columns', () => {
  it('旧配置只剩操作列时按 field_schema 生成默认列', async () => {
    renderTable(tableDataSource, [actionColumn]);

    expect(await screen.findByDisplayValue('主机')).toBeTruthy();
    expect(screen.getByDisplayValue('状态')).toBeTruthy();
    expect(screen.queryByText('dashboard.noDisplayColumns')).toBeNull();
  });

  it('没有已存列时不填展示列', async () => {
    renderTable(tableDataSource);

    await waitFor(() => {
      expect(screen.getByDisplayValue('主机表')).toBeTruthy();
    });
    expect(screen.getByText('dashboard.noDisplayColumns')).toBeTruthy();
    expect(screen.queryByDisplayValue('主机')).toBeNull();
  });

  it('没有 schema 时，只剩操作列就用探测到的字段', async () => {
    renderTable(probedDataSource, [actionColumn]);

    expect(await screen.findAllByDisplayValue('host')).toHaveLength(2);
    expect(screen.getAllByDisplayValue('status')).toHaveLength(2);
  });

  it('仍保留过滤后的数据列', async () => {
    renderTable(tableDataSource, [
      { key: 'cpu', title: 'CPU', visible: true, order: 0 },
      actionColumn,
    ]);

    expect(await screen.findByDisplayValue('CPU')).toBeTruthy();
    expect(screen.queryByDisplayValue('主机')).toBeNull();
  });
});
