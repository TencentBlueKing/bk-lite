// @vitest-environment jsdom

import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import type { DatasourceItem, ParamItem } from '@/app/ops-analysis/types/dataSource';
import type { LayoutItem } from '@/app/ops-analysis/types/dashBoard';
import {
  getDataSourceFormParamInitialValue,
  processDataSourceFormParamsForSubmit,
} from '@/app/ops-analysis/utils/dataSourceFormParams';
import ViewConfig from '@/app/ops-analysis/components/widgetConfig';

const calls = vi.hoisted(() => ({
  getSourceDataByApiId: vi.fn(),
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

vi.mock('@/app/ops-analysis/context/common', () => ({
  useOpsAnalysis: () => ({ canvasDataSourceLookupStatus: 'ready', dataSources: [] }),
}));

vi.mock('@/app/ops-analysis/api/dataSource', async () => {
  const actual = await vi.importActual<typeof import('@/app/ops-analysis/api/dataSource')>(
    '@/app/ops-analysis/api/dataSource',
  );
  return {
    ...actual,
    useDataSourceApi: () => ({
      getSourceDataByApiId: (...args: unknown[]) => calls.getSourceDataByApiId(...args),
      getDataSourceDetail: vi.fn(),
      getDataSourceList: vi.fn(),
    }),
  };
});

vi.mock('@/app/ops-analysis/components/widgetSelector', () => ({
  default: () => null,
}));

vi.mock('@/app/ops-analysis/components/paramInputConfigEditor', () => ({
  ParamInputConfigEditor: () => null,
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

vi.mock('@/app/ops-analysis/components/widgetRegistry', () => ({
  getWidgetComponent: (chartType?: string) => function FakeChart() {
    return <div data-testid="chart-renderer" data-chart-type={chartType} />;
  },
}));

const modelParam: ParamItem = {
  name: 'model_id',
  alias_name: '模型',
  type: 'string',
  filterType: 'params',
  value: 'host',
};

const datasource: DatasourceItem = {
  id: 149,
  created_at: '',
  updated_at: '',
  created_by: '',
  updated_by: '',
  domain: '',
  updated_by_domain: '',
  name: 'CMDB 实例查询',
  source_type: 'nats',
  desc: '',
  params: [modelParam],
  chart_type: ['table', 'line'],
  namespaces: [],
};

const tableItem = (): LayoutItem => ({
  i: 'cmdb-1',
  x: 0,
  y: 0,
  w: 6,
  h: 4,
  name: 'CMDB 实例查询',
  description: '按所选模型查询当前权限范围内的实例',
  valueConfig: {
    dataSource: datasource.id,
    chartType: 'table',
    dataSourceParams: [modelParam],
  },
});

const hostRows = {
  items: [{ inst_uuid: '4c4b9718', inst_name: 'bare-01', model_id: 'host' }],
  count: 16,
  fields: [],
};

const nicRows = {
  items: [{ inst_uuid: 'aa11', inst_name: 'nic-01', model_id: 'nic' }],
  count: 2,
  fields: [],
};

const buildManager = (dataSource: DatasourceItem) => {
  let selectedDataSource: DatasourceItem | undefined = dataSource;
  return {
    selectedDataSource,
    setSelectedDataSource: (next?: DatasourceItem) => {
      selectedDataSource = next;
    },
    ensureDataSource: async () => dataSource,
    setDefaultParamValues: (params: ParamItem[], formParams: Record<string, unknown>) => {
      params.forEach((param) => {
        formParams[param.name] = getDataSourceFormParamInitialValue(param);
      });
    },
    restoreUserParamValues: (dataSourceParams: ParamItem[], formParams: Record<string, unknown>) => {
      dataSourceParams.forEach((param) => {
        if (param.value !== undefined) formParams[param.name] = param.value;
      });
    },
    processFormParamsForSubmit: processDataSourceFormParamsForSubmit,
    dataSources: [dataSource],
    dataSourcesLoading: false,
    fetchDataSources: vi.fn(),
    loadCanvasDataSources: vi.fn(),
    findDataSource: () => dataSource,
  };
};

const requestedModel = (call: unknown[]) => {
  const params = call[1] as { model_id?: string } | undefined;
  return params?.model_id;
};

afterEach(() => {
  cleanup();
  calls.getSourceDataByApiId.mockReset();
});

describe('ViewConfig table preview refresh', () => {
  it('shows raw json after the first preview and refetches the edited model on manual refresh', async () => {
    const user = userEvent.setup();
    calls.getSourceDataByApiId.mockImplementation(async (_id: unknown, params?: { model_id?: string }) => (
      params?.model_id === 'nic' ? { data: nicRows } : { data: hostRows }
    ));

    render(
      <ViewConfig
        open
        item={tableItem()}
        onClose={() => undefined}
        dataSourceManager={buildManager(datasource) as never}
      />,
    );

    const modelInput = await screen.findByRole('textbox', { name: /模型/ });
    await waitFor(() => {
      expect((modelInput as HTMLInputElement).value).toBe('host');
    });

    await user.click(await screen.findByTestId('widget-config-preview-button'));

    // 真实 Drawer 会懒加载 WidgetDataRenderer，冷启动可能超过 waitFor 默认 1 秒。
    await waitFor(() => {
      expect(calls.getSourceDataByApiId).toHaveBeenCalled();
      expect(requestedModel(calls.getSourceDataByApiId.mock.calls[0])).toBe('host');
    }, { timeout: 8000 });

    await user.click(screen.getByText('dashboard.configPreviewRawJson'));
    await waitFor(() => {
      expect(screen.getByTestId('widget-config-preview-json').textContent).toContain('bare-01');
    });
    expect(screen.queryByTestId('widget-config-preview-json-loading')).toBeNull();

    await user.clear(modelInput);
    await user.type(modelInput, 'nic');

    expect(screen.getByTestId('widget-config-preview-stale')).toBeTruthy();
    expect(calls.getSourceDataByApiId).toHaveBeenCalledTimes(1);
    const refresh = screen.getByTestId('widget-config-preview-refresh');
    expect(refresh.hasAttribute('disabled')).toBe(false);

    await user.click(refresh);

    await waitFor(() => {
      expect(calls.getSourceDataByApiId).toHaveBeenCalledTimes(2);
      expect(requestedModel(calls.getSourceDataByApiId.mock.calls[1])).toBe('nic');
    });
    await waitFor(() => {
      expect(screen.getByTestId('widget-config-preview-json').textContent).toContain('nic-01');
    });
    expect(screen.queryByTestId('widget-config-preview-stale')).toBeNull();
    expect(screen.getByTestId('widget-config-preview-refresh').hasAttribute('disabled')).toBe(false);
  }, 20000);
});
