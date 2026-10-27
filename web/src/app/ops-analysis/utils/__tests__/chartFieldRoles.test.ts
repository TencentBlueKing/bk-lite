import assert from 'node:assert/strict';
import test from 'node:test';
import { formatPeriodCompare, validateGaugeData } from '../compareQuery';
import { ChartDataTransformer } from '../chartDataTransform';

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
