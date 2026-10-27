import assert from 'node:assert/strict';
import test from 'node:test';
import {
  buildTopNItems,
  coerceTopNNumericValue,
  resolveConfiguredTopNBarPercent,
  resolveTopNBarPercent,
  resolveTopNMaxValue,
  validateTopNPayload,
} from '../topNData';

test('numeric strings coerce, IPs and blanks stay empty', () => {
  assert.equal(coerceTopNNumericValue('208036'), 208036);
  assert.equal(coerceTopNNumericValue(208036), 208036);
  assert.equal(coerceTopNNumericValue('0'), 0);
  assert.equal(coerceTopNNumericValue('10.51.176.171'), null);
  assert.equal(coerceTopNNumericValue(''), null);
  assert.equal(coerceTopNNumericValue(true), null);
});

test('log top rows keep names and convert string hits', () => {
  const items = buildTopNItems(
    [
      { value: '208036', name: '10.51.176.171' },
      { value: 'not-a-number', name: '10.51.176.50' },
    ],
    'name',
    'value',
  );

  assert.deepEqual(items, [
    {
      name: '10.51.176.171',
      value: 208036,
      source: { value: '208036', name: '10.51.176.171' },
    },
    {
      name: '10.51.176.50',
      value: null,
      source: { value: 'not-a-number', name: '10.51.176.50' },
    },
  ]);
  assert.equal(resolveTopNMaxValue(items), 208036);
  assert.equal(resolveTopNBarPercent(items[1].value, 208036), 0);
});

test('ranking rows sort by value descending and keep ties in input order', () => {
  const items = buildTopNItems(
    [
      { classification_name: '中间件', value: 2 },
      { classification_name: '主机', value: 9 },
      { classification_name: '数据库', value: 9 },
      { classification_name: '空分类', value: null },
      { classification_name: '网络', value: 4 },
    ],
    'classification_name',
    'value',
  );

  assert.deepEqual(items.map((item) => item.name), ['主机', '数据库', '网络', '中间件', '空分类']);
  assert.deepEqual(items.map((item) => item.value), [9, 9, 4, 2, null]);
  assert.equal(resolveTopNBarPercent(9, 9), 100);
  assert.equal(resolveTopNBarPercent(4, 9), (4 / 9) * 100);
  assert.equal(resolveConfiguredTopNBarPercent(4, items, {}), (4 / 9) * 100);
});

test('absolute bar width uses the configured full score', () => {
  const items = [
    { name: 'CPU', value: 40 },
    { name: '内存', value: 150 },
    { name: '磁盘', value: 0 },
    { name: '空', value: null },
  ];

  assert.equal(resolveTopNBarPercent(40, 100, 'absolute'), 40);
  assert.equal(resolveTopNBarPercent(150, 100, 'absolute'), 100);
  assert.equal(resolveTopNBarPercent(-5, 100, 'absolute'), 0);
  assert.equal(resolveTopNBarPercent(0, 100, 'absolute'), 0);
  assert.equal(
    resolveConfiguredTopNBarPercent(40, items, { barMode: 'absolute', barMax: 100 }),
    40,
  );
  assert.equal(
    resolveConfiguredTopNBarPercent(150, items, { barMode: 'absolute', barMax: 100 }),
    100,
  );
  assert.equal(
    resolveConfiguredTopNBarPercent(25, items, { barMode: 'absolute', gaugeMax: 100 }),
    25,
  );
  assert.notEqual(
    resolveConfiguredTopNBarPercent(40, items, { barMode: 'absolute', barMax: 100 }),
    resolveTopNBarPercent(40, resolveTopNMaxValue(items)),
  );
});

test('relative bars keep a two percent floor and absolute bars stay exact', () => {
  const items = [
    { name: '高', value: 100 },
    { name: '低', value: 1 },
  ];

  assert.equal(resolveConfiguredTopNBarPercent(1, items, {}), 2);
  assert.equal(resolveConfiguredTopNBarPercent(100, items, {}), 100);
  assert.equal(resolveConfiguredTopNBarPercent(0, items, {}), 0);
  assert.equal(resolveConfiguredTopNBarPercent(null, items, {}), 0);
  assert.equal(
    resolveConfiguredTopNBarPercent(1, items, { barMode: 'absolute', barMax: 100 }),
    1,
  );
});

test('scalar fields keep configured order and ignore value ranking', () => {
  const snapshot = {
    host_count: 3,
    avg_disk: 80,
    avg_cpu: 10,
    avg_memory: null,
  };
  const items = buildTopNItems(snapshot, 'name', 'value', {
    scalarFields: [
      { field: 'avg_cpu', label: 'CPU 使用率' },
      { field: ' avg_memory ', label: ' 内存使用率 ' },
      { field: 'avg_disk' },
      { field: ' ', label: '空' },
    ],
  });

  assert.deepEqual(items.map((item) => item.name), ['CPU 使用率', '内存使用率', 'avg_disk']);
  assert.deepEqual(items.map((item) => item.value), [10, null, 80]);
  assert.deepEqual(items.map((item) => item.field), ['avg_cpu', 'avg_memory', 'avg_disk']);
  assert.equal(validateTopNPayload(snapshot, {
    scalarFields: [{ field: 'avg_cpu' }, { field: 'avg_disk' }],
  }), true);
  assert.equal(validateTopNPayload(snapshot), false);
});

test('scalar fields do not change array ranking', () => {
  const rows = [
    { name: '低', value: 1 },
    { name: '高', value: 9 },
  ];
  const items = buildTopNItems(rows, 'name', 'value', {
    scalarFields: [{ field: 'avg_cpu', label: 'CPU' }],
  });

  assert.deepEqual(items.map((item) => item.name), ['高', '低']);
  assert.equal(validateTopNPayload(rows, {
    labelField: 'name',
    valueField: 'value',
    scalarFields: [{ field: 'avg_cpu' }],
  }), true);
  assert.equal(validateTopNPayload({ items: rows }, {
    labelField: 'name',
    valueField: 'value',
    scalarFields: [{ field: 'avg_cpu', label: 'CPU' }],
  }), false);
});
