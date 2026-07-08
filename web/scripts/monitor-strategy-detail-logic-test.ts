import assert from 'node:assert/strict';

import {
  FORMULA_DEFAULT_RESULT_UNIT,
  filterInvalidCalculationUnit,
  getCalculationUnitOnMetricRowsChange,
  getMetricThresholdEnumState,
  getReverseModeCalculationUnit,
  getThresholdUnitFilterBase,
  getThresholdUnitOptions,
  getValidThresholdUnitOptions,
  resolveFormulaResultUnit,
  resolveInitialMetricPluginId,
} from '../src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils';
import type { MetricExpressionMode } from '../src/app/monitor/(pages)/event/strategy/detail/formulaExpressionUtils';
import { UnitListItem } from '../src/app/monitor/types';

const plugins = [
  { label: '主机（Telegraf）', value: 1 },
  { label: 'Windows WMI', value: 2 },
  { label: '主机远程采集（Telegraf）', value: 3 },
];

assert.equal(resolveInitialMetricPluginId({
  type: 'edit',
  pluginList: plugins,
  policyCollectType: 3,
}), 3);

assert.equal(resolveInitialMetricPluginId({
  type: 'edit',
  pluginList: plugins,
  policyCollectType: '3',
}), 3);

assert.equal(resolveInitialMetricPluginId({
  type: 'add',
  pluginList: plugins,
  policyCollectType: 3,
}), 1);

assert.equal(resolveInitialMetricPluginId({
  type: 'edit',
  pluginList: plugins,
  policyCollectType: 99,
}), 1);

const unitList: UnitListItem[] = [
  {
    unit_id: 'none',
    unit_name: '无单位',
    display_unit: '',
    category: 'Base',
    system: 'none',
    description: '',
    is_standalone: false,
  },
  {
    unit_id: 'short',
    unit_name: '短数字',
    display_unit: '',
    category: 'Base',
    system: 'short',
    description: '',
    is_standalone: false,
  },
  {
    unit_id: 'percent',
    unit_name: '百分比',
    display_unit: '%',
    category: 'Base',
    system: 'percent',
    description: '',
    is_standalone: false,
  },
  {
    unit_id: 'bytes',
    unit_name: '字节',
    display_unit: 'B',
    category: 'Data',
    system: 'bytes',
    description: '',
    is_standalone: false,
  },
  {
    unit_id: 'kilobytes',
    unit_name: '千字节',
    display_unit: 'KB',
    category: 'Data',
    system: 'bytes',
    description: '',
    is_standalone: false,
  },
  {
    unit_id: 'milliseconds',
    unit_name: '毫秒',
    display_unit: 'ms',
    category: 'Time',
    system: 'time',
    description: '',
    is_standalone: false,
  },
  {
    unit_id: 'watts',
    unit_name: '瓦特',
    display_unit: 'W',
    category: 'Power',
    system: null as unknown as string,
    description: '',
    is_standalone: true,
  },
];

assert.equal(FORMULA_DEFAULT_RESULT_UNIT, 'percent');
assert.deepEqual(
  getValidThresholdUnitOptions(unitList).map((item) => item.unit_id),
  ['percent', 'bytes', 'kilobytes', 'milliseconds', 'watts']
);

assert.equal(resolveFormulaResultUnit(null, unitList), 'percent');
assert.equal(resolveFormulaResultUnit('', unitList), 'percent');
assert.equal(resolveFormulaResultUnit('none', unitList), 'percent');
assert.equal(resolveFormulaResultUnit('short', unitList), 'percent');
assert.equal(resolveFormulaResultUnit('bytes', unitList), 'bytes');
assert.equal(resolveFormulaResultUnit('unknown-unit', unitList), 'percent');
assert.equal(
  getCalculationUnitOnMetricRowsChange({
    previousMode: 'metric' as MetricExpressionMode,
    nextMode: 'formula' as MetricExpressionMode,
    currentCalculationUnit: 'bytes',
    unitList,
  }),
  'percent'
);
assert.equal(
  getCalculationUnitOnMetricRowsChange({
    previousMode: 'formula' as MetricExpressionMode,
    nextMode: 'formula' as MetricExpressionMode,
    currentCalculationUnit: 'bytes',
    unitList,
  }),
  'bytes'
);
// 反向: 'formula' → 'metric' 时 helper 保持 currentCalculationUnit(对称 retract 由 Task 2 接管)
assert.equal(
  getCalculationUnitOnMetricRowsChange({
    previousMode: 'formula' as MetricExpressionMode,
    nextMode: 'metric' as MetricExpressionMode,
    currentCalculationUnit: 'percent',
    unitList,
  }),
  'percent'
);

// unitList 为空:resolveFormulaResultUnit 不再硬塞 percent
assert.equal(resolveFormulaResultUnit(null, []), null);
assert.equal(resolveFormulaResultUnit('bytes', []), null);

// unitList 为空:首次进入 formula 不硬塞 percent
assert.equal(
  getCalculationUnitOnMetricRowsChange({
    previousMode: 'metric' as MetricExpressionMode,
    nextMode: 'formula' as MetricExpressionMode,
    currentCalculationUnit: 'bytes',
    unitList: [],
  }),
  null
);
// unitList 为空:在 formula 模式继续调整,保留用户已选值,不再二次覆盖
assert.equal(
  getCalculationUnitOnMetricRowsChange({
    previousMode: 'formula' as MetricExpressionMode,
    nextMode: 'formula' as MetricExpressionMode,
    currentCalculationUnit: 'bytes',
    unitList: [],
  }),
  'bytes'
);

assert.deepEqual(
  getMetricThresholdEnumState({
    isFormulaMode: true,
    metricUnit: '[{\"id\":1,\"name\":\"up\"}]',
  }),
  {
    isEnumMetric: false,
    enumOptions: [],
  }
);
assert.deepEqual(
  getMetricThresholdEnumState({
    isFormulaMode: false,
    metricUnit: '[{\"id\":1,\"name\":\"up\"}]',
  }),
  {
    isEnumMetric: true,
    enumOptions: [{ id: 1, name: 'up' }],
  }
);

assert.equal(
  getThresholdUnitFilterBase({
    isFormulaMode: true,
    formulaResultUnit: 'percent',
    selectedMetricUnit: 'bytes',
  }),
  'percent'
);
assert.equal(
  getThresholdUnitFilterBase({
    isFormulaMode: false,
    formulaResultUnit: 'percent',
    selectedMetricUnit: 'bytes',
  }),
  'bytes'
);
assert.equal(
  getThresholdUnitFilterBase({
    isFormulaMode: false,
    formulaResultUnit: 'percent',
    selectedMetricUnit: null,
  }),
  null
);

assert.deepEqual(
  getThresholdUnitOptions({
    unitList,
    unitFilterBase: 'percent',
    isEnumMetric: false,
  }).map((item) => item.unit_id),
  ['percent']
);
assert.deepEqual(
  getThresholdUnitOptions({
    unitList,
    unitFilterBase: 'bytes',
    isEnumMetric: false,
  }).map((item) => item.unit_id),
  ['bytes', 'kilobytes']
);
assert.deepEqual(
  getThresholdUnitOptions({
    unitList,
    unitFilterBase: 'watts',
    isEnumMetric: false,
  }).map((item) => item.unit_id),
  ['watts']
);
assert.deepEqual(
  getThresholdUnitOptions({
    unitList,
    unitFilterBase: 'bytes',
    isEnumMetric: true,
  }),
  []
);
assert.deepEqual(
  getThresholdUnitOptions({
    unitList,
    unitFilterBase: 'none',
    isEnumMetric: false,
  }),
  []
);

// filterInvalidCalculationUnit: 现有 page.tsx 逻辑上提
assert.equal(filterInvalidCalculationUnit(null), null);
assert.equal(filterInvalidCalculationUnit(undefined), null);
assert.equal(filterInvalidCalculationUnit(''), null);
assert.equal(filterInvalidCalculationUnit('none'), null);
assert.equal(filterInvalidCalculationUnit('short'), null);
assert.equal(filterInvalidCalculationUnit('bytes'), 'bytes');
// JSON 数组形式(枚举指标单位)不当作 calculationUnit
assert.equal(
  filterInvalidCalculationUnit('[{"id":1,"name":"up"}]'),
  null
);

// getReverseModeCalculationUnit
assert.equal(
  getReverseModeCalculationUnit({
    previousMode: 'formula' as MetricExpressionMode,
    nextMode: 'metric' as MetricExpressionMode,
    primaryMetricUnit: 'bytes',
  }),
  'bytes'
);
assert.equal(
  getReverseModeCalculationUnit({
    previousMode: 'formula' as MetricExpressionMode,
    nextMode: 'metric' as MetricExpressionMode,
    primaryMetricUnit: null,
  }),
  null
);
// 不是 retract 路径(继续在 formula 或单指标)返回 undefined,调用方不修改 calculationUnit
assert.equal(
  getReverseModeCalculationUnit({
    previousMode: 'formula' as MetricExpressionMode,
    nextMode: 'formula' as MetricExpressionMode,
    primaryMetricUnit: 'bytes',
  }),
  undefined
);
assert.equal(
  getReverseModeCalculationUnit({
    previousMode: 'metric' as MetricExpressionMode,
    nextMode: 'metric' as MetricExpressionMode,
    primaryMetricUnit: 'bytes',
  }),
  undefined
);

// getMetricThresholdEnumState 边界:畸形 JSON 全部兜底成空数组
assert.deepEqual(
  getMetricThresholdEnumState({ isFormulaMode: false, metricUnit: null }),
  { isEnumMetric: false, enumOptions: [] }
);
assert.deepEqual(
  getMetricThresholdEnumState({ isFormulaMode: false, metricUnit: '' }),
  { isEnumMetric: false, enumOptions: [] }
);
assert.deepEqual(
  getMetricThresholdEnumState({ isFormulaMode: false, metricUnit: 'not-json' }),
  { isEnumMetric: false, enumOptions: [] }
);
assert.deepEqual(
  getMetricThresholdEnumState({ isFormulaMode: false, metricUnit: '{"foo":1}' }),
  { isEnumMetric: false, enumOptions: [] }
);
assert.deepEqual(
  getMetricThresholdEnumState({
    isFormulaMode: false,
    metricUnit: '[{"foo":1}]'
  }),
  { isEnumMetric: false, enumOptions: [] }
);
// id 是字符串,正常化为 number
assert.deepEqual(
  getMetricThresholdEnumState({
    isFormulaMode: false,
    metricUnit: '[{"id":"1","name":"up"}]'
  }),
  { isEnumMetric: true, enumOptions: [{ id: 1, name: 'up' }] }
);
// 缺 name 的项被过滤
assert.deepEqual(
  getMetricThresholdEnumState({
    isFormulaMode: false,
    metricUnit: '[{"id":1,"name":"up"},{"id":2}]'
  }),
  { isEnumMetric: true, enumOptions: [{ id: 1, name: 'up' }] }
);

console.log('monitor-strategy-detail logic validation passed');
