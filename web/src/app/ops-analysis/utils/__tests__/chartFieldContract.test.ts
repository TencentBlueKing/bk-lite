import assert from 'node:assert/strict';
import test from 'node:test';
import { ChartDataTransformer } from '@/app/ops-analysis/utils/chartDataTransform';
import { buildRoleFieldOptions } from '@/app/ops-analysis/components/widgetConfig/utils/chartFieldOptions';
import { extractComparableValue } from '@/app/ops-analysis/utils/compareQuery';
import { buildTopNItems, validateTopNPayload } from '@/app/ops-analysis/utils/topNData';
import { buildPieCsvTable } from '@/app/ops-analysis/utils/widgetCsvExport';
import { missingConfiguredField } from '@/app/ops-analysis/utils/chartFieldContract';
import type { WidgetCsvLabels } from '@/app/ops-analysis/utils/widgetCsvExport';

const labels = {
  dimension: '维度',
  value: '值',
  name: '名称',
  seriesValue: '数值',
} as WidgetCsvLabels;

const modelFields = [
  { key: 'classification_name', title: '分类', value_type: 'string' as const },
  { key: 'model_name', title: '模型名称', value_type: 'string' as const, role: 'dimension' as const },
  { key: 'model_id', title: '模型标识', value_type: 'string' as const, role: 'identity' as const },
  { key: 'instance_count', title: '实例数', value_type: 'number' as const, role: 'measure' as const },
];

const modelDistribution = {
  structure: 'category',
  status: 'ok',
  items: [
    { classification_name: '计算', model_name: '主机', model_id: 'host', instance_count: 4 },
    { classification_name: '运维', model_name: '主机', model_id: 'host_shadow', instance_count: 4 },
    { classification_name: '空间', model_name: '机房', model_id: 'room', instance_count: 0 },
  ],
  fields: modelFields,
};

test('model distribution charts use the columns the user selected', () => {
  const mapping = { dimensionField: 'model_name', valueField: 'instance_count' };
  const bar = ChartDataTransformer.transformToLineBarData(modelDistribution, mapping);
  const pie = ChartDataTransformer.transformToPieData(modelDistribution, mapping);
  const ranked = buildTopNItems(modelDistribution, 'model_name', 'instance_count');

  assert.deepEqual(ChartDataTransformer.transformToLineBarData(modelDistribution).categories, []);
  assert.deepEqual(bar.categories, ['主机', '主机', '机房']);
  assert.deepEqual(bar.values, [4, 4, 0]);
  assert.deepEqual(pie.map((item) => item.name), ['主机', '主机', '机房']);
  assert.deepEqual(pie.map((item) => item.label), [undefined, undefined, undefined]);
  assert.deepEqual(pie.map((item) => item.value), [4, 4, 0]);
  assert.equal(ChartDataTransformer.validateLineBarData(modelDistribution, '数据格式不匹配', mapping).isValid, true);
  assert.equal(ChartDataTransformer.validatePieData(modelDistribution, '数据格式不匹配', mapping).isValid, true);
  assert.equal(validateTopNPayload(modelDistribution, {
    labelField: 'model_name',
    valueField: 'instance_count',
  }), true);
  assert.deepEqual(ranked.map((item) => [item.name, item.value]), [
    ['主机', 4],
    ['主机', 4],
    ['机房', 0],
  ]);
});

test('single value uses the first number unless a display field is selected', () => {
  const payload = {
    structure: 'value',
    count: 99,
    model_count: 0,
    unit: '个',
    aggregation: '模型计数',
    fields: [{ key: 'model_count', title: '模型数', value_type: 'number', role: 'measure' }],
  };
  assert.equal(extractComparableValue(payload), 99);
  assert.equal(extractComparableValue(payload, 'model_count'), 0);
  assert.equal(ChartDataTransformer.isStructurallyEmpty({
    structure: 'value',
    model_count: 0,
    unit: '个',
  }), false);
  assert.equal(ChartDataTransformer.isStructurallyEmpty({
    aggregate_value: null,
    aggregate_field: 'cpu',
  }), false);
  assert.equal(missingConfiguredField({
    aggregate_value: null,
  }, ['model_name']), undefined);
  assert.equal(extractComparableValue(payload, 'missing'), null);
  assert.equal(
    ChartDataTransformer.validatePieData(payload, 'bad', { dimensionField: 'model_name', valueField: 'instance_count' }).message,
    'bad',
  );
});

test('an empty result does not report a missing selected field', () => {
  const empty = {
    items: [],
  };
  assert.equal(missingConfiguredField(empty, ['model_name']), undefined);
  assert.equal(ChartDataTransformer.validateLineBarData(empty, 'bad', {
    dimensionField: 'model_name',
    valueField: 'instance_count',
  }).isValid, true);
  assert.equal(missingConfiguredField({
    ...empty,
    fields: [{ key: 'model_count', title: '模型数', value_type: 'number', role: 'measure' }],
  }, ['model_name']), undefined);
});

test('unfilled distribution categories show as -- and share one count', () => {
  const payload = {
    structure: 'category',
    status: 'ok',
    items: [
      { status: null, instance_count: 2 },
      { status: '已上线', instance_count: 8 },
      { status: '', instance_count: 3 },
      { status: 0, instance_count: 1 },
      { status: false, instance_count: 4 },
    ],
    fields: [
      { key: 'status', title: '运行状态', value_type: 'string', role: 'dimension' as const },
      { key: 'instance_count', title: '实例数', value_type: 'number', role: 'measure' as const },
    ],
  };
  const mapping = { dimensionField: 'status', valueField: 'instance_count' };
  const bar = ChartDataTransformer.transformToLineBarData(payload, mapping);
  const pie = ChartDataTransformer.transformToPieData(payload, mapping);
  const ranked = buildTopNItems(payload, 'status', 'instance_count');
  assert.deepEqual(bar.categories, ['--', '已上线', '0', 'false']);
  assert.deepEqual(bar.values, [5, 8, 1, 4]);
  assert.equal(bar.points?.[0]?.numeric, 5);
  assert.equal(bar.points?.[0]?.fields?.status, null);
  assert.deepEqual(pie.map((item) => item.name), ['', '已上线', '', '0', 'false']);
  assert.deepEqual(pie.map((item) => item.value), [2, 8, 3, 1, 4]);
  assert.deepEqual(ranked.map((item) => [item.name, item.value]), [
    ['已上线', 8],
    ['false', 4],
    ['0', 1],
  ]);
  assert.equal(payload.items[0].status, null);
  assert.equal(payload.items[2].status, '');
});

test('one hop blank start name and metric time map without source-specific names', () => {
  const hop = {
    structure: 'category',
    status: 'ok',
    items: [{ start_name: '', start_uuid: 'start-1', relation_count: 2 }],
    fields: [
      { key: 'start_name', title: '起点名称', value_type: 'string', role: 'dimension' },
      { key: 'start_uuid', title: '起点标识', value_type: 'string', role: 'identity' },
      { key: 'relation_count', title: '关联数', value_type: 'number', role: 'measure' },
    ],
  };
  const ranked = buildTopNItems(hop, 'start_name', 'relation_count');
  assert.deepEqual(ranked, []);
  const pie = ChartDataTransformer.transformToPieData(hop, {
    dimensionField: 'start_name',
    valueField: 'relation_count',
  });
  assert.equal(pie[0]?.name, '');
  assert.equal(pie[0]?.label, undefined);
  assert.equal(pie[0]?.value, 2);

  const chart = ChartDataTransformer.transformToLineBarData({
    host: [['2026-01-01T00:00:00Z', 0]],
  });
  assert.equal(chart.series?.[0]?.data?.[0], 0);
  assert.equal(chart.categories.length, 1);
});

test('field options come from the schema and keys found in the sample', () => {
  const schema = [
    ...modelFields.map((field) => ({ ...field, modes: ['detail', 'distribution'] })),
    { key: 'model_count', title: '模型数', value_type: 'number' as const, role: 'measure' as const, modes: ['count'] },
  ];
  const previewOptions = buildRoleFieldOptions(schema, modelDistribution);
  assert.deepEqual(previewOptions.map((option) => option.value), [
    'classification_name',
    'model_name',
    'model_id',
    'instance_count',
    'model_count',
  ]);
  const rowsOnly = buildRoleFieldOptions(schema, {
    structure: 'category',
    items: [{ end_name: 'A', start_count: 1 }],
  });
  assert.deepEqual(rowsOnly.map((option) => option.value), [
    'classification_name',
    'model_name',
    'model_id',
    'instance_count',
    'model_count',
    'end_name',
    'start_count',
  ]);
});

test('pie export keeps duplicate model names, zero and the real field titles', () => {
  const table = buildPieCsvTable(modelDistribution, {
    dimensionField: 'model_name',
    valueField: 'instance_count',
  }, labels, modelFields);
  assert.deepEqual(table.headers[0], '模型名称');
  assert.equal(table.headers[1].includes('实例数'), true);
  assert.deepEqual(table.rows, [
    ['主机', '4'],
    ['主机', '4'],
    ['机房', '0'],
  ]);
});
