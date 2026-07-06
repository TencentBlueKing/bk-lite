import assert from 'node:assert/strict';

import {
  assignMetricRowRefs,
  buildMetricExpressionPreviewPayload,
  buildMetricExpressionQueryCondition,
  extractFormulaRefs,
  shouldShowFormulaEditor,
  toMetricExpressionStateFromQueryCondition,
  toMetricRowsFromMetricCondition,
  validateMetricExpressionPayload
} from '../src/app/monitor/(pages)/event/strategy/detail/formulaExpressionUtils';

const assertValidationIncludes = (
  errors: string[],
  expectedMessage: string
) => {
  assert.ok(
    errors.includes(expectedMessage),
    `Expected validation errors to include "${expectedMessage}", got ${JSON.stringify(errors)}`
  );
};

const assertBuildThrows = (
  rows: Parameters<typeof buildMetricExpressionQueryCondition>[0]['rows'],
  expectedMessage: string
) => {
  assert.throws(
    () =>
      buildMetricExpressionQueryCondition({
        resultName: 'HTTP 5xx 错误率',
        expression: 'a / b',
        rows
      }),
    (error) =>
      error instanceof Error && error.message.includes(expectedMessage)
  );
};

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

const previewInstance = {
  instance_id: 'host-1',
  instance_name: 'host-1',
  instance_id_values: ['host-1']
};

const formulaPreviewPayload = buildMetricExpressionPreviewPayload({
  monitorObjId: 'linux',
  source: {
    type: 'instance',
    values: ['host-1']
  },
  metrics: [
    {
      id: 1,
      name: 'http_5xx_total',
      display_name: 'HTTP 5xx',
      unit: 'short',
      dimensions: [],
      instance_id_keys: ['instance_id']
    },
    {
      id: 2,
      name: 'http_requests_total',
      display_name: 'HTTP 请求',
      unit: 'short',
      dimensions: [],
      instance_id_keys: ['instance_id']
    }
  ],
  mode: 'formula',
  resultName: 'HTTP 5xx 错误率',
  expression: 'a / b * 100',
  rows: formulaRows,
  selectedInstance: previewInstance,
  period: 1,
  periodUnit: 'min',
  algorithm: 'avg_over_time',
  groupAlgorithm: 'max',
  groupBy: ['ignored_dimension'],
  calculationUnit: 'percent'
});

assert.equal(formulaPreviewPayload?.query_condition.type, 'formula');
assert.equal(formulaPreviewPayload?.group_algorithm, 'sum');
assert.deepEqual(formulaPreviewPayload?.group_by, ['instance_id', 'status']);
assert.equal(formulaPreviewPayload?.metric_unit, '');
assert.equal(formulaPreviewPayload?.calculation_unit, 'percent');
assert.deepEqual(formulaPreviewPayload?.preview, {
  instance_id: 'host-1',
  instance_id_values: ['host-1'],
  duration_points: 30
});

const metricPreviewPayload = buildMetricExpressionPreviewPayload({
  monitorObjId: 'linux',
  source: {
    type: 'instance',
    values: ['host-1']
  },
  metrics: [
    {
      id: 10,
      name: 'cpu_usage',
      display_name: 'CPU 使用率',
      unit: 'percent',
      dimensions: [],
      instance_id_keys: ['instance_id']
    }
  ],
  mode: 'metric',
  resultName: '',
  expression: '',
  rows: singleRows,
  selectedInstance: previewInstance,
  period: 5,
  periodUnit: 'min',
  algorithm: 'avg_over_time',
  groupAlgorithm: 'avg',
  groupBy: ['instance_id'],
  calculationUnit: null
});

assert.deepEqual(metricPreviewPayload?.query_condition, singlePayload);
assert.equal(metricPreviewPayload?.group_algorithm, 'avg');
assert.deepEqual(metricPreviewPayload?.group_by, ['instance_id']);
assert.equal(metricPreviewPayload?.metric_unit, 'percent');

assert.throws(
  () =>
    buildMetricExpressionPreviewPayload({
      monitorObjId: 'linux',
      source: {
        type: 'instance',
        values: ['host-1']
      },
      metrics: [],
      mode: 'formula',
      resultName: '',
      expression: 'a / b',
      rows: formulaRows,
      selectedInstance: previewInstance,
      period: 5,
      periodUnit: 'min',
      algorithm: 'avg_over_time',
      groupAlgorithm: 'avg',
      groupBy: ['instance_id'],
      calculationUnit: null
    }),
  (error) => error instanceof Error && error.message.includes('结果名称不能为空')
);

assert.deepEqual(
  validateMetricExpressionPayload({
    resultName: '',
    expression: 'a / b',
    rows: formulaRows
  }),
  ['结果名称不能为空']
);

assertValidationIncludes(
  validateMetricExpressionPayload({
    resultName: 'HTTP 5xx 错误率',
    expression: 'a / b',
    rows: [{ ...formulaRows[0], metricId: null }]
  }),
  '指标 a 必须选择有效指标'
);

assertValidationIncludes(
  validateMetricExpressionPayload({
    resultName: 'HTTP 5xx 错误率',
    expression: 'a / b',
    rows: [{ ...formulaRows[0], groupAlgorithm: '' }, formulaRows[1]]
  }),
  '指标 a 缺少有效分组聚合方式'
);

assertValidationIncludes(
  validateMetricExpressionPayload({
    resultName: 'HTTP 5xx 错误率',
    expression: 'a / b',
    rows: [{ ...formulaRows[0], groupBy: [] }, formulaRows[1]]
  }),
  '指标 a 缺少有效分组维度'
);

assertValidationIncludes(
  validateMetricExpressionPayload({
    resultName: 'HTTP 5xx 错误率',
    expression: 'a b',
    rows: formulaRows
  }),
  '表达式语法不完整'
);

assertValidationIncludes(
  validateMetricExpressionPayload({
    resultName: 'HTTP 5xx 错误率',
    expression: 'a * 100',
    rows: formulaRows
  }),
  '表达式至少需要引用两个不同变量'
);

assertValidationIncludes(
  validateMetricExpressionPayload({
    resultName: 'HTTP 5xx 错误率',
    expression: 'a /',
    rows: formulaRows
  }),
  '表达式语法不完整'
);

assertValidationIncludes(
  validateMetricExpressionPayload({
    resultName: 'HTTP 5xx 错误率',
    expression: '(a / b',
    rows: formulaRows
  }),
  '表达式括号不匹配'
);

assert.deepEqual(
  validateMetricExpressionPayload({
    resultName: 'HTTP 5xx 错误率',
    expression: '',
    rows: formulaRows
  }),
  ['表达式不能为空']
);

assertValidationIncludes(
  validateMetricExpressionPayload({
    resultName: 'HTTP 5xx 错误率',
    expression: 'a / c',
    rows: formulaRows
  }),
  '表达式引用了不存在的变量：c'
);

assert.deepEqual(
  validateMetricExpressionPayload({
    resultName: 'HTTP 5xx 错误率',
    expression: 'a / b * 100',
    rows: formulaRows.slice(0, 1)
  }),
  ['表达式引用了不存在的变量：b']
);

assert.equal(shouldShowFormulaEditor('metric'), false);
assert.equal(shouldShowFormulaEditor('formula'), true);

assert.throws(
  () =>
    buildMetricExpressionQueryCondition({
      mode: 'formula',
      resultName: 'HTTP 5xx 错误率',
      expression: 'a / b',
      rows: [formulaRows[0]]
    }),
  (error) =>
    error instanceof Error &&
    error.message.includes('表达式引用了不存在的变量：b')
);

const formulaRowsAfterDeletingMiddle = [
  formulaRows[0],
  {
    ref: 'c',
    metricId: 3,
    filters: [{ name: 'service', method: '=', value: 'checkout' }],
    groupAlgorithm: 'sum',
    groupBy: ['instance_id']
  }
];

const formulaPayloadAfterDeletingMiddle = buildMetricExpressionQueryCondition({
  mode: 'formula',
  resultName: 'HTTP 5xx 错误率',
  expression: 'a / c',
  rows: formulaRowsAfterDeletingMiddle
});

assert.equal(formulaPayloadAfterDeletingMiddle.type, 'formula');
assert.deepEqual(
  formulaPayloadAfterDeletingMiddle.queries.map((query) => query.ref),
  ['a', 'c']
);
assert.equal(formulaPayloadAfterDeletingMiddle.expression, 'a / c');

const explicitMetricPayload = buildMetricExpressionQueryCondition({
  mode: 'metric',
  resultName: 'HTTP 5xx 错误率',
  expression: 'a / b',
  rows: singleRows
});

assert.deepEqual(explicitMetricPayload, {
  type: 'metric',
  metric_id: 10,
  filter: [
    { name: 'service', method: '=', value: 'checkout' },
    { logic: 'or', name: 'status', method: '=~', value: '5..' }
  ]
});

const restoredMetricState = toMetricExpressionStateFromQueryCondition(
  {
    type: 'metric',
    metric_id: 11,
    filter: [{ name: 'service', method: '=', value: 'checkout' }]
  },
  {
    groupAlgorithm: 'max',
    groupBy: ['instance_id', 'service']
  }
);

assert.deepEqual(restoredMetricState, {
  rows: [
    {
      ref: 'a',
      metricId: 11,
      filters: [{ name: 'service', method: '=', value: 'checkout' }],
      groupAlgorithm: 'max',
      groupBy: ['instance_id', 'service']
    }
  ],
  resultName: '',
  expression: 'a / b * 100'
});

const restoredFormulaState = toMetricExpressionStateFromQueryCondition({
  type: 'formula',
  result_name: 'HTTP 5xx 错误率',
  expression: 'a / b * 100',
  queries: [
    {
      ref: 'a',
      metric_id: 101,
      filter: [{ name: 'service', method: '=', value: 'checkout' }],
      group_algorithm: 'sum',
      group_by: ['instance_id', 'status']
    },
    {
      ref: 'b',
      metric_id: 102,
      filter: [{ logic: 'or', name: 'status', method: '=', value: '200' }],
      group_algorithm: 'sum',
      group_by: ['instance_id']
    }
  ]
});

assert.deepEqual(restoredFormulaState, {
  rows: [
    {
      ref: 'a',
      metricId: 101,
      filters: [{ name: 'service', method: '=', value: 'checkout' }],
      groupAlgorithm: 'sum',
      groupBy: ['instance_id', 'status']
    },
    {
      ref: 'b',
      metricId: 102,
      filters: [{ logic: 'or', name: 'status', method: '=', value: '200' }],
      groupAlgorithm: 'sum',
      groupBy: ['instance_id']
    }
  ],
  resultName: 'HTTP 5xx 错误率',
  expression: 'a / b * 100'
});

assertBuildThrows([], '至少需要配置一个指标');
assertBuildThrows(
  [{ ...singleRows[0], metricId: null }],
  '指标 a 必须选择有效指标'
);

console.log('monitor-policy-formula-payload-test passed');
