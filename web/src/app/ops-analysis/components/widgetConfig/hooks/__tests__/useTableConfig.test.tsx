import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useTableConfig } from '../useTableConfig';
import type { DisplayColumnRow } from '../../utils/columnProbing';
import { buildWidgetSubmitConfig } from '../../utils/submitConfig';
import { processDataSourceFormParamsForSubmit } from '@/app/ops-analysis/utils/dataSourceFormParams';
import type { ParamItem } from '@/app/ops-analysis/types/dataSource';

const styledColumn: DisplayColumnRow = {
  id: 'status-column',
  key: 'status',
  title: 'status',
  visible: true,
  order: 0,
  cellType: 'colorBackground',
  valueMappings: [
    {
      type: 'value',
      value: 'failed',
      result: { text: '失败', color: '#fd666d' },
    },
  ],
  cellThresholdColors: [{ value: '80', color: '#fd666d' }],
};

const otherColumn: DisplayColumnRow = {
  id: 'host-column',
  key: 'host',
  title: '主机',
  visible: true,
  order: 1,
  cellType: 'text',
  valueMappings: [
    { type: 'value', value: 'node-1', result: { text: '节点 1' } },
  ],
};

const renderTableConfig = () =>
  renderHook(() =>
    useTableConfig({
      form: { getFieldValue: vi.fn() } as never,
      chartType: 'table',
      selectedDataSource: undefined,
      availableFields: [
        { key: 'status', title: '状态' },
        { key: 'host_name', title: '主机名' },
      ] as never,
      getSourceDataByApiId: vi.fn(),
      processFormParamsForSubmit: vi.fn(),
      t: (key) => key,
    }),
  );

describe('useTableConfig column field changes', () => {
  it('clears only the changed column cell style when its key changes', () => {
    const { result } = renderTableConfig();
    act(() => result.current.setDisplayColumns([styledColumn, otherColumn]));

    act(() =>
      result.current.handleDisplayColumnChange(
        styledColumn.id,
        'key',
        'host_name',
      ),
    );

    expect(result.current.displayColumns[0]).toEqual({
      id: 'status-column',
      key: 'host_name',
      title: '主机名',
      visible: true,
      order: 0,
    });
    expect(result.current.displayColumns[1]).toEqual(otherColumn);
  });

  it('keeps cell style when the normalized key does not change', () => {
    const { result } = renderTableConfig();
    act(() => result.current.setDisplayColumns([styledColumn]));

    act(() =>
      result.current.handleDisplayColumnChange(styledColumn.id, 'key', 'status'),
    );

    expect(result.current.displayColumns[0]).toEqual({
      ...styledColumn,
      title: '状态',
    });
  });

  it('does not restore cleared style when the changed column is submitted', () => {
    const { result } = renderTableConfig();
    act(() => result.current.setDisplayColumns([styledColumn]));
    act(() =>
      result.current.handleDisplayColumnChange(
        styledColumn.id,
        'key',
        'host_name',
      ),
    );

    const submitted = buildWidgetSubmitConfig({
      values: { name: '健康矩阵', chartType: 'table' },
      chartType: 'table',
      showChartThemeMode: false,
      showTableFilterFields: false,
      selectedFields: [],
      thresholdColors: [],
      filterBindings: {},
      displayColumns: result.current.displayColumns,
      filterFields: [],
      actions: [],
    });

    expect(submitted.config?.tableConfig?.columns?.[0]).toEqual({
      key: 'host_name',
      title: '主机名',
      visible: true,
      order: 0,
      columnType: undefined,
    });
  });
});

const modelParams = (): ParamItem[] => [
  {
    name: 'analysis_mode',
    alias_name: '分析方式',
    type: 'string',
    filterType: 'params',
    value: 'detail',
    inputConfig: {
      control: 'select',
      optionsSource: {
        type: 'static',
        staticItems: [
          { label: '明细', value: 'detail', charts: ['table'], result: { structure: 'table' } },
          { label: '计数', value: 'count', charts: ['single'], result: { structure: 'value' } },
          { label: '分布', value: 'distribution', charts: ['bar', 'pie', 'topN'], result: { structure: 'category' } },
        ],
      },
    },
  },
  { name: 'page', alias_name: '页码', type: 'number', filterType: 'params', value: null },
  { name: 'page_size', alias_name: '每页', type: 'number', filterType: 'params', value: null },
];

describe('useTableConfig probe requests', () => {
  it('re-probes table columns from the row and does not restore alias fields', async () => {
    const calls: Array<Record<string, unknown>> = [];
    const { result } = renderHook(() =>
      useTableConfig({
        form: { getFieldValue: () => ({ analysis_mode: 'detail', page: 3, page_size: 50 }) } as never,
        chartType: 'bar',
        selectedDataSource: undefined,
        availableFields: [],
        getSourceDataByApiId: vi.fn(async (_id, params) => {
          calls.push(params);
          return { data: { items: [{ classification_name: '计算', model_name: '主机', model_id: 'host', instance_count: 1 }] } };
        }),
        processFormParamsForSubmit: processDataSourceFormParamsForSubmit,
        t: (key) => key,
      }),
    );

    let probed: Array<{ key: string }> = [];
    await act(async () => {
      probed = await result.current.probeDefaultDisplayColumns(
        {
          id: 9,
          params: modelParams(),
          namespaces: [],
          field_schema: [
            { key: 'classification_name', title: '分类' },
            { key: 'name', title: '名称' },
            { key: 'value', title: '值' },
          ],
        } as never,
        { analysis_mode: 'detail', page: 3, page_size: 50 },
        'table',
      );
    });

    expect(calls[0]?.analysis_mode).toBe('detail');
    expect(calls[0]?.page).toBe(3);
    expect(calls[0]?.page_size).toBe(50);
    expect(calls[0]?.top_n).toBeUndefined();
    expect(probed.map((column) => column.key)).toEqual([
      'classification_name',
      'model_name',
      'model_id',
      'instance_count',
    ]);
  });

  it('does not change the saved mode or paging when the probe chart is not a table', async () => {
    const calls: Array<Record<string, unknown>> = [];
    const { result } = renderHook(() =>
      useTableConfig({
        form: { getFieldValue: () => ({}) } as never,
        chartType: 'bar',
        selectedDataSource: undefined,
        availableFields: [],
        getSourceDataByApiId: vi.fn(async (_id, params) => {
          calls.push(params);
          return { data: { items: [] } };
        }),
        processFormParamsForSubmit: processDataSourceFormParamsForSubmit,
        t: (key) => key,
      }),
    );

    await act(async () => {
      await result.current.probeDefaultDisplayColumns(
        { id: 9, params: modelParams(), namespaces: [] } as never,
        { analysis_mode: 'detail', page: 1, page_size: 20 },
        'topN',
      );
    });

    expect(calls[0]?.analysis_mode).toBe('detail');
    expect(calls[0]?.page).toBe(1);
    expect(calls[0]?.page_size).toBe(20);
  });

  it('keeps distribution paging when the probe chart is a bar', async () => {
    const calls: Array<Record<string, unknown>> = [];
    const { result } = renderHook(() =>
      useTableConfig({
        form: { getFieldValue: () => ({}) } as never,
        chartType: 'topN',
        selectedDataSource: undefined,
        availableFields: [],
        getSourceDataByApiId: vi.fn(async (_id, params) => {
          calls.push(params);
          return { data: { items: [] } };
        }),
        processFormParamsForSubmit: processDataSourceFormParamsForSubmit,
        t: (key) => key,
      }),
    );

    await act(async () => {
      await result.current.probeDefaultDisplayColumns(
        { id: 9, params: modelParams(), namespaces: [] } as never,
        { analysis_mode: 'distribution', page: 2, page_size: 20 },
        'bar',
      );
    });

    expect(calls[0]?.analysis_mode).toBe('distribution');
    expect(calls[0]?.page).toBe(2);
    expect(calls[0]?.page_size).toBe(20);
  });

  it('keeps the configured table page instead of forcing page 1', async () => {
    const calls: Array<Record<string, unknown>> = [];
    const { result } = renderHook(() =>
      useTableConfig({
        form: { getFieldValue: () => ({}) } as never,
        chartType: 'table',
        selectedDataSource: undefined,
        availableFields: [],
        getSourceDataByApiId: vi.fn(async (_id, params) => {
          calls.push(params);
          return { data: { items: [] } };
        }),
        processFormParamsForSubmit: processDataSourceFormParamsForSubmit,
        t: (key) => key,
      }),
    );

    await act(async () => {
      await result.current.probeDefaultDisplayColumns(
        { id: 9, params: modelParams(), namespaces: [] } as never,
        { analysis_mode: 'distribution', page: 4, page_size: 50 },
        'table',
      );
    });

    expect(calls[0]?.analysis_mode).toBe('distribution');
    expect(calls[0]?.page).toBe(4);
    expect(calls[0]?.page_size).toBe(50);
  });

  it('still pages a legacy source that has no analysis mode', async () => {
    const legacy: ParamItem[] = [
      { name: 'query', alias_name: '查询', type: 'string', filterType: 'params', value: 'up' },
      { name: 'page', alias_name: '页码', type: 'number', filterType: 'params', value: 2 },
      { name: 'page_size', alias_name: '每页', type: 'number', filterType: 'params', value: 15 },
    ];
    const calls: Array<Record<string, unknown>> = [];
    const { result } = renderHook(() =>
      useTableConfig({
        form: { getFieldValue: () => ({}) } as never,
        chartType: 'table',
        selectedDataSource: undefined,
        availableFields: [],
        getSourceDataByApiId: vi.fn(async (_id, params) => {
          calls.push(params);
          return { data: { items: [{ query: 'up' }] } };
        }),
        processFormParamsForSubmit: processDataSourceFormParamsForSubmit,
        t: (key) => key,
      }),
    );

    await act(async () => {
      await result.current.probeDefaultDisplayColumns(
        { id: 3, params: legacy, namespaces: [] } as never,
        { query: 'up', page: 2, page_size: 15 },
      );
    });

    expect(calls[0]?.page).toBe(2);
    expect(calls[0]?.page_size).toBe(15);
  });
});
