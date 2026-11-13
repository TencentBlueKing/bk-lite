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

test('model distribution bar, pie and topN use model_name and instance_count without a mapping', () => {
  const bar = ChartDataTransformer.transformToLineBarData(modelDistribution);
  const pie = ChartDataTransformer.transformToPieData(modelDistribution);
  const ranked = buildTopNItems(modelDistribution);

  assert.deepEqual(bar.categories, ['主机', '主机', '机房']);
  assert.deepEqual(bar.values, [4, 4, 0]);
  assert.deepEqual(pie.map((item) => item.label), ['主机', '主机', '机房']);
  assert.deepEqual(pie.map((item) => item.name), ['host', 'host_shadow', 'room']);
  assert.deepEqual(pie.map((item) => item.value), [4, 4, 0]);
  assert.equal(ChartDataTransformer.validateLineBarData(modelDistribution).isValid, true);
  assert.equal(ChartDataTransformer.validatePieData(modelDistribution).isValid, true);
  assert.equal(validateTopNPayload(modelDistribution), true);
  assert.deepEqual(ranked.map((item) => [item.name, item.value]), [
    ['主机', 4],
    ['主机', 4],
    ['机房', 0],
  ]);
});

test('model count zero stays visible and does not scan another number', () => {
  const payload = {
    structure: 'value',
    status: 'ok',
    model_count: 0,
    unit: '个',
    aggregation: '模型计数',
    count: 99,
    fields: [{ key: 'model_count', title: '模型数', value_type: 'number', role: 'measure' }],
  };
  assert.equal(extractComparableValue(payload), 0);
  assert.equal(ChartDataTransformer.isStructurallyEmpty(payload), false);
  assert.equal(extractComparableValue(payload, 'missing'), null);
  assert.equal(
    ChartDataTransformer.validatePieData(payload, 'bad', { dimensionField: 'model_name', valueField: 'instance_count' }).message,
    'dashboard.chartFieldMissing:model_name',
  );
});

test('empty result is not a missing field, but authoritative fields still are', () => {
  const empty = {
    structure: 'category',
    status: 'empty',
    items: [],
    fields: modelFields,
  };
  assert.equal(missingConfiguredField(empty, ['model_name']), undefined);
  assert.equal(ChartDataTransformer.validateLineBarData(empty, 'bad', {
    dimensionField: 'model_name',
    valueField: 'instance_count',
  }).isValid, true);
  assert.equal(missingConfiguredField({
    ...empty,
    fields: [{ key: 'model_count', title: '模型数', value_type: 'number', role: 'measure' }],
  }, ['model_name']), 'model_name');
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
  const bar = ChartDataTransformer.transformToLineBarData(payload);
  const pie = ChartDataTransformer.transformToPieData(payload);
  const ranked = buildTopNItems(payload);
  assert.deepEqual(bar.categories, ['--', '已上线', '0', 'false']);
  assert.deepEqual(bar.values, [5, 8, 1, 4]);
  assert.equal(bar.points?.[0]?.numeric, 5);
  assert.equal(bar.points?.[0]?.fields?.status, null);
  assert.deepEqual(pie.map((item) => item.name), ['--', '已上线', '0', 'false']);
  assert.deepEqual(pie.map((item) => item.value), [5, 8, 1, 4]);
  assert.deepEqual(ranked.map((item) => [item.name, item.value]), [
    ['已上线', 8],
    ['--', 5],
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
  const ranked = buildTopNItems(hop);
  assert.equal(ranked[0]?.name, 'start-1');
  assert.equal(ranked[0]?.value, 2);
  const pie = ChartDataTransformer.transformToPieData(hop);
  assert.equal(pie[0]?.name, 'start-1');
  assert.equal(pie[0]?.label, 'start-1');
  assert.equal(pie[0]?.value, 2);

  const series = {
    structure: 'series',
    status: 'ok',
    series: { host: [{ time: '2026-01-01T00:00:00Z', value: 0 }] },
    fields: [
      { key: 'time', title: '时间', value_type: 'datetime', role: 'dimension' },
      { key: 'value', title: '值', value_type: 'number', role: 'measure' },
    ],
  };
  const chart = ChartDataTransformer.transformToLineBarData(series);
  assert.equal(chart.series?.[0]?.data?.[0], 0);
  assert.equal(chart.categories.length, 1);
});

test('candidates follow response fields and do not union fields from another mode', () => {
  const schema = [
    ...modelFields.map((field) => ({ ...field, modes: ['detail', 'distribution'] })),
    { key: 'model_count', title: '模型数', value_type: 'number' as const, role: 'measure' as const, modes: ['count'] },
  ];
  const previewOptions = buildRoleFieldOptions(schema, modelDistribution, 'distribution');
  assert.deepEqual(previewOptions.map((option) => option.value), [
    'classification_name',
    'model_name',
    'model_id',
    'instance_count',
  ]);
  const countOptions = buildRoleFieldOptions(schema, undefined, 'count');
  assert.deepEqual(countOptions.map((option) => option.value), ['model_count']);
  const rowsOnly = buildRoleFieldOptions(schema, {
    structure: 'category',
    items: [{ end_name: 'A', start_count: 1 }],
  }, 'distribution');
  assert.deepEqual(rowsOnly.map((option) => option.value), ['end_name', 'start_count']);
});

test('pie export keeps duplicate model names, zero and the real field titles', () => {
  const table = buildPieCsvTable(modelDistribution, {}, labels);
  assert.deepEqual(table.headers[0], '模型名称');
  assert.equal(table.headers[1].includes('实例数'), true);
  assert.deepEqual(table.rows, [
    ['主机', '4'],
    ['主机', '4'],
    ['机房', '0'],
  ]);
});
