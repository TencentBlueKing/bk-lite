import React, { useState } from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import ViewConfig from '@/app/ops-analysis/components/widgetConfig';
import type { LayoutItem, WidgetConfig } from '@/app/ops-analysis/types/dashBoard';
import type { DatasourceItem, ParamItem } from '@/app/ops-analysis/types/dataSource';
import {
  getDataSourceFormParamInitialValue,
  mergeRestoredParamValue,
  processDataSourceFormParamsForSubmit,
} from '@/app/ops-analysis/utils/dataSourceFormParams';

const getSourceDataByApiId = vi.hoisted(() => vi.fn());

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
    getSourceDataByApiId,
    getDataSourceDetail: vi.fn(),
  }),
}));

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

vi.mock('@/app/cmdb/(pages)/assetManage/management/list/selectIcon', () => ({
  default: () => null,
}));

vi.mock('@/app/ops-analysis/components/widgetDataRenderer', () => ({
  default: ({
    config,
  }: {
    config?: { dataSourceParams?: Array<{ name?: string; value?: unknown }> };
  }) => {
    const mode = config?.dataSourceParams?.find((param) => param.name === 'analysis_mode')?.value;
    return <div data-testid="preview-analysis-mode">{String(mode ?? '')}</div>;
  },
}));

afterEach(() => {
  cleanup();
  getSourceDataByApiId.mockReset();
  getSourceDataByApiId.mockResolvedValue({ data: { items: [] } });
});

const analysisModeParam = (): ParamItem => ({
  name: 'analysis_mode',
  alias_name: '分析方式',
  type: 'string',
  filterType: 'params',
  value: 'detail',
  required: true,
  inputConfig: {
    control: 'select',
    optionsSource: {
      type: 'static',
      staticItems: [
        { label: '明细', value: 'detail' },
        { label: '计数', value: 'count' },
        { label: '分布', value: 'distribution' },
      ],
    },
  },
});

const buildSource = (
  id: number,
  restApi: string,
  params: ParamItem[],
): DatasourceItem => ({
  id,
  name: restApi,
  rest_api: restApi,
  chart_type: ['line', 'bar', 'pie', 'single', 'table', 'topN'],
  field_schema: [{ key: 'model_name', title: '模型', value_type: 'string' }],
  params,
} as DatasourceItem);

const modelSource = buildSource(54, 'cmdb/query_cmdb_models', [analysisModeParam()]);

const instanceSource = buildSource(55, 'cmdb/query_cmdb_instances', [
  analysisModeParam(),
  {
    name: 'model_id',
    alias_name: '模型',
    type: 'string',
    filterType: 'params',
    value: '',
  },
]);

const oneHopSource = buildSource(56, 'cmdb/query_cmdb_one_hop', [
  analysisModeParam(),
  { name: 'start_model_id', alias_name: '起点模型', type: 'string', filterType: 'params', value: '' },
  { name: 'model_asst_id', alias_name: '关联', type: 'string', filterType: 'params', value: '' },
]);

const savedParams = (source: DatasourceItem, values: Record<string, unknown>) =>
  processDataSourceFormParamsForSubmit(values, source.params || []);

const widgetItem = (
  source: DatasourceItem,
  chartType: string,
  params: ParamItem[],
): LayoutItem => ({
  i: `widget-${source.id}`,
  x: 0,
  y: 0,
  w: 6,
  h: 4,
  name: '分析组件',
  description: '',
  valueConfig: {
    dataSource: source.id,
    chartType,
    dataSourceParams: params,
  },
});

const modeOf = (config?: WidgetConfig | null) =>
  config?.dataSourceParams?.find((param) => param.name === 'analysis_mode')?.value;

const analysisModeItem = () => {
  const label = screen.getByTitle('分析方式');
  const item = label.closest('.ant-form-item');
  if (!item) {
    throw new Error('分析方式表单项未挂上');
  }
  return item as HTMLElement;
};

const selectedMode = () =>
  analysisModeItem().querySelector('.ant-select-selection-item')?.textContent ?? '';

const buildManager = (
  source: DatasourceItem,
  selectedDataSource: DatasourceItem | undefined,
  setSelectedDataSource: (next?: DatasourceItem) => void,
) => ({
  selectedDataSource,
  setSelectedDataSource,
  dataSources: [source],
  dataSourcesLoading: false,
  fetchDataSources: vi.fn(),
  loadCanvasDataSources: vi.fn(),
  findDataSource: () => source,
  ensureDataSource: async () => source,
  setDefaultParamValues: (params: ParamItem[], formParams: Record<string, unknown>) => {
    params.forEach((param) => {
      formParams[param.name] = getDataSourceFormParamInitialValue(param);
    });
  },
  restoreUserParamValues: (params: ParamItem[], formParams: Record<string, unknown>) => {
    params.forEach((param) => {
      formParams[param.name] = mergeRestoredParamValue(
        formParams[param.name] as never,
        param,
      );
    });
  },
  processFormParamsForSubmit: processDataSourceFormParamsForSubmit,
});

const AnalysisDrawer = ({
  source,
  initialItem,
  onConfirm,
}: {
  source: DatasourceItem;
  initialItem: LayoutItem;
  onConfirm?: (config: WidgetConfig) => void;
}) => {
  const [open, setOpen] = useState(true);
  const [item, setItem] = useState(initialItem);
  const [selectedDataSource, setSelectedDataSource] = useState<DatasourceItem | undefined>();
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>重新打开</button>
      <ViewConfig
        open={open}
        item={item}
        onClose={() => setOpen(false)}
        onConfirm={(config) => {
          onConfirm?.(config);
          setItem((current) => ({
            ...current,
            name: config.name || current.name,
            valueConfig: {
              ...current.valueConfig,
              dataSource: config.dataSource ?? current.valueConfig?.dataSource,
              chartType: config.chartType,
              dataSourceParams: config.dataSourceParams,
            },
          }));
          setOpen(false);
        }}
        dataSourceManager={buildManager(
          source,
          selectedDataSource,
          setSelectedDataSource,
        ) as never}
      />
    </>
  );
};

const chooseMode = async (label: string) => {
  fireEvent.mouseDown(within(analysisModeItem()).getByRole('combobox'));
  fireEvent.click(await screen.findByText(label, {
    selector: '.ant-select-item-option-content',
  }));
  await waitFor(() => {
    expect(selectedMode()).toBe(label);
  });
};

const switchChart = async (label: string) => {
  const text = screen.getByText(label);
  fireEvent.click(text.closest('label') ?? text);
};

const previewMode = async () => {
  fireEvent.click(screen.getByTestId('widget-config-preview-button'));
  return screen.findByTestId('preview-analysis-mode');
};

describe('ViewConfig analysis mode reopen', () => {
  it('keeps a selected count through preview, save, chart switch, close and reopen', async () => {
    const confirmed: WidgetConfig[] = [];
    render(
      <AnalysisDrawer
        source={modelSource}
        initialItem={widgetItem(modelSource, 'pie', [])}
        onConfirm={(config) => confirmed.push(config)}
      />,
    );

    await waitFor(() => {
      expect(selectedMode()).toBe('明细');
    });
    await chooseMode('计数');
    expect((await previewMode()).textContent).toBe('count');

    fireEvent.click(screen.getByRole('button', { name: 'common.confirm' }));
    await waitFor(() => {
      expect(modeOf(confirmed[0])).toBe('count');
    });
    expect(confirmed[0]?.chartType).toBe('pie');

    fireEvent.click(screen.getByRole('button', { name: '重新打开' }));
    await waitFor(() => {
      expect(selectedMode()).toBe('计数');
    });
    switchChart('dataSource.barChart');
    await waitFor(() => {
      expect(selectedMode()).toBe('计数');
    });
    expect((await previewMode()).textContent).toBe('count');

    fireEvent.click(screen.getByRole('button', { name: 'common.confirm' }));
    await waitFor(() => {
      expect(confirmed).toHaveLength(2);
    });
    expect(modeOf(confirmed[1])).toBe('count');
    expect(confirmed[1]?.chartType).toBe('bar');
  });

  it('reopens a saved distribution without rewriting it when the chart changes', async () => {
    const confirmed: WidgetConfig[] = [];
    render(
      <AnalysisDrawer
        source={modelSource}
        initialItem={widgetItem(
          modelSource,
          'topN',
          savedParams(modelSource, { analysis_mode: 'distribution' }),
        )}
        onConfirm={(config) => confirmed.push(config)}
      />,
    );

    await waitFor(() => {
      expect(selectedMode()).toBe('分布');
    });
    switchChart('dataSource.pieChart');
    await waitFor(() => {
      expect(selectedMode()).toBe('分布');
    });
    fireEvent.click(screen.getByRole('button', { name: 'common.confirm' }));
    await waitFor(() => {
      expect(modeOf(confirmed[0])).toBe('distribution');
    });
    expect(confirmed[0]?.chartType).toBe('pie');
  });

  it('keeps count on a model table that fills columns without a probe request', async () => {
    render(
      <AnalysisDrawer
        source={modelSource}
        initialItem={widgetItem(
          modelSource,
          'table',
          savedParams(modelSource, { analysis_mode: 'count' }),
        )}
      />,
    );

    await waitFor(() => {
      expect(selectedMode()).toBe('计数');
    });
    expect(getSourceDataByApiId).not.toHaveBeenCalled();
  });

  it.each([
    ['instance', instanceSource, { analysis_mode: 'count', model_id: 'host' }],
    ['one-hop', oneHopSource, {
      analysis_mode: 'distribution',
      start_model_id: 'host',
      model_asst_id: 'run',
    }],
  ] as const)(
    'keeps the saved mode when %s table probing is still in flight',
    async (_label, source, values) => {
      let releaseProbe = () => undefined;
      const gate = new Promise<void>((resolve) => {
        releaseProbe = resolve;
      });
      getSourceDataByApiId.mockImplementation(async () => {
        await gate;
        return {
          data: {
            column_fields: {
              source: 'model_attrs',
              model_key: 'host',
              fields: [{ key: 'bk_inst_name', title: '名称' }],
            },
            items: [],
          },
        };
      });
      const expected = values.analysis_mode === 'count' ? '计数' : '分布';
      render(
        <AnalysisDrawer
          source={source}
          initialItem={widgetItem(source, 'table', savedParams(source, values))}
        />,
      );

      await waitFor(() => {
        expect(getSourceDataByApiId).toHaveBeenCalled();
      });
      releaseProbe();
      await waitFor(() => {
        expect(selectedMode()).toBe(expected);
      });
    },
  );
});
