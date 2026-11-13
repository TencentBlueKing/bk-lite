import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { Form } from 'antd';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import DataSourceParamsConfig from '@/app/ops-analysis/components/paramsConfig';
import type { DatasourceItem, ParamItem } from '@/app/ops-analysis/types/dataSource';
import { reconcileComponentParamValue } from '@/app/ops-analysis/utils/componentParamSwitch';

const api = vi.hoisted(() => ({
  getDataSourceList: vi.fn(async () => [
    { id: 3, rest_api: 'cmdb/list_cmdb_attr_options', name: '属性' },
    { id: 4, rest_api: 'cmdb/get_model_association_options', name: '关系' },
  ]),
  getSourceDataByApiId: vi.fn(),
}));

vi.mock('@/app/ops-analysis/api/dataSource', () => ({
  // 真实 hook 每次渲染都返回新对象。稳定引用会藏住属性加载的重复请求。
  useDataSourceApi: () => ({
    getDataSourceList: api.getDataSourceList,
    getSourceDataByApiId: api.getSourceDataByApiId,
  }),
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      if (key === 'dashboard.selectClassificationFirst') return '请先选择分类';
      return key;
    },
  }),
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

afterEach(() => {
  cleanup();
  api.getSourceDataByApiId.mockReset();
});

const classification = (name = 'classification_id'): ParamItem => ({
  name,
  alias_name: '模型分类',
  type: 'string',
  filterType: 'params',
  value: '',
  inputConfig: {
    control: 'select',
    optionsSource: {
      type: 'dynamic',
      sourceId: 1,
      valueField: 'classification_id',
      labelField: 'classification_name',
    },
  },
});

const modelSelect = (name: string, alias: string): ParamItem => ({
  name,
  alias_name: alias,
  type: 'string',
  filterType: 'params',
  value: '',
  required: true,
  inputConfig: {
    control: 'select',
    optionsSource: {
      type: 'dynamic',
      sourceId: 2,
      valueField: 'model_id',
      labelField: 'model_name',
      queryParams: { classification_id: { ref: 'classification_id' } },
      emptyUpstreamHintKey: 'dashboard.selectClassificationFirst',
    },
  },
});

const analysisMode = (): ParamItem => ({
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
        { label: '明细', value: 'detail', charts: ['table'], result: { structure: 'table' } },
      ],
    },
  },
});

const QueryForm = ({
  source,
  initialParams,
}: {
  source: DatasourceItem;
  initialParams: Record<string, unknown>;
}) => {
  const [form] = Form.useForm();
  return (
    <Form form={form} initialValues={{ chartType: 'table', params: initialParams }}>
      <DataSourceParamsConfig
        selectedDataSource={source}
        includeFilterTypes={['params', 'fixed']}
        globalFilters={[]}
        onParamOptionsResolved={(param, options) => {
          const current = form.getFieldValue(['params', param.name]);
          const next = reconcileComponentParamValue(current, options);
          if (next !== current) form.setFieldValue(['params', param.name], next);
        }}
      />
      <Form.Item shouldUpdate noStyle>
        {() => (
          <pre data-testid="form-params">{JSON.stringify(form.getFieldsValue(true)?.params ?? {})}</pre>
        )}
      </Form.Item>
    </Form>
  );
};

const readParams = () => JSON.parse(screen.getByTestId('form-params').textContent || '{}') as Record<string, unknown>;

const openSelect = (index: number) => {
  const select = screen.getAllByRole('combobox')[index];
  fireEvent.mouseDown(select);
};

describe('cmdb classification cascade', () => {
  it('blocks the model request until a classification is chosen', async () => {
    api.getSourceDataByApiId.mockImplementation(async (id: number) => {
      if (id === 1) {
        return { data: [{ classification_id: 'compute', classification_name: '计算' }], warnings: [] };
      }
      return { data: [{ model_id: 'host', model_name: '主机' }], warnings: [] };
    });
    render(
      <QueryForm
        source={{
          id: 21,
          name: 'CMDB 实例通用查询',
          params: [classification(), modelSelect('model_id', '模型'), analysisMode()],
        } as DatasourceItem}
        initialParams={{ classification_id: null, model_id: 'host', analysis_mode: 'detail' }}
      />,
    );

    expect(await screen.findByText('请先选择分类')).toBeTruthy();
    await waitFor(() => {
      expect(readParams().model_id).toBeNull();
    });
    expect(api.getSourceDataByApiId.mock.calls.some(([id]) => id === 2)).toBe(false);
  });

  it('lists models in the classification and clears attrs, conditions and sort when it changes', async () => {
    api.getSourceDataByApiId.mockImplementation(async (id: number, params?: { classification_id?: string; model_id?: string }) => {
      if (id === 1) {
        return {
          data: [
            { classification_id: 'compute', classification_name: '计算' },
            { classification_id: 'space', classification_name: '空间' },
          ],
          warnings: [],
        };
      }
      if (id === 2) {
        const rows = params?.classification_id === 'compute'
          ? [{ model_id: 'host', model_name: '主机' }]
          : [{ model_id: 'room', model_name: '机房' }];
        return { data: rows, warnings: [] };
      }
      if (params?.model_id === 'host') {
        return { data: [{ attr_id: 'cpu', attr_name: 'CPU', value_type: 'number', options: [] }], warnings: [] };
      }
      return { data: [], warnings: [] };
    });
    render(
      <QueryForm
        source={{
          id: 22,
          name: 'CMDB 实例通用查询',
          params: [
            classification(),
            modelSelect('model_id', '模型'),
            analysisMode(),
            {
              name: 'filters',
              alias_name: '条件过滤',
              type: 'conditionFilter',
              filterType: 'params',
              value: { logic: 'AND', items: [] },
              inputConfig: {
                control: 'conditionFilter',
                fields: { kind: 'modelAttrs', modelParam: 'model_id' },
              },
            },
            {
              name: 'order',
              alias_name: '排序',
              type: 'order',
              filterType: 'params',
              value: '',
              visible_modes: ['detail'],
              inputConfig: {
                control: 'order',
                modelParam: 'model_id',
                includeModelAttrsInModes: ['detail'],
                fields: [{ value: 'inst_name', label: '实例名', modes: ['detail'] }],
              },
            },
          ],
        } as DatasourceItem}
        initialParams={{
          classification_id: 'compute',
          model_id: 'host',
          analysis_mode: 'detail',
          filters: { logic: 'AND', items: [{ field: 'cpu', op: 'gt', value: 2 }] },
          order: '-cpu',
        }}
      />,
    );

    await waitFor(() => {
      expect(api.getSourceDataByApiId).toHaveBeenCalledWith(2, { classification_id: 'compute' }, undefined);
      expect(readParams().model_id).toBe('host');
      expect(readParams().order).toBe('-cpu');
      expect((readParams().filters as { items: unknown[] }).items).toHaveLength(1);
    });

    openSelect(0);
    fireEvent.click(await screen.findByText('空间'));
    await waitFor(() => {
      const next = readParams();
      expect(next.classification_id).toBe('space');
      expect(next.model_id).toBeNull();
      expect(next.order).toBe('');
      expect((next.filters as { items: unknown[] }).items).toEqual([]);
    });
    expect(api.getSourceDataByApiId).toHaveBeenCalledWith(2, { classification_id: 'space' }, undefined);
  });

  it('loads associations from the start model and clears them with the classification', async () => {
    api.getSourceDataByApiId.mockImplementation(async (id: number, params?: { classification_id?: string; model_id?: string }) => {
      if (id === 1) {
        return {
          data: [
            { classification_id: 'compute', classification_name: '计算' },
            { classification_id: 'space', classification_name: '空间' },
          ],
          warnings: [],
        };
      }
      if (id === 2) {
        return {
          data: params?.classification_id === 'space'
            ? [{ model_id: 'room', model_name: '机房' }]
            : [{ model_id: 'host', model_name: '主机' }],
          warnings: [],
        };
      }
      if (id === 4) {
        return {
          data: [{
            model_asst_id: 'host_belong_app',
            label: '属于应用',
            src_model_id: 'host',
            dst_model_id: 'app',
          }],
          warnings: [],
        };
      }
      if (params?.model_id === 'app') {
        return { data: [{ attr_id: 'port', attr_name: '端口', value_type: 'string', options: [] }], warnings: [] };
      }
      if (params?.model_id === 'host') {
        return { data: [{ attr_id: 'cpu', attr_name: 'CPU', value_type: 'number', options: [] }], warnings: [] };
      }
      return { data: [], warnings: [] };
    });
    render(
      <QueryForm
        source={{
          id: 23,
          name: 'CMDB 一跳关联通用查询',
          params: [
            classification(),
            modelSelect('start_model_id', '起点模型'),
            {
              name: 'model_asst_id',
              alias_name: '关系',
              type: 'string',
              filterType: 'params',
              value: '',
              required: true,
              inputConfig: {
                control: 'select',
                optionsSource: {
                  type: 'dynamic',
                  sourceId: 4,
                  valueField: 'model_asst_id',
                  labelField: 'label',
                  queryParams: { model_id: { ref: 'start_model_id' } },
                },
              },
            },
            analysisMode(),
            {
              name: 'filters',
              alias_name: '起点条件',
              type: 'conditionFilter',
              filterType: 'params',
              value: { logic: 'AND', items: [] },
              inputConfig: {
                control: 'conditionFilter',
                fields: { kind: 'modelAttrs', modelParam: 'start_model_id' },
              },
            },
            {
              name: 'end_filters',
              alias_name: '终点条件',
              type: 'conditionFilter',
              filterType: 'params',
              value: { logic: 'AND', items: [] },
              inputConfig: {
                control: 'conditionFilter',
                fields: {
                  kind: 'endModelAttrs',
                  startModelParam: 'start_model_id',
                  associationParam: 'model_asst_id',
                },
              },
            },
          ],
        } as DatasourceItem}
        initialParams={{
          classification_id: 'compute',
          start_model_id: 'host',
          model_asst_id: 'host_belong_app',
          direction: 'out',
          analysis_mode: 'detail',
          filters: { logic: 'AND', items: [{ field: 'cpu', op: 'gt', value: 1 }] },
          end_filters: { logic: 'AND', items: [{ field: 'port', op: 'eq', value: '80' }] },
        }}
      />,
    );

    await waitFor(() => {
      expect(api.getSourceDataByApiId).toHaveBeenCalledWith(4, { model_id: 'host' }, undefined);
      expect(readParams().model_asst_id).toBe('host_belong_app');
      expect((readParams().end_filters as { items: unknown[] }).items).toHaveLength(1);
    });

    openSelect(0);
    fireEvent.click(await screen.findByText('空间'));
    await waitFor(() => {
      const next = readParams();
      expect(next.start_model_id).toBeNull();
      expect(next.model_asst_id).toBeNull();
      expect((next.filters as { items: unknown[] }).items).toEqual([]);
      expect((next.end_filters as { items: unknown[] }).items).toEqual([]);
    });
  });

  const attrCallsFor = (modelId: string) => api.getSourceDataByApiId.mock.calls.filter(
    ([id, params]) => id === 3 && (params as { model_id?: string } | undefined)?.model_id === modelId,
  ).length;

  const expectAttrLoadsToSettle = async (modelId: string, count: number) => {
    await waitFor(() => {
      expect(attrCallsFor(modelId)).toBe(count);
    });
    const settled = attrCallsFor(modelId);
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 30));
    });
    expect(attrCallsFor(modelId)).toBe(settled);
  };

  it('loads model attributes once for the condition filter and the sort control', async () => {
    api.getSourceDataByApiId.mockResolvedValue({
      data: [{ attr_id: 'cpu', attr_name: 'CPU', value_type: 'number', options: [] }],
      warnings: [],
    });
    render(
      <QueryForm
        source={{
          id: 24,
          name: 'CMDB 实例通用查询',
          params: [
            analysisMode(),
            {
              name: 'filters',
              alias_name: '条件过滤',
              type: 'conditionFilter',
              filterType: 'params',
              value: { logic: 'AND', items: [] },
              inputConfig: {
                control: 'conditionFilter',
                fields: { kind: 'modelAttrs', modelParam: 'model_id' },
              },
            },
            {
              name: 'order',
              alias_name: '排序',
              type: 'order',
              filterType: 'params',
              value: '',
              inputConfig: {
                control: 'order',
                modelParam: 'model_id',
                includeModelAttrsInModes: ['detail'],
                fields: [{ value: 'inst_name', label: '实例名', modes: ['detail'] }],
              },
            },
          ],
        } as DatasourceItem}
        initialParams={{
          model_id: 'host',
          analysis_mode: 'detail',
          filters: { logic: 'AND', items: [] },
          order: '',
        }}
      />,
    );

    await expectAttrLoadsToSettle('host', 2);
  });

  it('loads start-model attributes once for the one-hop condition filter', async () => {
    api.getSourceDataByApiId.mockResolvedValue({
      data: [{ attr_id: 'cpu', attr_name: 'CPU', value_type: 'number', options: [] }],
      warnings: [],
    });
    render(
      <QueryForm
        source={{
          id: 25,
          name: 'CMDB 一跳关联通用查询',
          params: [
            {
              name: 'filters',
              alias_name: '起点条件',
              type: 'conditionFilter',
              filterType: 'params',
              value: { logic: 'AND', items: [] },
              inputConfig: {
                control: 'conditionFilter',
                fields: { kind: 'modelAttrs', modelParam: 'start_model_id' },
              },
            },
          ],
        } as DatasourceItem}
        initialParams={{
          start_model_id: 'host',
          filters: { logic: 'AND', items: [] },
        }}
      />,
    );

    await expectAttrLoadsToSettle('host', 1);
  });

  it('keeps a saved enum condition while the model attribute list is loading', async () => {
    let resolveAttrs: ((value: unknown) => void) | undefined;
    api.getSourceDataByApiId.mockImplementation(
      () => new Promise((resolve) => {
        resolveAttrs = resolve;
      }),
    );
    const forms: Array<ReturnType<typeof Form.useForm>[0]> = [];
    const Harness = () => {
      const [form] = Form.useForm();
      forms[0] = form;
      return (
        <Form form={form} initialValues={{ chartType: 'table', params: { model_id: '', filters: { logic: 'AND', items: [] } } }}>
          <DataSourceParamsConfig
            selectedDataSource={{
              id: 26,
              name: 'CMDB 实例通用查询',
              params: [{
                name: 'filters',
                alias_name: '条件过滤',
                type: 'conditionFilter',
                filterType: 'params',
                value: { logic: 'AND', items: [] },
                inputConfig: {
                  control: 'conditionFilter',
                  fields: { kind: 'modelAttrs', modelParam: 'model_id' },
                },
              }],
            } as DatasourceItem}
            includeFilterTypes={['params', 'fixed']}
            globalFilters={[]}
            filterBindings={{}}
            globalFilterValues={{}}
          />
          <Form.Item shouldUpdate noStyle>
            {() => (
              <pre data-testid="form-params">{JSON.stringify(form.getFieldsValue(true)?.params ?? {})}</pre>
            )}
          </Form.Item>
        </Form>
      );
    };
    render(<Harness />);
    await act(async () => {
      await Promise.resolve();
    });
    await act(async () => {
      forms[0].setFieldsValue({
        params: {
          model_id: 'system',
          filters: { logic: 'AND', items: [{ field: 'status', op: 'eq', value: '1' }] },
        },
      });
    });
    const savedItems = () => (
      readParams().filters as { items: Array<{ field?: string; op?: string; value?: string }> }
    ).items;
    expect(savedItems()).toEqual([{ field: 'status', op: 'eq', value: '1' }]);
    await act(async () => {
      await Promise.resolve();
    });
    expect(savedItems()).toEqual([{ field: 'status', op: 'eq', value: '1' }]);

    resolveAttrs?.({
      data: [{
        attr_id: 'status',
        attr_name: '运行状态',
        value_type: 'enum',
        options: [
          { label: '已上线', value: '1' },
          { label: '测试中', value: '2' },
        ],
      }],
      warnings: [],
    });
    await waitFor(() => {
      expect(savedItems()).toEqual([{ field: 'status', op: 'eq', value: '1' }]);
    });
    expect(screen.getByText('已上线')).toBeTruthy();
  });
});
