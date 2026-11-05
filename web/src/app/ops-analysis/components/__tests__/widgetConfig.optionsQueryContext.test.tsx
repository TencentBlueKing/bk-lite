import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import ViewConfig from '@/app/ops-analysis/components/widgetConfig';
import type { LayoutItem } from '@/app/ops-analysis/types/dashBoard';
import type { DatasourceItem, InputControlConfig, ParamItem } from '@/app/ops-analysis/types/dataSource';
import type { OptionsQueryEditorContext } from '@/app/ops-analysis/utils/optionsQueryCandidates';

const editorProps = vi.hoisted(() => ({
  current: null as null | {
    open: boolean;
    editingParamName?: string;
    optionsQueryContext?: OptionsQueryEditorContext;
  },
}));

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: () => ({
      matches: false,
      media: '',
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }),
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
    getSourceDataByApiId: vi.fn(async () => ({ data: { items: [] } })),
    getDataSourceDetail: vi.fn(),
  }),
}));

vi.mock('@/app/ops-analysis/components/widgetSelector', () => ({
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
    singleValueTreeData: [],
    loadingSingleValueData: false,
    fetchSingleValueDataFields: vi.fn(),
    handleSingleValueFieldChange: vi.fn(),
    handleThresholdChange: vi.fn(),
    handleThresholdBlur: vi.fn(),
    addThreshold: vi.fn(),
    removeThreshold: vi.fn(),
    compareAvailable: false,
  }),
}));

vi.mock('@/app/ops-analysis/components/widgetConfig/hooks/useTableConfig', () => ({
  useTableConfig: () => ({
    displayColumns: [],
    filterFields: [],
    detectedDisplayColumns: [],
    displayColumnsError: '',
    paramsChangedAfterProbe: false,
    setDisplayColumns: vi.fn(),
    setFilterFields: vi.fn(),
    setDetectedDisplayColumns: vi.fn(),
    setDisplayColumnsError: vi.fn(),
    setParamsChangedAfterProbe: vi.fn(),
    resetTableConfig: vi.fn(),
    handleChartTypeChange: vi.fn(),
    probeDefaultDisplayColumns: vi.fn(async () => []),
    createDefaultFilterField: vi.fn(),
    createDefaultDisplayColumn: vi.fn(),
    createDefaultOperationColumn: vi.fn(),
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
  }),
}));

vi.mock('@/app/ops-analysis/components/paramInputConfigEditor', () => ({
  ParamInputConfigEditor: (props: {
    open: boolean;
    editingParamName?: string;
    optionsQueryContext?: OptionsQueryEditorContext;
  }) => {
    editorProps.current = props;
    return props.open ? <div data-testid="param-input-config-editor" /> : null;
  },
}));

afterEach(() => {
  cleanup();
  editorProps.current = null;
});

const zoneOverrideConfig: InputControlConfig = {
  control: 'select',
  optionsSource: {
    type: 'dynamic',
    sourceId: 11,
    valueField: 'id',
    labelField: 'name',
    queryParams: { region_id: { ref: 'cloud_region_ids' } },
  },
};

const regionParam: ParamItem = {
  name: 'cloud_region_ids',
  alias_name: '地域',
  type: 'string',
  filterType: 'params',
  value: null,
};

const zoneParam: ParamItem = {
  name: 'zone_id',
  alias_name: '可用区',
  type: 'string',
  filterType: 'params',
  value: null,
  inputConfig: {
    control: 'select',
    optionsSource: {
      type: 'static',
      staticItems: [{ label: '原始', value: 'source-zone' }],
    },
  },
};

const dataSource = {
  id: 101,
  name: 'region source',
  source_type: 'nats',
  rest_api: 'cmdb/zones',
  chart_type: ['single'],
  field_schema: [],
  namespaces: [],
  params: [regionParam, zoneParam],
  created_at: '',
  updated_at: '',
  created_by: '',
  updated_by: '',
  domain: '',
  updated_by_domain: '',
  desc: '',
} as DatasourceItem;

const zoneOverride: ParamItem = {
  name: 'zone_id',
  alias_name: '可用区覆盖',
  type: 'number',
  filterType: 'fixed',
  value: 'override-value',
  inputConfig: zoneOverrideConfig,
};

const item: LayoutItem = {
  i: 'widget-1',
  x: 0,
  y: 0,
  w: 4,
  h: 4,
  name: 'region-widget',
  description: '',
  valueConfig: {
    chartType: 'single',
    dataSource: 101,
    dataSourceParams: [zoneOverride],
  },
};

const manager = {
  selectedDataSource: dataSource,
  setSelectedDataSource: vi.fn(),
  ensureDataSource: vi.fn(async () => dataSource),
  setDefaultParamValues: (params: ParamItem[], formParams: Record<string, unknown>) => {
    params.forEach((param) => {
      formParams[param.name] = param.value ?? null;
    });
  },
  restoreUserParamValues: (dataSourceParams: ParamItem[], formParams: Record<string, unknown>) => {
    dataSourceParams.forEach((param) => {
      formParams[param.name] = param.value ?? null;
    });
  },
  processFormParamsForSubmit: (formParams: Record<string, unknown>, sourceParams: ParamItem[]) =>
    sourceParams.map((param) => ({
      ...param,
      value: Object.prototype.hasOwnProperty.call(formParams, param.name)
        ? formParams[param.name] as ParamItem['value']
        : param.value,
    })),
  dataSources: [dataSource],
  dataSourcesLoading: false,
  fetchDataSources: vi.fn(),
  loadCanvasDataSources: vi.fn(),
  findDataSource: () => dataSource,
};

const openEditorFromLabel = async (label: string) => {
  await waitFor(() => {
    expect(screen.getByText(label)).toBeTruthy();
  });
  const labelNode = screen.getByText(label);
  const labelContainer = labelNode.closest('.ant-form-item-label') || labelNode.parentElement?.parentElement;
  const gearButton = within(labelContainer as HTMLElement).getByRole('button');
  fireEvent.click(gearButton);
};

describe('ViewConfig options query context', () => {
  it('keeps every component param when an inputConfig override exists', async () => {
    render(
      <ViewConfig
        open
        item={item}
        onClose={() => undefined}
        onConfirm={() => undefined}
        dataSourceManager={manager as never}
      />,
    );

    await openEditorFromLabel('可用区');

    const params = editorProps.current?.optionsQueryContext?.componentParams ?? [];
    expect(editorProps.current?.open).toBe(true);
    expect(editorProps.current?.editingParamName).toBe('zone_id');
    expect(params.map((param) => param.name)).toEqual(['cloud_region_ids', 'zone_id']);
    expect(params.find((param) => param.name === 'cloud_region_ids')).toMatchObject({
      label: '地域',
      type: 'string',
      filterType: 'params',
    });
    expect(params.find((param) => param.name === 'zone_id')).toMatchObject({
      label: '可用区',
      type: 'string',
      filterType: 'params',
      queryParams: { region_id: { ref: 'cloud_region_ids' } },
      inputConfig: zoneOverrideConfig,
    });
  });
});
