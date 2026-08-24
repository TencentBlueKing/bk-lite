import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import ViewConfig from '@/app/ops-analysis/components/widgetConfig';
import type { LayoutItem } from '@/app/ops-analysis/types/dashBoard';
import type { DatasourceItem, InputControlConfig, ParamItem } from '@/app/ops-analysis/types/dataSource';
import {
  migrateParamItemsFromStringList,
  normalizeDatasourceItemParams,
} from '@/app/ops-analysis/utils/stringParamMultipleMigrate';

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
  ParamInputConfigEditor: ({
    open,
    value,
    onConfirm,
  }: {
    open: boolean;
    value?: InputControlConfig;
    onConfirm: (value: InputControlConfig) => void;
  }) => open ? (
    <div data-testid="param-input-config-editor">
      <pre data-testid="param-input-config-value">{JSON.stringify(value)}</pre>
      <button
        type="button"
        data-testid="param-input-config-confirm"
        onClick={() => value && onConfirm(value)}
      >
        confirm-editor
      </button>
    </div>
  ) : null,
}));

afterEach(() => {
  cleanup();
});

const buildLegacyDataSource = (
  param: ParamItem,
): DatasourceItem => ({
  id: 101,
  name: 'Legacy Host Source',
  source_type: 'nats',
  rest_api: 'monitor/query',
  chart_type: ['single'],
  field_schema: [],
  namespaces: [],
  params: [param],
  created_at: '',
  updated_at: '',
  created_by: '',
  updated_by: '',
  domain: '',
  updated_by_domain: '',
  desc: '',
} as DatasourceItem);

const buildItem = (dataSourceParams?: ParamItem[]): LayoutItem => ({
  i: 'widget-1',
  x: 0,
  y: 0,
  w: 4,
  h: 4,
  name: 'legacy-widget',
  description: '',
  valueConfig: {
    chartType: 'single',
    dataSource: 101,
    dataSourceParams: dataSourceParams || [],
  },
});

const buildManager = (dataSource: DatasourceItem) => ({
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
});

const expectSelectInputConfig = (value?: InputControlConfig) => {
  expect(value?.control).toBe('select');
  if (!value || value.control !== 'select') {
    throw new Error('expected select input config');
  }
  return value;
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

describe('ViewConfig legacy stringList param normalization', () => {
  it('shows gear for legacy datasource params and saves canonical string params', async () => {
    const dataSource = buildLegacyDataSource({
      name: 'instance_ids',
      alias_name: '主机',
      type: 'stringList',
      filterType: 'params',
      value: ['host-a'],
      inputConfig: {
        control: 'select',
        multiple: true,
        optionsSource: { type: 'static', staticItems: [{ label: 'A', value: 'host-a' }] },
      },
    });
    render(
      <ViewConfig
        open
        item={buildItem()}
        onClose={() => undefined}
        onConfirm={() => undefined}
        dataSourceManager={buildManager(dataSource) as never}
      />,
    );

    await openEditorFromLabel('主机');
    expect(screen.getByTestId('param-input-config-value').textContent).toContain('"control":"select"');
    expect(screen.getByTestId('param-input-config-value').textContent).toContain('"multiple":true');
    const canonicalParams = normalizeDatasourceItemParams(dataSource).params;
    expect(canonicalParams[0].type).toBe('string');
    expect(canonicalParams[0].filterType).toBe('params');
    expect(expectSelectInputConfig(canonicalParams[0].inputConfig).multiple).toBe(true);
  });

  it('normalizes legacy datasource and legacy widget override together without duplicates', async () => {
    const dataSource = buildLegacyDataSource({
      name: 'instance_ids',
      alias_name: '主机',
      type: 'stringList',
      filterType: 'params',
      value: ['host-a'],
      inputConfig: {
        control: 'select',
        multiple: true,
        picker: 'table',
        optionsSource: {
          type: 'dynamic',
          sourceRef: { type: 'rest_api', value: 'monitor/get_host_instance_list' },
          valueField: 'instance_id',
          labelField: 'display_name',
        },
      },
    });
    const legacyOverride: ParamItem = {
      name: 'instance_ids',
      alias_name: '主机',
      type: 'stringList',
      filterType: 'params',
      value: ['host-a'],
      inputConfig: {
        control: 'select',
        multiple: true,
        picker: 'table',
        optionsSource: {
          type: 'dynamic',
          sourceRef: { type: 'rest_api', value: 'monitor/get_host_instance_list' },
          valueField: 'instance_id',
          labelField: 'display_name',
        },
      },
    };
    render(
      <ViewConfig
        open
        item={buildItem([legacyOverride])}
        onClose={() => undefined}
        onConfirm={() => undefined}
        dataSourceManager={buildManager(dataSource) as never}
      />,
    );

    await openEditorFromLabel('主机');
    const editorValue = screen.getByTestId('param-input-config-value').textContent || '';
    expect(editorValue).toContain('"picker":"table"');
    expect(editorValue).toContain('"sourceRef":{"type":"rest_api","value":"monitor/get_host_instance_list"}');

    const normalizedSourceParams = normalizeDatasourceItemParams(dataSource).params;
    const normalizedOverrideParams = migrateParamItemsFromStringList([legacyOverride]).params;
    expect(normalizedSourceParams).toHaveLength(1);
    expect(normalizedOverrideParams).toHaveLength(1);
    expect(normalizedSourceParams[0].type).toBe('string');
    expect(normalizedOverrideParams[0].type).toBe('string');
    const normalizedOverrideInputConfig = expectSelectInputConfig(
      normalizedOverrideParams[0].inputConfig,
    );
    expect(normalizedOverrideInputConfig.picker).toBe('table');
    expect(
      normalizedOverrideInputConfig.optionsSource.type === 'dynamic'
        ? normalizedOverrideInputConfig.optionsSource.sourceRef?.value
        : undefined,
    ).toBe(
      'monitor/get_host_instance_list',
    );
  });

  it('normalizes legacy options-only params into editable select config', async () => {
    const dataSource = buildLegacyDataSource({
      name: 'instance_ids',
      alias_name: '主机',
      type: 'stringList',
      filterType: 'params',
      value: ['host-a'],
      options: [
        { label: 'Host A', value: 'host-a' },
        { label: 'Host B', value: 'host-b' },
      ],
    });

    render(
      <ViewConfig
        open
        item={buildItem()}
        onClose={() => undefined}
        onConfirm={() => undefined}
        dataSourceManager={buildManager(dataSource) as never}
      />,
    );

    await openEditorFromLabel('主机');
    const editorValue = screen.getByTestId('param-input-config-value').textContent || '';
    expect(editorValue).toContain('"control":"select"');
    expect(editorValue).toContain('"multiple":true');
    expect(editorValue).toContain('"staticItems":[{"label":"Host A","value":"host-a"},{"label":"Host B","value":"host-b"}]');
  });
});
