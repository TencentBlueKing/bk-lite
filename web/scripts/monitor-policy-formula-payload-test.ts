import assert from 'node:assert/strict';

import {
  buildMetricDimensionVariable,
  buildMetricDimensionVariables,
} from '../src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils';
import {
  alignFollowerGroupBy,
  assignMetricRowRefs,
  buildMetricExpressionPreviewPayload,
  buildMetricExpressionQueryCondition,
  addMultiLevel,
  buildMultiConditionSentence,
  buildMultiQueryCondition,
  multiLevelRows,
  removeMultiLevel,
  setMultiLevelCell,
  validateMultiConditionRows,
  conditionLayersFromQueryType,
  createMetricRow,
  derivedQueryType,
  omitMultiMirrorFields,
  DEFAULT_FORMULA_RESULT_NAME,
  extractFormulaRefs,
  getMetricExpressionModeForRows,
  rowsAfterEnteringFormula,
  rowsAfterEnteringMulti,
  rowsAfterLeavingMulti,
  shouldShowConditionSourceSwitch,
  shouldShowFormulaEditor,
  shouldWarnQueryTypeChange,
  groupByAfterSelectingMetric,
  switchConditionSource,
  toMetricExpressionStateFromQueryCondition,
  toMetricRowsFromMetricCondition,
  validateMetricExpressionPayload
} from '../src/app/monitor/(pages)/event/strategy/detail/formulaExpressionUtils';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

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
assert.equal(getMetricExpressionModeForRows(singleRows), 'metric');

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
assert.equal(getMetricExpressionModeForRows(formulaRows), 'metric');
assert.equal(getMetricExpressionModeForRows(formulaRows, 'formula'), 'formula');
assert.equal(getMetricExpressionModeForRows(formulaRows.slice(0, 1)), 'metric');

const formulaPayload = buildMetricExpressionQueryCondition({
  mode: 'formula',
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

const defaultFormulaPayload = buildMetricExpressionQueryCondition({
  mode: 'formula',
  resultName: DEFAULT_FORMULA_RESULT_NAME,
  expression: 'a / b * 100',
  rows: formulaRows
});
assert.equal(defaultFormulaPayload.result_name, '计算指标');
assert.deepEqual(formulaPayload.queries[1].group_by, ['instance_id']);

const previewInstance = {
  instance_id: 'host-1',
  instance_name: 'host-1',
  instance_id_values: ['host.1', 'tenant(a)']
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
      instance_id_keys: ['node', 'tenant']
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
if (formulaPreviewPayload?.query_condition.type === 'formula') {
  assert.deepEqual(formulaPreviewPayload.query_condition.queries[0].filter, [
    { name: 'service', method: '=', value: 'checkout' },
    { logic: 'and', name: 'status', method: '=~', value: '5..' }
  ]);
  assert.deepEqual(formulaPreviewPayload.query_condition.queries[1].filter, [
    { name: 'service', method: '=', value: 'checkout' },
    { logic: 'or', name: 'status', method: '=', value: '200' }
  ]);
}
assert.equal(formulaPreviewPayload?.group_algorithm, 'sum');
assert.deepEqual(formulaPreviewPayload?.group_by, ['instance_id', 'status']);
assert.equal(formulaPreviewPayload?.metric_unit, '');
assert.equal(formulaPreviewPayload?.calculation_unit, 'percent');
assert.equal(formulaPreviewPayload?.compare_mode, 'absolute');
assert.equal(formulaPreviewPayload?.compare_value_kind, '');
assert.deepEqual(formulaPreviewPayload?.preview, {
  instance_id: 'host-1',
  instance_id_values: ['host.1', 'tenant(a)'],
  duration_points: 30
});

const reversedExpressionPayload = buildMetricExpressionQueryCondition({
  mode: 'formula',
  resultName: 'HTTP 5xx 错误率',
  expression: 'b / a * 100',
  rows: formulaRows
});

assert.deepEqual(
  validateMetricExpressionPayload({
    resultName: 'HTTP 5xx 错误率',
    expression: 'b / a * 100',
    rows: formulaRows
  }),
  []
);
assert.equal(reversedExpressionPayload.type, 'formula');
assert.equal(reversedExpressionPayload.expression, 'b / a * 100');
assert.equal(reversedExpressionPayload.queries[0].ref, 'a');
assert.deepEqual(reversedExpressionPayload.queries[0].group_by, [
  'instance_id',
  'status'
]);

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
assert.equal(metricPreviewPayload?.compare_mode, 'absolute');
assert.equal(metricPreviewPayload?.compare_value_kind, '');

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
      resultName: 'HTTP 5xx 错误率',
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
  (error) =>
    error instanceof Error && error.message.includes('指标不存在或尚未加载')
);

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

assertValidationIncludes(
  validateMetricExpressionPayload({
    resultName: 'HTTP 5xx 错误率',
    expression: 'a / b',
    rows: [{ ...formulaRows[0], groupBy: ['status'] }, formulaRows[1]]
  }),
  '指标 a 分组维度必须包含 instance_id'
);

assertValidationIncludes(
  validateMetricExpressionPayload({
    resultName: 'HTTP 5xx 错误率',
    expression: 'a / b',
    rows: [{ ...formulaRows[0], groupBy: ['instance_id', 'x) or vector(1'] }, formulaRows[1]]
  }),
  '指标 a 分组维度 x) or vector(1 包含非法字符'
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

const formulaRowsWithEmptyFilterValue = [
  {
    ...formulaRows[0],
    filters: [{ name: 'empty_label', method: '=', value: '' }]
  },
  formulaRows[1]
];
assert.deepEqual(
  validateMetricExpressionPayload({
    resultName: 'HTTP 5xx 错误率',
    expression: 'a / b',
    rows: formulaRowsWithEmptyFilterValue
  }),
  []
);

const formulaRowsWithLegacyFilters = [
  {
    ...formulaRows[0],
    filters: [
      { name: 'service', method: '=', value: 'checkout' },
      { name: 'status', method: '=~', value: '5..' }
    ]
  },
  formulaRows[1]
];
assert.deepEqual(
  validateMetricExpressionPayload({
    resultName: 'HTTP 5xx 错误率',
    expression: 'a / b',
    rows: formulaRowsWithLegacyFilters
  }),
  []
);

const formulaRowsWithStructuredFilterValue = [
  {
    ...formulaRows[0],
    filters: [{ name: 'service', method: '=', value: ['checkout'] as never }]
  },
  formulaRows[1]
];
assertValidationIncludes(
  validateMetricExpressionPayload({
    resultName: 'HTTP 5xx 错误率',
    expression: 'a / b',
    rows: formulaRowsWithStructuredFilterValue
  }),
  '指标 a 的条件 1 的值必须是字符串、数字或布尔值'
);

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

assert.equal(
  buildMetricDimensionVariable('cpu'),
  '${metric__cpu}'
);
assert.deepEqual(
  buildMetricDimensionVariables(['instance_id', 'cpu', 'cpu', '']),
  [
    { key: 'metric__instance_id', variable: '${metric__instance_id}', dimension: 'instance_id' },
    { key: 'metric__cpu', variable: '${metric__cpu}', dimension: 'cpu' },
  ]
);
assert.deepEqual(buildMetricDimensionVariables(null), []);

const offsetPreviewPayload = buildMetricExpressionPreviewPayload({
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
  algorithm: 'p95_over_time',
  groupAlgorithm: 'avg',
  groupBy: ['instance_id'],
  calculationUnit: 'percent',
  thresholdUnit: 'percent',
  compareMode: 'offset_1h',
  compareValueKind: 'percent'
});
assert.equal(offsetPreviewPayload?.compare_mode, 'offset_1h');
assert.equal(offsetPreviewPayload?.compare_value_kind, 'percent');
assert.equal(offsetPreviewPayload?.threshold_unit, 'percent');
assert.equal(offsetPreviewPayload?.algorithm, 'p95_over_time');
assert.deepEqual(offsetPreviewPayload?.count_predicate, {});
assert.equal(offsetPreviewPayload?.forecast_target, null);
assert.deepEqual(offsetPreviewPayload?.forecast_lookback, {});

const countIfPreviewPayload = buildMetricExpressionPreviewPayload({
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
  algorithm: 'count_if_over_time',
  groupAlgorithm: 'avg',
  groupBy: ['instance_id'],
  countPredicate: { method: '>', value: 80 }
});
assert.equal(countIfPreviewPayload?.algorithm, 'count_if_over_time');
assert.deepEqual(countIfPreviewPayload?.count_predicate, {
  method: '>',
  value: 80
});
assert.equal(countIfPreviewPayload?.compare_mode, 'absolute');

const timeleftPreviewPayload = buildMetricExpressionPreviewPayload({
  monitorObjId: 'linux',
  source: {
    type: 'instance',
    values: ['host-1']
  },
  metrics: [
    {
      id: 10,
      name: 'disk_used_percent',
      display_name: '磁盘使用率',
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
  compareMode: 'timeleft',
  compareValueKind: 'hours',
  forecastTarget: 90,
  forecastLookback: { type: 'hour', value: 4 }
});
assert.equal(timeleftPreviewPayload?.compare_mode, 'timeleft');
assert.equal(timeleftPreviewPayload?.compare_value_kind, 'hours');
assert.equal(timeleftPreviewPayload?.forecast_target, 90);
assert.equal(timeleftPreviewPayload?.forecast_target_unit, '');
assert.deepEqual(timeleftPreviewPayload?.forecast_lookback, {
  type: 'hour',
  value: 4
});
assert.deepEqual(timeleftPreviewPayload?.count_predicate, {});

const implicitMultiRows = buildMetricExpressionQueryCondition({
  resultName: 'CPU 与内存双高',
  expression: 'a / b',
  rows: formulaRows
});
assert.equal(implicitMultiRows.type, 'metric');

const multiRows = [
  {
    ref: 'a',
    metricId: 1,
    metricName: 'cpu_usage',
    filters: [],
    groupAlgorithm: 'avg',
    groupBy: ['instance_id', 'device'],
    algorithm: 'avg_over_time',
    metricUnit: 'percent',
    calculationUnit: 'percent',
    thresholdUnit: '%',
    role: 'level' as const,
    threshold: [
      { level: 'critical', method: '>', value: 90 },
      { level: 'warning', method: '>', value: 80 }
    ]
  },
  {
    ref: 'b',
    metricId: 2,
    metricName: 'mem_used',
    filters: [],
    groupAlgorithm: 'avg',
    groupBy: ['instance_id'],
    algorithm: 'avg_over_time',
    metricUnit: 'percent',
    calculationUnit: 'percent',
    thresholdUnit: '%',
    role: 'level' as const,
    threshold: [
      { level: 'warning', method: '>', value: 85 },
      { level: 'critical', method: '>', value: 95 }
    ]
  },
  {
    ref: 'c',
    metricId: 3,
    metricName: '系统运行时长',
    filters: [],
    groupAlgorithm: 'avg',
    groupBy: ['instance_id'],
    algorithm: 'avg_over_time',
    metricUnit: 's',
    calculationUnit: 's',
    thresholdUnit: 's',
    role: 'gate' as const,
    threshold: [{ method: '>', value: 600 }]
  }
];

const multiPayload = buildMultiQueryCondition({
  resultName: 'CPU 与内存双高',
  rows: multiRows
});
assert.equal(multiPayload.type, 'multi');
assert.equal(multiPayload.combinator, 'all');
assert.equal(multiPayload.queries[2].role, 'gate');
assert.equal(multiPayload.queries[2].threshold.length, 1);
assert.equal('level' in multiPayload.queries[2].threshold[0], false);
assert.equal(
  omitMultiMirrorFields({
    ...multiPayload,
    algorithm: 'avg_over_time',
    group_by: ['instance_id'],
    threshold: [{ level: 'warning', method: '>', value: 1 }],
    compare_mode: 'absolute',
    recovery_threshold: { method: '<', value: 1 },
    name: 'kept'
  }).algorithm,
  undefined
);

const restoredMulti = toMetricExpressionStateFromQueryCondition(multiPayload);
assert.equal(restoredMulti.rows[0].role, 'level');
assert.equal(restoredMulti.rows[2].role, 'gate');
assert.equal(restoredMulti.rows[0].threshold?.[1].level, 'warning');
assert.equal(restoredMulti.rows[2].thresholdUnit, 's');
assert.equal(
  getMetricExpressionModeForRows(restoredMulti.rows, multiPayload.type),
  'multi'
);

assert.equal(
  buildMultiConditionSentence(multiRows),
  '严重：cpu_usage > 90% 且 mem_used > 95%；警告：cpu_usage > 80% 且 mem_used > 85%；前置条件：系统运行时长 > 600s'
);

assert.throws(
  () => buildMultiQueryCondition({ resultName: '双高', rows: multiRows.slice(0, 1) }),
  (error) => error instanceof Error && error.message.includes('2 到 5')
);
assert.throws(
  () =>
    buildMultiQueryCondition({
      resultName: '双高',
      rows: multiRows.map((row) => ({ ...row, role: 'gate' as const, threshold: [{ method: '>', value: 1 }] }))
    }),
  (error) => error instanceof Error && error.message.includes('常规条件')
);
assert.throws(
  () =>
    buildMultiQueryCondition({
      resultName: '双高',
      rows: [
        multiRows[0],
        { ...multiRows[1], groupBy: ['instance_id', 'mount'] }
      ]
    }),
  (error) => error instanceof Error && error.message.includes('锚点外额外维度')
);

const multiPreview = buildMetricExpressionPreviewPayload({
  monitorObjId: 'linux',
  source: { type: 'instance', values: ['host-1'] },
  metrics: [
    { id: 1, name: 'cpu_usage', display_name: 'CPU', unit: 'percent', dimensions: [], instance_id_keys: ['instance_id'] },
    { id: 2, name: 'mem_used', display_name: '内存', unit: 'percent', dimensions: [], instance_id_keys: ['instance_id'] },
    { id: 3, name: '系统运行时长', display_name: '运行时长', unit: 's', dimensions: [], instance_id_keys: ['instance_id'] }
  ],
  mode: 'multi',
  resultName: 'CPU 与内存双高',
  expression: '',
  rows: multiRows,
  selectedInstance: previewInstance,
  period: 5,
  periodUnit: 'min',
  algorithm: null,
  groupAlgorithm: null,
  groupBy: []
});
assert.equal(multiPreview?.query_condition.type, 'multi');
assert.equal('algorithm' in (multiPreview || {}), false);
assert.equal('threshold' in (multiPreview || {}), false);

assert.equal(derivedQueryType('single', 'metric'), 'metric');
assert.equal(derivedQueryType('single', 'formula'), 'formula');
assert.equal(derivedQueryType('multi', 'metric'), 'multi');
assert.equal(derivedQueryType('multi', 'formula'), 'multi');
assert.deepEqual(conditionLayersFromQueryType(singlePayload.type), {
  count: 'single',
  source: 'metric'
});
assert.deepEqual(conditionLayersFromQueryType(formulaPayload.type), {
  count: 'single',
  source: 'formula'
});
assert.deepEqual(conditionLayersFromQueryType(multiPayload.type), {
  count: 'multi',
  source: 'metric'
});
assert.equal(shouldShowConditionSourceSwitch('single'), true);
assert.equal(shouldShowConditionSourceSwitch('multi'), true);
assert.equal(
  shouldWarnQueryTypeChange({
    isPersisted: true,
    savedType: 'metric',
    nextType: 'formula'
  }),
  true
);
assert.equal(
  shouldWarnQueryTypeChange({
    isPersisted: true,
    savedType: 'formula',
    nextType: 'metric'
  }),
  true
);
assert.equal(
  shouldWarnQueryTypeChange({
    isPersisted: true,
    savedType: 'metric',
    nextType: 'multi'
  }),
  true
);
assert.equal(
  shouldWarnQueryTypeChange({
    isPersisted: true,
    savedType: 'multi',
    nextType: 'metric'
  }),
  true
);
assert.equal(
  shouldWarnQueryTypeChange({
    isPersisted: true,
    savedType: 'multi',
    nextType: 'multi'
  }),
  false
);
assert.equal(
  shouldWarnQueryTypeChange({
    isPersisted: false,
    savedType: 'metric',
    nextType: 'formula'
  }),
  false
);

const nativeRow = createMetricRow(0, {
  metricId: 11,
  metricName: 'cpu_usage',
  groupBy: ['instance_id']
});
const enteredMulti = rowsAfterEnteringMulti([nativeRow], {
  algorithm: 'avg_over_time',
  groupBy: ['instance_id']
});
assert.equal(enteredMulti.length, 2);
assert.equal(enteredMulti[0].metricId, 11);
assert.equal(enteredMulti[0].threshold?.length, 3);
assert.equal(enteredMulti[1].ref, 'b');
assert.equal(enteredMulti[1].role, 'level');
const enteredFormula = rowsAfterEnteringFormula([
  nativeRow,
  createMetricRow(1, { metricId: 99, metricName: 'hidden' })
]);
assert.equal(enteredFormula.length, 2);
assert.equal(enteredFormula[0].ref, 'a');
assert.equal(enteredFormula[0].metricId, 11);
assert.equal(enteredFormula[1].ref, 'b');
assert.equal(enteredFormula[1].metricId, null);
assert.equal(
  buildMultiConditionSentence([
    { ...nativeRow, threshold: [{ level: 'warning', method: '>', value: null }] },
    { ...createMetricRow(1), role: 'gate', threshold: [{ method: '>', value: null }] }
  ]),
  '警告：cpu_usage 未设阈值；前置条件：b 未设阈值'
);
assert.match(
  buildMultiConditionSentence([
    {
      ...nativeRow,
      ref: 'a',
      source: 'formula',
      resultName: '',
      operands: [{ ...nativeRow, ref: 'a1', metricLabel: 'CPU使用率' }]
    }
  ]),
  /^CPU使用率 未设阈值/
);
assert.match(
  buildMultiConditionSentence([
    {
      ...nativeRow,
      ref: 'a',
      source: 'formula',
      resultName: '',
      operands: [createMetricRow(0, { ref: 'a1' })]
    }
  ]),
  /^未命名结果 未设阈值/
);
const keptOperands = rowsAfterEnteringMulti(
  [
    createMetricRow(0, { metricId: 1, groupBy: ['instance_id', 'status'] }),
    createMetricRow(1, { metricId: 2, groupBy: ['instance_id'] })
  ],
  { algorithm: 'max_over_time', groupBy: ['instance_id'] }
);
assert.equal(keptOperands.length, 2);
assert.equal(keptOperands[0].algorithm, 'max_over_time');
assert.deepEqual(keptOperands[1].groupBy, ['instance_id']);
assert.equal(rowsAfterLeavingMulti(keptOperands).length, 1);
assert.equal(rowsAfterLeavingMulti(keptOperands)[0].metricId, 1);
assert.deepEqual(
  alignFollowerGroupBy(
    [
      { ...keptOperands[0], groupBy: ['instance_id'] },
      { ...keptOperands[1], groupBy: ['instance_id', 'mount'] }
    ],
    ['instance_id']
  )[1].groupBy,
  ['instance_id']
);

const zhEvents = JSON.parse(
  readFileSync(resolve('src/app/monitor/locales/zh.json'), 'utf8')
).monitor.events;
const enEvents = JSON.parse(
  readFileSync(resolve('src/app/monitor/locales/en.json'), 'utf8')
).monitor.events;
for (const key of [
  'conditionCountSingle',
  'conditionCountSingleHint',
  'conditionCountMulti',
  'conditionCountMultiHint',
  'conditionSourceMetric',
  'conditionSourceFormula',
  'multiAlignHint',
  'multiAddLevel',
  'multiRemoveLevel'
]) {
  assert.equal(typeof zhEvents[key], 'string', key);
  assert.equal(typeof enEvents[key], 'string', key);
  assert.notEqual(zhEvents[key], '');
  assert.notEqual(enEvents[key], '');
}
assert.equal(zhEvents.conditionCountSingle, '单条件');
assert.equal(zhEvents.conditionCountMulti, '多条件');
assert.equal(zhEvents.conditionSourceMetric, '原生指标');
assert.equal(zhEvents.conditionSourceFormula, '计算指标');
assert.equal(zhEvents.multiAlignHint, '其余条件按第一条的实例对齐');
assert.equal(zhEvents.multiAddLevel, '添加级别');
assert.equal(enEvents.multiAddLevel, 'Add level');
assert.equal(zhEvents.multiRemoveLevel, '删除级别');
assert.equal(enEvents.multiRemoveLevel, 'Remove level');
assert.equal(zhEvents.multiAlignHint.includes('锚点'), false);
assert.equal(multiPayload.queries[0].source, undefined);

const formulaRow = switchConditionSource(
  createMetricRow(0, {
    ref: 'a',
    metricId: 11,
    metricName: 'error_total',
    metricLabel: '错误数',
    groupAlgorithm: 'sum',
    groupBy: ['instance_id'],
    algorithm: 'avg_over_time',
    role: 'level',
    calculationUnit: 'percent',
    thresholdUnit: 'percent',
    threshold: [
      { level: 'warning', method: '>', value: 5 },
      { level: 'error', method: '>', value: 10 },
      { level: 'critical', method: '>', value: 20 }
    ]
  }),
  'formula'
);
formulaRow.resultName = '错误率';
if (formulaRow.operands?.[0] && formulaRow.operands?.[1]) {
  formulaRow.operands[0].groupBy = ['instance_id', 'device'];
  formulaRow.operands[1].metricId = 12;
  formulaRow.operands[1].metricName = 'request_total';
  formulaRow.operands[1].groupBy = ['instance_id'];
  formulaRow.groupBy = ['instance_id', 'device'];
}
const formulaMulti = buildMultiQueryCondition({
  resultName: '错误率与请求数',
  rows: [formulaRow, multiRows[2]]
});
assert.equal(formulaMulti.type, 'multi');
assert.equal(formulaMulti.queries[0].source, 'formula');
assert.equal(formulaMulti.queries[0].metric_name, '错误率');
assert.equal(formulaMulti.queries[0].expression, 'a1 / a2 * 100');
assert.equal(formulaMulti.queries[0].metric_unit, '');
assert.equal('group_algorithm' in formulaMulti.queries[0], false);
assert.deepEqual(formulaMulti.queries[0].group_by, ['instance_id', 'device']);
assert.deepEqual(formulaMulti.queries[0].operands?.[0].group_by, ['instance_id', 'device']);
assert.deepEqual(formulaMulti.queries[0].operands?.[1].group_by, ['instance_id']);
assert.equal(formulaMulti.queries[0].operands?.[1].metric_id, 12);
assert.equal(formulaMulti.queries[1].source, undefined);
assert.equal(
  derivedQueryType('multi', formulaRow.source || 'metric'),
  'multi'
);
assert.equal(
  shouldWarnQueryTypeChange({
    isPersisted: true,
    savedType: 'multi',
    nextType: derivedQueryType('multi', 'formula')
  }),
  false
);

const echoedFormula = toMetricExpressionStateFromQueryCondition(formulaMulti);
assert.equal(echoedFormula.rows[0].source, 'formula');
assert.equal(echoedFormula.rows[0].resultName, '错误率');
assert.equal(echoedFormula.rows[0].expression, 'a1 / a2 * 100');
assert.equal(echoedFormula.rows[0].operands?.[0].metricId, 11);
assert.equal(echoedFormula.rows[1].source, undefined);
assert.equal(
  buildMultiConditionSentence([
    { ...formulaRow, resultName: '错误率' },
    multiRows[2]
  ]).includes('错误率'),
  true
);
assert.throws(
  () =>
    buildMultiQueryCondition({
      resultName: '错误率与请求数',
      rows: [{ ...formulaRow, algorithm: 'rate' }, multiRows[2]]
    }),
  /逐序列/
);
assert.throws(
  () =>
    buildMultiQueryCondition({
      resultName: '错误率与请求数',
      rows: [
        {
          ...formulaRow,
          operands: (formulaRow.operands || []).map((operand, index) =>
            index === 1 ? { ...operand, groupBy: ['instance_id', 'mount'] } : operand
          )
        },
        multiRows[2]
      ]
    }),
  /锚点外额外维度/
);

const secondFormula = switchConditionSource(
  createMetricRow(1, {
    ref: 'b',
    metricId: 3,
    metricName: 'cpu_iowait',
    groupAlgorithm: 'avg',
    groupBy: ['instance_id'],
    algorithm: 'avg_over_time',
    role: 'level',
    calculationUnit: 'percent',
    thresholdUnit: 'percent',
    threshold: [
      { level: 'critical', method: '>', value: 12 },
      { level: 'error', method: '>', value: 8 },
      { level: 'warning', method: '>', value: 4 }
    ]
  }),
  'formula'
);
secondFormula.resultName = '等待比';
if (secondFormula.operands?.[1]) {
  secondFormula.operands[1].metricId = 4;
  secondFormula.operands[1].metricName = 'cpu_core';
}
const bothFormula = buildMultiQueryCondition({
  resultName: '两个比值',
  rows: [formulaRow, secondFormula]
});
assert.equal(bothFormula.queries.length, 2);
assert.equal(bothFormula.queries.every((query) => query.source === 'formula'), true);
assert.equal(bothFormula.queries[0].metric_name, '错误率');
assert.equal(bothFormula.queries[1].metric_name, '等待比');
assert.deepEqual(
  groupByAfterSelectingMetric(['instance_id', 'cpu'], ['instance_id'], true),
  ['instance_id']
);
assert.deepEqual(
  groupByAfterSelectingMetric(['cpu'], ['instance_id'], true),
  ['instance_id']
);
assert.deepEqual(
  groupByAfterSelectingMetric(['instance_id', 'cpu'], ['instance_id'], false),
  ['instance_id', 'cpu']
);

const levelGridA = createMetricRow(0, {
  metricId: 1,
  metricName: 'cpu_usage',
  algorithm: 'avg_over_time',
  role: 'level',
  threshold: [
    { level: 'warning', method: '>', value: 3 },
    { level: 'critical', method: '>', value: 20 }
  ]
});
const levelGridB = createMetricRow(1, {
  metricId: 2,
  metricName: 'mem_used',
  algorithm: 'avg_over_time',
  role: 'level',
  threshold: [{ level: 'error', method: '<', value: 12 }]
});
const levelGridGate = createMetricRow(2, {
  metricId: 3,
  metricName: 'request_total',
  algorithm: 'avg_over_time',
  role: 'gate',
  threshold: [{ method: '>', value: 100 }]
});
assert.deepEqual(
  multiLevelRows([levelGridA, levelGridB, levelGridGate]),
  ['critical', 'error', 'warning']
);
assert.deepEqual(
  multiLevelRows([
    levelGridA,
    createMetricRow(1, {
      role: 'gate',
      threshold: [{ level: 'error', method: '>', value: 1 }]
    })
  ]),
  ['critical', 'warning']
);

const levelGridBefore = structuredClone(levelGridA);
const patchedLevelCell = setMultiLevelCell(
  [levelGridA, levelGridB, levelGridGate],
  'a',
  'warning',
  { value: 9 }
);
assert.equal(patchedLevelCell[0].threshold?.find((item) => item.level === 'warning')?.value, 9);
assert.equal(patchedLevelCell[0].threshold?.find((item) => item.level === 'warning')?.method, '>');
assert.equal(patchedLevelCell[0].threshold?.find((item) => item.level === 'critical')?.value, 20);
assert.equal(patchedLevelCell[1], levelGridB);
assert.equal(patchedLevelCell[2], levelGridGate);
assert.deepEqual(levelGridA, levelGridBefore);
const createdLevelCell = setMultiLevelCell([levelGridB], 'b', 'critical', { method: '>=' });
assert.deepEqual(
  createdLevelCell[0].threshold?.find((item) => item.level === 'critical'),
  { level: 'critical', method: '>=', value: null }
);
assert.equal(createdLevelCell[0].threshold?.find((item) => item.level === 'error')?.value, 12);
assert.equal(levelGridB.threshold?.length, 1);

const addedLevel = addMultiLevel([levelGridB, levelGridGate]);
assert.deepEqual(
  addedLevel[0].threshold?.map((item) => item.level),
  ['error', 'critical']
);
assert.equal(addedLevel[0].threshold?.[1].method, '>');
assert.equal(addedLevel[0].threshold?.[1].value, null);
assert.equal(addedLevel[1], levelGridGate);
assert.deepEqual(levelGridGate.threshold, [{ method: '>', value: 100 }]);
const fullLevels = createMetricRow(0, {
  role: 'level',
  threshold: [
    { level: 'critical', method: '>', value: 1 },
    { level: 'error', method: '>', value: 2 },
    { level: 'warning', method: '>', value: 3 }
  ]
});
const fullLevelInput = [fullLevels, levelGridGate];
const addedWhenFull = addMultiLevel(fullLevelInput);
assert.notEqual(addedWhenFull, fullLevelInput);
assert.equal(addedWhenFull[0], fullLevels);
assert.equal(addedWhenFull[0].threshold?.length, 3);
assert.equal(addedWhenFull[1], levelGridGate);

const removedLevel = removeMultiLevel([levelGridA, levelGridB, levelGridGate], 'warning');
assert.deepEqual(
  removedLevel[0].threshold?.map((item) => item.level),
  ['critical']
);
assert.equal(removedLevel[1], levelGridB);
assert.equal(removedLevel[2], levelGridGate);
assert.equal(levelGridA.threshold?.some((item) => item.level === 'warning'), true);

const missingErrorLevel = validateMultiConditionRows({
  resultName: '双条件',
  rows: [
    createMetricRow(0, {
      metricId: 1,
      algorithm: 'avg_over_time',
      role: 'level',
      threshold: [
        { level: 'error', method: '>', value: 10 },
        { level: 'warning', method: '>', value: 1 }
      ]
    }),
    createMetricRow(1, {
      metricId: 2,
      algorithm: 'avg_over_time',
      role: 'level',
      threshold: [{ level: 'warning', method: '>', value: 2 }]
    })
  ]
});
assertValidationIncludes(missingErrorLevel, '错误级别里条件 b 的阈值不完整');
assert.equal(missingErrorLevel.includes('条件 b 至少需要一条阈值'), false);

const noLevelRows = validateMultiConditionRows({
  resultName: '双条件',
  rows: [
    createMetricRow(0, {
      metricId: 1,
      algorithm: 'avg_over_time',
      role: 'level',
      threshold: []
    }),
    createMetricRow(1, {
      metricId: 2,
      algorithm: 'avg_over_time',
      role: 'level',
      threshold: []
    })
  ]
});
assertValidationIncludes(noLevelRows, '多指标条件至少需要一个级别');

const duplicateLevel = validateMultiConditionRows({
  resultName: '双条件',
  rows: [
    createMetricRow(0, {
      metricId: 1,
      algorithm: 'avg_over_time',
      role: 'level',
      threshold: [
        { level: 'warning', method: '>', value: 1 },
        { level: 'warning', method: '>', value: 2 }
      ]
    }),
    createMetricRow(1, {
      metricId: 2,
      algorithm: 'avg_over_time',
      role: 'level',
      threshold: [{ level: 'warning', method: '>', value: 3 }]
    })
  ]
});
assertValidationIncludes(duplicateLevel, '条件 a 的级别不能重复');

const incompleteGate = validateMultiConditionRows({
  resultName: '双条件',
  rows: [
    createMetricRow(0, {
      metricId: 1,
      algorithm: 'avg_over_time',
      role: 'level',
      threshold: [{ level: 'warning', method: '>', value: 1 }]
    }),
    createMetricRow(1, {
      metricId: 2,
      algorithm: 'avg_over_time',
      role: 'gate',
      threshold: [{ method: '>', value: null }]
    })
  ]
});
assertValidationIncludes(incompleteGate, '前置条件 b 的阈值不完整');

console.log('monitor-policy-formula-payload-test passed');
