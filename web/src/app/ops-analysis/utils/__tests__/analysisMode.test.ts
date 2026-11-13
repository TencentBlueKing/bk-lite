import assert from 'node:assert/strict';
import { describe, it } from 'vitest';
import type { ParamItem } from '@/app/ops-analysis/types/dataSource';
import {
  filterChartTypesForAnalysisMode,
  resolveAnalysisModeValue,
} from '@/app/ops-analysis/utils/analysisMode';
import { mergeDetectedFieldsWithSchema } from '@/app/ops-analysis/components/widgetConfig/utils/columnProbing';
import { resolveTableLikeColumns } from '@/app/ops-analysis/utils/tableLikeData';
import { buildCompareRequestParams } from '@/app/ops-analysis/utils/compareQuery';
import {
  buildWidgetRequestParams,
  fetchWidgetData,
  processDataSourceParams,
} from '@/app/ops-analysis/utils/widgetDataTransform';

const modeParam = (items: Array<{
  label: string;
  value: string;
  charts: string[];
  result: { structure: 'table' | 'value' | 'category' | 'series' };
}>): ParamItem => ({
  name: 'analysis_mode',
  alias_name: '分析方式',
  type: 'string',
  filterType: 'params',
  value: 'detail',
  inputConfig: {
    control: 'select',
    optionsSource: { type: 'static', staticItems: items },
  },
});

const catalog = (): ParamItem[] => [
  modeParam([
    { label: '明细', value: 'detail', charts: ['table', 'topN'], result: { structure: 'table' } },
    { label: '计数', value: 'count', charts: ['single'], result: { structure: 'value' } },
    { label: '分布', value: 'distribution', charts: ['bar', 'pie'], result: { structure: 'category' } },
  ]),
  { name: 'model_id', alias_name: '模型', type: 'string', filterType: 'params', value: 'host' },
  { name: 'group_by', alias_name: '分组', type: 'string', filterType: 'params', value: 'os_type', visible_modes: ['distribution'] },
  { name: 'page', alias_name: '页码', type: 'number', filterType: 'params', value: null, visible_modes: ['detail'] },
  { name: 'page_size', alias_name: '每页', type: 'number', filterType: 'params', value: null, visible_modes: ['detail'] },
  {
    name: 'organization',
    alias_name: '组织',
    type: 'string',
    filterType: 'filter',
    value: '',
    inputConfig: { control: 'organization' },
  },
];

describe('analysis mode visibility and request', () => {
  it('keeps every configured param on the request for every chart', () => {
    const params = catalog();
    for (const chartType of ['table', 'single', 'pie', 'bar', 'topN']) {
      const request = processDataSourceParams({
        sourceParams: params,
        definitionParams: params,
        userParams: {
          analysis_mode: 'count',
          model_id: 'host',
          group_by: 'os_type',
          page: 2,
          page_size: 10,
        },
        chartType,
      });
      assert.equal(request.analysis_mode, 'count', chartType);
      assert.equal(request.group_by, 'os_type', chartType);
      assert.equal(request.page, 2, chartType);
      assert.equal(request.page_size, 10, chartType);
    }
  });

  it('filters charts from the latest catalog options, not a stale widget copy', () => {
    const latest = catalog();
    const stale = catalog();
    const staleMode = stale[0];
    if (staleMode.inputConfig && staleMode.inputConfig.control === 'select') {
      staleMode.inputConfig = {
        control: 'select',
        optionsSource: {
          type: 'static',
          staticItems: [{ label: '旧明细', value: 'detail' }],
        },
      };
    }
    stale[2] = { ...stale[2], visible_modes: ['detail'] };
    const charts = filterChartTypesForAnalysisMode(
      [{ value: 'table' }, { value: 'single' }, { value: 'bar' }, { value: 'pie' }],
      latest,
      'distribution',
    );
    assert.deepEqual(charts.map((item) => item.value), ['table', 'single', 'bar', 'pie']);
    assert.deepEqual(
      filterChartTypesForAnalysisMode(
        [{ value: 'table' }, { value: 'line' }],
        stale,
        'detail',
      ).map((item) => item.value),
      ['table', 'line'],
    );
  });

  it('keeps the selected mode and configured params when the widget copy is stale', () => {
    const latest = catalog();
    const stale = catalog();
    stale[2] = { ...stale[2], visible_modes: undefined };
    const request = processDataSourceParams({
      sourceParams: stale,
      definitionParams: latest,
      userParams: {
        analysis_mode: 'count',
        model_id: 'host',
        group_by: 'os_type',
        page: 1,
        page_size: 20,
      },
      chartType: 'single',
    });
    assert.equal(request.analysis_mode, 'count');
    assert.equal(request.model_id, 'host');
    assert.equal(request.group_by, 'os_type');
    assert.equal(request.page, 1);
    assert.equal(request.page_size, 20);
  });

  it('keeps the selected mode when the chart changes', () => {
    const params = catalog();
    assert.equal(resolveAnalysisModeValue({
      params,
      selected: 'detail',
      chartType: 'pie',
    }), 'detail');
    assert.equal(resolveAnalysisModeValue({
      params,
      selected: 'count',
      chartType: 'single',
    }), 'count');
  });

  it('uses the configured default when the widget has no selection', () => {
    const params = catalog();
    assert.equal(resolveAnalysisModeValue({
      params,
      selected: '',
      chartType: 'pie',
    }), 'detail');
    const request = processDataSourceParams({
      sourceParams: params.map((param) => (
        param.name === 'analysis_mode' ? { ...param, value: '' } : param
      )),
      definitionParams: params,
      chartType: 'pie',
    });
    assert.equal(request.analysis_mode, 'detail');
    assert.equal(request.group_by, 'os_type');
    assert.equal(request.page, undefined);
  });

  it('omits a cleared number instead of putting the seed default back', () => {
    const params = catalog().map((param) => {
      if (param.name === 'page') return { ...param, value: 1 };
      if (param.name === 'page_size') return { ...param, value: 20 };
      return param;
    });
    const detail = processDataSourceParams({
      sourceParams: params,
      definitionParams: params,
      chartType: 'table',
    });
    assert.equal(detail.page, 1);
    assert.equal(detail.page_size, 20);
    const cleared = processDataSourceParams({
      sourceParams: params,
      definitionParams: params,
      userParams: { analysis_mode: 'count', page: null, page_size: null },
      chartType: 'single',
    });
    assert.equal(cleared.analysis_mode, 'count');
    assert.equal(cleared.page, undefined);
    assert.equal(cleared.page_size, undefined);
    const counted = processDataSourceParams({
      sourceParams: params,
      definitionParams: params,
      userParams: { analysis_mode: 'count', page: 1, page_size: 20 },
      chartType: 'pie',
    });
    assert.equal(counted.page, 1);
    assert.equal(counted.page_size, 20);
  });

  it('leaves a datasource without analysis_mode unchanged', () => {
    const params: ParamItem[] = [
      { name: 'query', alias_name: '查询', type: 'string', filterType: 'params', value: 'up' },
      { name: 'step', alias_name: '步长', type: 'string', filterType: 'params', value: '5m' },
    ];
    assert.equal(resolveAnalysisModeValue({ params, selected: undefined, chartType: 'line' }), undefined);
    assert.deepEqual(processDataSourceParams({ sourceParams: params, chartType: 'bar' }), {
      query: 'up',
      step: '5m',
    });
    const legacyPaging = processDataSourceParams({
      sourceParams: [
        ...params,
        { name: 'page', alias_name: '页码', type: 'number', filterType: 'params', value: 2 },
        { name: 'page_size', alias_name: '每页', type: 'number', filterType: 'params', value: 15 },
      ],
      chartType: 'bar',
    });
    assert.equal(legacyPaging.page, 2);
    assert.equal(legacyPaging.page_size, 15);
    assert.deepEqual(
      filterChartTypesForAnalysisMode([{ value: 'line' }, { value: 'bar' }], params, undefined),
      [{ value: 'line' }, { value: 'bar' }],
    );
  });
});

const modelCatalog = (): ParamItem[] => [
  modeParam([
    { label: '明细', value: 'detail', charts: ['table'], result: { structure: 'table' } },
    { label: '计数', value: 'count', charts: ['single'], result: { structure: 'value' } },
    { label: '分布', value: 'distribution', charts: ['bar', 'pie', 'topN'], result: { structure: 'category' } },
  ]),
  { name: 'model_id', alias_name: '模型', type: 'string', filterType: 'params', value: 'host' },
  { name: 'page', alias_name: '页码', type: 'number', filterType: 'params', value: 1, visible_modes: ['detail'] },
  { name: 'page_size', alias_name: '每页', type: 'number', filterType: 'params', value: 20, visible_modes: ['detail'] },
];

const withPaging = (page: number, pageSize: number): ParamItem[] =>
  modelCatalog().map((param) => {
    if (param.name === 'page') return { ...param, value: page };
    if (param.name === 'page_size') return { ...param, value: pageSize };
    if (param.name === 'analysis_mode') return { ...param, value: 'detail' };
    return param;
  });

describe('chart requests keep the saved analysis mode and paging', () => {
  it('does not rewrite the mode or drop paging when the chart changes', () => {
    const params = withPaging(3, 50);
    for (const chartType of ['bar', 'pie', 'topN', 'single', 'table']) {
      const request = buildWidgetRequestParams({
        config: { chartType, dataSourceParams: params },
        dataSource: { params: modelCatalog() },
        extraParams: { page: 3, page_size: 50 },
      });
      assert.equal(request.page, 3, chartType);
      assert.equal(request.page_size, 50, chartType);
      assert.equal(request.analysis_mode, 'detail', chartType);
    }
  });

  it('keeps the saved page when the chart returns to the table', () => {
    const params = withPaging(4, 50);
    const request = buildCompareRequestParams({
      config: { chartType: 'table', dataSourceParams: params },
      dataSource: { params: modelCatalog() },
    });
    assert.equal(request.currentParams.analysis_mode, 'detail');
    assert.equal(request.currentParams.page, 4);
    assert.equal(request.currentParams.page_size, 50);
  });

  it('uses the saved chart type for run and compare when the caller omits chartType', async () => {
    const params = withPaging(1, 20);
    const compared = buildCompareRequestParams({
      config: { chartType: 'topN', dataSourceParams: params, dataSource: 8 },
      dataSource: { params: modelCatalog() },
    });
    assert.equal(compared.currentParams.page, 1);
    assert.equal(compared.currentParams.page_size, 20);
    assert.equal(compared.currentParams.analysis_mode, 'detail');

    let captured: Record<string, unknown> | undefined;
    await fetchWidgetData({
      config: { dataSource: 8, chartType: 'pie', dataSourceParams: params },
      dataSource: { params: modelCatalog() },
      getSourceDataByApiId: async (_id, request) => {
        captured = request;
        return { data: { structure: 'category', items: [] } };
      },
    });
    assert.equal(captured?.page, 1);
    assert.equal(captured?.page_size, 20);
    assert.equal(captured?.analysis_mode, 'detail');
  });

  it('keeps four model columns when the table is empty and a re-probe sees no aliases', () => {
    const schema = [
      { key: 'classification_name', title: '分类', value_type: 'string' as const },
      { key: 'model_name', title: '模型名称', value_type: 'string' as const },
      { key: 'model_id', title: '模型标识', value_type: 'string' as const },
      { key: 'instance_count', title: '实例数', value_type: 'number' as const },
    ];
    const headers = resolveTableLikeColumns({ schemaFields: schema, rows: [] });
    assert.deepEqual(headers.map((column) => column.key), schema.map((field) => field.key));
    const probed = mergeDetectedFieldsWithSchema(schema.map((field) => field.key), schema);
    assert.deepEqual(probed.map((column) => column.key), schema.map((field) => field.key));
    assert.equal(probed.some((column) => column.key === 'name' || column.key === 'value'), false);
  });

  it('keeps raw alert and object identifiers out of the default table', () => {
    const schema = [
      { key: 'content', title: '告警名称', value_type: 'string' as const },
      { key: 'monitor_object_name', title: '监控对象', value_type: 'string' as const },
      { key: 'id', title: '告警标识', value_type: 'string' as const, table: false },
      { key: 'monitor_object_id', title: '监控对象标识', value_type: 'string' as const, table: false },
    ];
    const probed = mergeDetectedFieldsWithSchema(
      ['content', 'monitor_object_name', 'id', 'monitor_object_id'],
      schema,
    );
    assert.deepEqual(probed.map((column) => column.key), ['content', 'monitor_object_name']);
  });
});

const optionalPaging = (): ParamItem[] => modelCatalog().map((param) => (
  param.name === 'page' || param.name === 'page_size' ? { ...param, value: null } : param
));

describe('optional paging stays empty until the user fills it', () => {
  it('omits empty paging on every chart and keeps a filled page on count', () => {
    const params = optionalPaging();
    for (const chartType of ['table', 'bar', 'pie', 'topN', 'single']) {
      const request = buildWidgetRequestParams({
        config: { chartType, dataSourceParams: params },
        dataSource: { params },
      });
      assert.equal(request.analysis_mode, 'detail', chartType);
      assert.equal(request.page, undefined, chartType);
      assert.equal(request.page_size, undefined, chartType);
    }
    const counted = buildWidgetRequestParams({
      config: {
        chartType: 'single',
        dataSourceParams: params.map((param) => (
          param.name === 'analysis_mode' ? { ...param, value: 'count' } : param
        )),
      },
      dataSource: { params },
      extraParams: { page: 2, page_size: 10 },
    });
    assert.equal(counted.analysis_mode, 'count');
    assert.equal(counted.page, 2);
    assert.equal(counted.page_size, 10);
  });

  it('keeps paging for a source that has no analysis mode', () => {
    const request = processDataSourceParams({
      sourceParams: [
        { name: 'query', alias_name: '查询', type: 'string', filterType: 'params', value: 'up' },
        { name: 'page', alias_name: '页码', type: 'number', filterType: 'params', value: 2 },
        { name: 'page_size', alias_name: '每页', type: 'number', filterType: 'params', value: 15 },
      ],
      chartType: 'topN',
    });
    assert.equal(request.page, 2);
    assert.equal(request.page_size, 15);
  });
});
