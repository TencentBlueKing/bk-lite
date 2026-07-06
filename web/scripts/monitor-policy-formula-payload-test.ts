import assert from 'node:assert/strict';

import {
  assignMetricRowRefs,
  buildMetricExpressionQueryCondition,
  extractFormulaRefs,
  toMetricRowsFromMetricCondition,
  validateMetricExpressionPayload
} from '../src/app/monitor/(pages)/event/strategy/detail/formulaExpressionUtils';

const singleRows = toMetricRowsFromMetricCondition(
  {
    type: 'metric',
    metric_id: 10,
    filter: [
      { name: 'service', method: '=', value: 'checkout' },
      { logic: 'or', name: 'status', method: '=~', value: '5..' }
    ]
  },
  {
    groupAlgorithm: 'sum',
    groupBy: ['instance_id']
  }
);

assert.equal(singleRows.length, 1);
assert.equal(singleRows[0].ref, 'a');
assert.equal(singleRows[0].metricId, 10);

const singlePayload = buildMetricExpressionQueryCondition({
  resultName: '',
  expression: '',
  rows: singleRows
});

assert.deepEqual(singlePayload, {
  type: 'metric',
  metric_id: 10,
  filter: [
    { name: 'service', method: '=', value: 'checkout' },
    { logic: 'or', name: 'status', method: '=~', value: '5..' }
  ]
});

const refs = extractFormulaRefs('a / b * 100');
assert.deepEqual(refs, ['a', 'b']);

const formulaRows = assignMetricRowRefs([
  {
    ref: '',
    metricId: 1,
    filters: [
      { name: 'service', method: '=', value: 'checkout' },
      { logic: 'and', name: 'status', method: '=~', value: '5..' }
    ],
    groupAlgorithm: 'sum',
    groupBy: ['instance_id', 'status']
  },
  {
    ref: 'z',
    metricId: 2,
    filters: [
      { name: 'service', method: '=', value: 'checkout' },
      { logic: 'or', name: 'status', method: '=', value: '200' }
    ],
    groupAlgorithm: 'sum',
    groupBy: ['instance_id']
  }
]);

assert.deepEqual(
  formulaRows.map((row) => row.ref),
  ['a', 'b']
);

const formulaPayload = buildMetricExpressionQueryCondition({
  resultName: 'HTTP 5xx 错误率',
  expression: 'a / b * 100',
  rows: formulaRows
});

assert.equal(formulaPayload.type, 'formula');
assert.equal(formulaPayload.result_name, 'HTTP 5xx 错误率');
assert.equal(formulaPayload.expression, 'a / b * 100');
assert.equal(formulaPayload.queries[0].ref, 'a');
assert.equal(formulaPayload.queries[1].ref, 'b');
assert.deepEqual(formulaPayload.queries[1].filter, [
  { name: 'service', method: '=', value: 'checkout' },
  { logic: 'or', name: 'status', method: '=', value: '200' }
]);
assert.deepEqual(formulaPayload.queries[1].group_by, ['instance_id']);

assert.deepEqual(
  validateMetricExpressionPayload({
    resultName: '',
    expression: 'a / b',
    rows: formulaRows
  }),
  ['结果名称不能为空']
);

assert.deepEqual(
  validateMetricExpressionPayload({
    resultName: 'HTTP 5xx 错误率',
    expression: '',
    rows: formulaRows
  }),
  ['表达式不能为空']
);

assert.deepEqual(
  validateMetricExpressionPayload({
    resultName: 'HTTP 5xx 错误率',
    expression: 'a / c',
    rows: formulaRows
  }),
  ['表达式引用了不存在的变量：c']
);

assert.deepEqual(
  validateMetricExpressionPayload({
    resultName: 'HTTP 5xx 错误率',
    expression: 'a / b * 100',
    rows: formulaRows.slice(0, 1)
  }),
  ['表达式引用了不存在的变量：b']
);

console.log('monitor-policy-formula-payload-test passed');
