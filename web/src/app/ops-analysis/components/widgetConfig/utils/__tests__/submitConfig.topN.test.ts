import assert from 'node:assert/strict';
import test from 'node:test';
import { buildWidgetSubmitConfig } from '../submitConfig';

const base = {
  chartType: 'topN',
  showChartThemeMode: false,
  showTableFilterFields: false,
  selectedFields: [],
  thresholdColors: [],
  filterBindings: {},
  displayColumns: [],
  filterFields: [],
  actions: [],
};

test('topN submit without scalar fields keeps label and value ranking', () => {
  const result = buildWidgetSubmitConfig({
    ...base,
    values: {
      name: '排行',
      chartType: 'topN',
      topNLabelField: 'name',
      topNValueField: 'value',
      barMode: 'relative',
      barMax: 100,
    },
  });

  assert.equal(result.error, undefined);
  assert.equal(result.config?.topNLabelField, 'name');
  assert.equal(result.config?.topNValueField, 'value');
  assert.equal(result.config?.topNScalarFields, undefined);
  assert.equal(result.config?.barMode, undefined);
  assert.equal(result.config?.barMax, undefined);
});

test('topN submit prefers scalar rows and stores an absolute full score', () => {
  const result = buildWidgetSubmitConfig({
    ...base,
    values: {
      name: '主机关键指标',
      chartType: 'topN',
      topNLabelField: 'name',
      topNValueField: 'value',
      topNScalarFields: [
        { field: 'avg_cpu', label: 'CPU 使用率' },
        { field: ' avg_memory ', label: ' 内存使用率 ' },
        { field: ' ', label: '空' },
      ],
      barMode: 'absolute',
      barMax: 100,
      unitId: 'percent',
      decimalPlaces: 1,
    },
  });

  assert.equal(result.error, undefined);
  assert.deepEqual(result.config?.topNScalarFields, [
    { field: 'avg_cpu', label: 'CPU 使用率' },
    { field: 'avg_memory', label: '内存使用率' },
  ]);
  assert.equal(result.config?.topNLabelField, undefined);
  assert.equal(result.config?.topNValueField, undefined);
  assert.equal(result.config?.barMode, 'absolute');
  assert.equal(result.config?.barMax, 100);
  assert.equal(result.config?.unitId, 'percent');
  assert.equal(result.config?.decimalPlaces, 1);
});
