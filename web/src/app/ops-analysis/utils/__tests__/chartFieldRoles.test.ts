import assert from 'node:assert/strict';
import test from 'node:test';
import { formatPeriodCompare, validateGaugeData } from '../compareQuery';
import { ChartDataTransformer } from '../chartDataTransform';
import {
  buildLineBarValueFieldOptions,
  recommendLineBarFields,
} from '../lineBarFieldMapping';

test('mapped line chart reads selected columns and leaves incomplete numbers empty', () => {
  const chart = ChartDataTransformer.transformToLineBarData(
    [
      { src_ip: '10.0.0.1', value: '12' },
      { src_ip: '10.0.0.2', value: '1abc' },
    ],
    { dimensionField: 'src_ip', valueField: 'value' },
  );

  assert.deepEqual(chart.categories, ['10.0.0.1', '10.0.0.2']);
  assert.deepEqual(chart.values, [12, null]);
  assert.equal(chart.series, undefined);
  assert.equal(
    ChartDataTransformer.validateLineBarData(
      [
        { src_ip: '10.0.0.2', value: '1abc' },
      ],
      '数据格式不匹配',
      { dimensionField: 'src_ip', valueField: 'value' },
    ).isValid,
    true,
  );
});

test('unmapped line chart still reads name and count', () => {
  const chart = ChartDataTransformer.transformToLineBarData([
    { name: 'a', count: 3 },
  ]);

  assert.deepEqual(chart.categories, ['a']);
  assert.deepEqual(chart.values, [3]);
});

test('mapped single series prefers valueFields and matches the row-wise chart', () => {
  const chart = ChartDataTransformer.transformToLineBarData(
    [
      { src_ip: '10.0.0.1', value: '12', other: 9 },
      { src_ip: '10.0.0.2', value: 4, other: 1 },
    ],
    {
      dimensionField: 'src_ip',
      valueField: 'other',
      valueFields: ['value'],
    },
  );

  assert.deepEqual(chart.categories, ['10.0.0.1', '10.0.0.2']);
  assert.deepEqual(chart.values, [12, 4]);
  assert.equal(chart.series, undefined);
});

test('wide line chart makes one series per value field and nulls duplicate categories', () => {
  const rows = [
    { ts: 'b', cpu: 1, mem: '' },
    { ts: 'a', cpu: '3', mem: 4 },
    { ts: 'a', cpu: 9, mem: 5 },
  ];
  const mapping = {
    dimensionField: 'ts',
    valueFields: ['cpu', 'mem'],
    fieldLabels: { cpu: 'CPU 使用率' },
  };
  const chart = ChartDataTransformer.transformToLineBarData(rows, mapping);

  assert.deepEqual(chart.categories, ['b', 'a']);
  assert.deepEqual(chart.series?.map((series) => series.name), ['CPU 使用率', 'mem']);
  assert.deepEqual(chart.series?.[0]?.data, [1, null]);
  assert.deepEqual(chart.series?.[1]?.data, [null, null]);
  assert.equal(chart.series?.[0]?.points?.[1]?.numeric, undefined);
  assert.equal(
    ChartDataTransformer.validateLineBarData(rows, '数据格式不匹配', {
      ...mapping,
      seriesField: 'host',
    }).message,
    'dashboard.lineBarSeriesFieldConflict',
  );
  assert.equal(
    ChartDataTransformer.validateLineBarData(rows, '数据格式不匹配', mapping).isValid,
    true,
  );
});

test('wide line chart keeps points when formatted time labels collide', () => {
  const rows = [
    { ts: '2024-01-01 10:00:01', cpu: 1, mem: 10 },
    { ts: '2024-01-01 10:00:40', cpu: 2, mem: 20 },
    { ts: '2025-01-01 10:00:00', cpu: 3, mem: 30 },
  ];
  const sameRaw = [
    { ts: '2024-01-01 10:00:01', cpu: 1, mem: 10 },
    { ts: '2024-01-01 10:00:01', cpu: 9, mem: 11 },
  ];
  const mapping = {
    dimensionField: 'ts',
    valueFields: ['cpu', 'mem'],
  };
  const chart = ChartDataTransformer.transformToLineBarData(rows, mapping);
  const duplicate = ChartDataTransformer.transformToLineBarData(sameRaw, mapping);

  assert.equal(chart.categories?.length, 3);
  assert.equal(chart.categories?.[0], chart.categories?.[1]);
  assert.deepEqual(chart.series?.[0]?.data, [1, 2, 3]);
  assert.deepEqual(chart.series?.[1]?.data, [10, 20, 30]);
  assert.equal(duplicate.categories?.length, 1);
  assert.deepEqual(duplicate.series?.[0]?.data, [null]);
  assert.deepEqual(duplicate.series?.[1]?.data, [null]);
});

test('long line chart splits series by field value and leaves empty numbers null', () => {
  const rows = [
    { ts: '10:00', metric: 'cpu', value: 1 },
    { ts: '10:00', metric: 'mem', value: null },
    { ts: '11:00', metric: 'cpu', value: '2' },
    { ts: '10:00', metric: 'cpu', value: 8 },
  ];
  const mapping = {
    dimensionField: 'ts',
    valueFields: ['value'],
    valueField: 'value',
    seriesField: 'metric',
  };
  const chart = ChartDataTransformer.transformToLineBarData(rows, mapping);

  assert.deepEqual(chart.categories, ['10:00', '11:00']);
  assert.deepEqual(chart.series?.map((series) => series.name), ['cpu', 'mem']);
  assert.deepEqual(chart.series?.[0]?.data, [null, 2]);
  assert.deepEqual(chart.series?.[1]?.data, [null, null]);
  assert.equal(
    ChartDataTransformer.validateLineBarData(rows, '数据格式不匹配', mapping).isValid,
    true,
  );
  assert.equal(
    ChartDataTransformer.validateLineBarData(
      [{ ts: '10:00', metric: 'cpu', value: '1abc' }],
      '数据格式不匹配',
      mapping,
    ).message,
    'dashboard.lineBarValueFieldNotNumeric',
  );
});

test('unmapped line chart still draws multi-series objects', () => {
  const chart = ChartDataTransformer.transformToLineBarData({
    cpu: [{ name: '10:00', value: 1 }],
  });

  assert.deepEqual(chart.categories, ['10:00']);
  assert.equal(chart.series?.[0]?.name, 'cpu');
  assert.deepEqual(chart.series?.[0]?.data, [1]);
});

test('mapped line chart reads rows wrapped in data or items', () => {
  const wrapped = ChartDataTransformer.transformToLineBarData(
    { data: [{ src_ip: '10.0.0.1', value: 3 }] },
    { dimensionField: 'src_ip', valueField: 'value' },
  );
  const items = ChartDataTransformer.transformToPieData(
    { items: [{ host: 'a', count: 2 }] },
    { dimensionField: 'host', valueField: 'count' },
  );

  assert.deepEqual(wrapped.categories, ['10.0.0.1']);
  assert.deepEqual(wrapped.values, [3]);
  assert.deepEqual(items.map(({ name, value }) => ({ name, value })), [{ name: 'a', value: 2 }]);
  assert.equal(items[0]?.__link?.fields?.host, 'a');
  assert.equal(items[0]?.__link?.raw, 2);
});

test('mapped line chart does not fall back to multi-series', () => {
  const chart = ChartDataTransformer.transformToLineBarData(
    { cpu: [{ name: '10:00', value: 1 }] },
    { dimensionField: 'name', valueField: 'value' },
  );

  assert.deepEqual(chart.categories, []);
});

test('gauge with a selected field stays renderable when the value is not a complete number', () => {
  assert.equal(
    validateGaugeData({ usage: '1abc' }, { selectedFields: ['usage'] }).isValid,
    true,
  );
  assert.equal(
    validateGaugeData([{ ready: true }], { selectedFields: ['ready'] }).isValid,
    true,
  );
  assert.equal(validateGaugeData({ usage: '1abc' }).isValid, false);
});

test('mapped pie chart with only incomplete numbers is an empty chart, not a format error', () => {
  const result = ChartDataTransformer.validatePieData(
    [{ host: 'a', count: '1abc' }],
    '数据格式不匹配',
    { dimensionField: 'host', valueField: 'count' },
  );

  assert.equal(result.isValid, true);
});

test('mapped pie chart omits slices that are not complete numbers', () => {
  const slices = ChartDataTransformer.transformToPieData(
    [
      { host: 'a', count: 4 },
      { host: 'b', count: '1abc' },
      { host: 'c', count: 0 },
    ],
    { dimensionField: 'host', valueField: 'count' },
  );

  assert.deepEqual(slices.map(({ name, value }) => ({ name, value })), [
    { name: 'a', value: 4 },
    { name: 'c', value: 0 },
  ]);
  assert.equal(slices[0]?.__link?.numeric, 4);
  assert.equal(slices[1]?.__link?.numeric, 0);
});

test('scalar pie binds two object fields and leaves root arrays on the existing path', () => {
  const slices = ChartDataTransformer.transformToPieData(
    {
      collected_instance_count: 3,
      uncollected_instance_count: null,
      extra: 9,
    },
    {
      pieScalarFields: [
        { field: 'collected_instance_count', label: '已采集' },
        { field: 'uncollected_instance_count' },
        { field: ' ' },
      ],
    },
  );

  assert.deepEqual(slices.map(({ name, value }) => ({ name, value })), [
    { name: '已采集', value: 3 },
    { name: 'uncollected_instance_count', value: 0 },
  ]);

  const arraySlices = ChartDataTransformer.transformToPieData(
    [{ name: '主机', value: 4 }],
    {
      pieScalarFields: [
        { field: 'collected_instance_count', label: '已采集' },
        { field: 'uncollected_instance_count', label: '未采集' },
      ],
    },
  );
  assert.deepEqual(arraySlices.map(({ name, value }) => ({ name, value })), [
    { name: '主机', value: 4 },
  ]);

  const oneField = ChartDataTransformer.transformToPieData(
    { collected_instance_count: 3, uncollected_instance_count: 1 },
    { pieScalarFields: [{ field: 'collected_instance_count' }] },
  );
  assert.deepEqual(oneField, []);

  const invalid = ChartDataTransformer.validatePieData(
    { collected_instance_count: 3, uncollected_instance_count: '1abc' },
    '数据格式不匹配',
    {
      pieScalarFields: [
        { field: 'collected_instance_count' },
        { field: 'uncollected_instance_count' },
      ],
    },
  );
  assert.equal(invalid.isValid, false);
});

test('line bar value options keep only numeric columns when schema can tell them apart', () => {
  const options = [
    { label: 'host', value: 'host' },
    { label: 'cpu', value: 'cpu' },
    { label: 'extra', value: 'extra' },
  ];
  assert.deepEqual(
    buildLineBarValueFieldOptions([
      { key: 'host', title: '主机', value_type: 'string' },
      { key: 'cpu', title: 'CPU', value_type: 'number' },
    ], options).map((option) => option.value),
    ['cpu', 'extra'],
  );
  assert.deepEqual(
    buildLineBarValueFieldOptions([], options).map((option) => option.value),
    ['host', 'cpu', 'extra'],
  );
});

test('recommended line bar fields prefer name and value, otherwise the first non-numeric and numeric columns', () => {
  assert.deepEqual(
    recommendLineBarFields([
      { key: 'cpu', value_type: 'number' },
      { key: 'name', value_type: 'string' },
      { key: 'value', value_type: 'number' },
    ]),
    { dimensionField: 'name', valueFields: ['value'] },
  );
  assert.deepEqual(
    recommendLineBarFields([
      { key: 'ts', value_type: 'datetime' },
      { key: 'cpu', value_type: 'number' },
      { key: 'mem', value_type: 'number' },
    ]),
    { dimensionField: 'ts', valueFields: ['cpu'] },
  );
  assert.deepEqual(
    recommendLineBarFields([], [
      { host: 'a', cpu: 1 },
      { host: 'b', cpu: 2 },
    ]),
    { dimensionField: 'host', valueFields: ['cpu'] },
  );
});

test('period compare formats the same arrow as a single value', () => {
  assert.deepEqual(
    formatPeriodCompare({ current: 86, baseline: 80, compareMode: 'percent' }),
    { text: '↑7.5%', tone: 'up' },
  );
  assert.deepEqual(
    formatPeriodCompare({
      current: 40,
      baseline: 45,
      compareMode: 'value',
      decimalPlaces: 1,
      unitLabel: '%',
    }),
    { text: '↓5.0%', tone: 'down' },
  );
  assert.equal(
    formatPeriodCompare({ current: null, baseline: 1 }).text,
    '--',
  );
});
