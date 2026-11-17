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

test('topN submit keeps label and value and drops scalar rows and bar scale', () => {
  const result = buildWidgetSubmitConfig({
    ...base,
    values: {
      name: '排行',
      chartType: 'topN',
      topNLabelField: 'name',
      topNValueField: 'value',
      topNScalarFields: [
        { field: 'avg_cpu', label: 'CPU 使用率' },
        { field: 'avg_memory', label: '内存使用率' },
      ],
      barMode: 'absolute',
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
