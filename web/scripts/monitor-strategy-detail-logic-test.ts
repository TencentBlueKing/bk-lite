import assert from 'node:assert/strict';

import {
  FORMULA_DEFAULT_RESULT_UNIT,
  buildMetricSelectOption,
  buildMetricUnitCascaderOptions,
  filterInvalidCalculationUnit,
  getCalculationUnitOnMetricRowsChange,
  getMetricThresholdEnumState,
  getReverseModeCalculationUnit,
  getThresholdUnitOnCalculationUnitChange,
  getThresholdUnitOptions,
  getValidThresholdUnitOptions,
  resolveFormulaResultUnit,
  resolveEffectiveCalculationUnit,
  resolveInitialMetricPluginId,
  resolveMetricDisplayUnit,
  resolvePreviewChartUnit,
  resolveThresholdUnit,
  restoreCalculationUnitState,
  shouldShowThresholdUnitSelector,
} from '../src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils';
import {
  resolveMetricExpressionUnits,
  type MetricExpressionMode,
} from '../src/app/monitor/(pages)/event/strategy/detail/formulaExpressionUtils';
import type { GroupedUnitList } from '../src/app/monitor/types';
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

assert.equal(resolveMetricDisplayUnit('percent', unitList), '%');
assert.equal(resolveMetricDisplayUnit('bytes', unitList), 'B');
assert.equal(resolveMetricDisplayUnit('none', unitList), '');
assert.equal(resolveMetricDisplayUnit('short', unitList), '');
assert.equal(
  resolveMetricDisplayUnit('[{"id":1,"name":"up"}]', unitList),
  ''
);
assert.equal(resolveMetricDisplayUnit('unknown-unit', unitList), '');
assert.equal(resolveMetricDisplayUnit('percent', []), '');

assert.equal(
  resolvePreviewChartUnit('kibibytes', 'kibibytes', 'bytes'),
  'kibibytes'
);
assert.equal(resolvePreviewChartUnit('', null, 'bytes'), 'bytes');
assert.equal(resolvePreviewChartUnit('', '', ''), null);

assert.deepEqual(
  buildMetricSelectOption(
    {
      id: 1,
      metric_group: 1,
      metric_object: 1,
      name: 'disk_usage',
      type: 'gauge',
      display_name: '磁盘使用率',
      dimensions: [],
      unit: 'percent',
    },
    unitList
  ),
  { label: '磁盘使用率（%）', value: 'disk_usage' }
);
assert.deepEqual(
  buildMetricSelectOption(
    {
      id: 2,
      metric_group: 1,
      metric_object: 1,
      name: 'disk_state',
      type: 'gauge',
      display_name: '磁盘状态',
      dimensions: [],
      unit: '[{"id":1,"name":"up"}]',
    },
    unitList
  ),
  { label: '磁盘状态', value: 'disk_state' }
);

assert.equal(
  resolveEffectiveCalculationUnit({
    isFormulaMode: true,
    unit: null,
    unitList: [],
  }),
  null
);
assert.equal(
  resolveEffectiveCalculationUnit({
    isFormulaMode: true,
    unit: null,
    unitList,
  }),
  FORMULA_DEFAULT_RESULT_UNIT
);
assert.equal(
  resolveEffectiveCalculationUnit({
    isFormulaMode: false,
    unit: 'unknown-unit',
    unitList,
  }),
  null
);
assert.equal(
  resolveEffectiveCalculationUnit({
    isFormulaMode: false,
    unit: 'percent',
    unitList,
  }),
  'percent'
);
assert.equal(restoreCalculationUnitState('kilobytes'), 'kilobytes');
assert.equal(restoreCalculationUnitState('unknown-unit'), 'unknown-unit');
assert.equal(restoreCalculationUnitState('none'), null);
const restoredFormulaUnit = restoreCalculationUnitState('kilobytes');
assert.equal(
  resolveEffectiveCalculationUnit({
    isFormulaMode: true,
    unit: restoredFormulaUnit,
    unitList: [],
  }),
  null
);
assert.equal(
  resolveEffectiveCalculationUnit({
    isFormulaMode: true,
    unit: restoredFormulaUnit,
    unitList,
  }),
  'kilobytes'
);

assert.deepEqual(
  resolveMetricExpressionUnits({
    queryType: 'metric',
    metricUnit: 'bytes',
    calculationUnit: 'megabytes',
    thresholdUnit: 'kilobytes',
  }),
  { metricUnit: 'bytes', calculationUnit: 'megabytes', thresholdUnit: 'kilobytes' }
);

assert.deepEqual(
  resolveMetricExpressionUnits({
    queryType: 'formula',
    metricUnit: 'bytes',
    calculationUnit: 'percent',
    thresholdUnit: 'percent',
  }),
  { metricUnit: '', calculationUnit: 'percent', thresholdUnit: 'percent' }
);

assert.deepEqual(
  resolveMetricExpressionUnits({
    queryType: 'metric',
    metricUnit: '[{"id":1,"name":"up"}]',
    calculationUnit: null,
    thresholdUnit: null,
  }),
  { metricUnit: '', calculationUnit: '', thresholdUnit: '' }
);

assert.equal(
  shouldShowThresholdUnitSelector({
    isFormulaMode: false,
    isEnumMetric: false,
  }),
  true
);
assert.equal(
  shouldShowThresholdUnitSelector({
    isFormulaMode: true,
    isEnumMetric: false,
  }),
  true
);
assert.equal(
  shouldShowThresholdUnitSelector({
    isFormulaMode: false,
    isEnumMetric: true,
  }),
  false
);

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

assert.deepEqual(
  getThresholdUnitOptions({
    unitList,
    metricUnit: 'percent',
    isEnumMetric: false,
  }).map((item) => item.unit_id),
  ['percent']
);
assert.deepEqual(
  getThresholdUnitOptions({
    unitList,
    metricUnit: 'bytes',
    isEnumMetric: false,
  }).map((item) => item.unit_id),
  ['bytes', 'kilobytes']
);
assert.deepEqual(
  getThresholdUnitOptions({
    unitList,
    metricUnit: 'watts',
    isEnumMetric: false,
  }).map((item) => item.unit_id),
  ['watts']
);
assert.deepEqual(
  getThresholdUnitOptions({
    unitList,
    metricUnit: 'bytes',
    isEnumMetric: true,
  }),
  []
);

assert.equal(
  resolveThresholdUnit({
    thresholdUnit: null,
    calculationUnit: 'bytes',
    unitList,
  }),
  'bytes'
);
assert.equal(
  resolveThresholdUnit({
    thresholdUnit: 'kilobytes',
    calculationUnit: 'bytes',
    unitList,
  }),
  'kilobytes'
);
assert.equal(
  getThresholdUnitOnCalculationUnitChange({
    thresholdUnit: 'milliseconds',
    calculationUnit: 'bytes',
    unitList,
  }),
  'bytes'
);
assert.equal(
  resolveThresholdUnit({
    thresholdUnit: 'historical-unit',
    calculationUnit: 'bytes',
    unitList: [],
  }),
  'historical-unit'
);
assert.deepEqual(
  getThresholdUnitOptions({
    unitList,
    metricUnit: 'none',
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

const groupedUnitList: GroupedUnitList[] = [
  {
    label: 'Data',
    children: [
      { unit_id: 'bytes', unit_name: '字节', display_unit: 'B', label: '字节', value: 'bytes', unit: 'B' },
      { unit_id: 'kibibytes', unit_name: '千字节', display_unit: 'KiB', label: '千字节', value: 'kibibytes', unit: 'KiB' },
    ],
  },
  {
    label: 'Time',
    children: [
      { unit_id: 'seconds', unit_name: '秒', display_unit: 's', label: '秒', value: 'seconds', unit: 's' },
    ],
  },
  {
    label: 'Base',
    children: [
      { unit_id: 'none', unit_name: '无单位', display_unit: '', label: '无单位', value: 'none', unit: '' },
      { unit_id: 'short', unit_name: '短数字', display_unit: '', label: '短数字', value: 'short', unit: '' },
    ],
  },
];

// buildMetricUnitCascaderOptions:过滤不能用于计算的 none/short 分组
const cascaderOptions = buildMetricUnitCascaderOptions(groupedUnitList);
assert.equal(cascaderOptions.length, 2);
assert.equal(cascaderOptions[0].value, 'Data');
assert.equal(cascaderOptions[0].children?.length, 2);
assert.equal(cascaderOptions[0].children?.[0].value, 'bytes');

// getThresholdUnitOptions(新签名:metricUnit 基准) — 同 system 过滤
const crossSystemUnitList: UnitListItem[] = [
  { unit_id: 'bytes', unit_name: '字节', display_unit: 'B', category: 'Data', system: 'bytes', description: '', is_standalone: false },
  { unit_id: 'kibibytes', unit_name: '千字节', display_unit: 'KiB', category: 'Data', system: 'bytes', description: '', is_standalone: false },
  { unit_id: 'mebibytes', unit_name: '兆字节', display_unit: 'MiB', category: 'Data', system: 'bytes', description: '', is_standalone: false },
  { unit_id: 'seconds', unit_name: '秒', display_unit: 's', category: 'Time', system: 'seconds', description: '', is_standalone: false },
  { unit_id: 'minutes', unit_name: '分钟', display_unit: 'min', category: 'Time', system: 'seconds', description: '', is_standalone: false },
  { unit_id: 'none', unit_name: '无单位', display_unit: '', category: 'Base', system: 'none', description: '', is_standalone: false },
];

const bytesOptions = getThresholdUnitOptions({ unitList: crossSystemUnitList, metricUnit: 'bytes', isEnumMetric: false });
assert.deepEqual(
  bytesOptions.map((u) => u.unit_id).sort(),
  ['bytes', 'kibibytes', 'mebibytes']
);

const secondsOptions = getThresholdUnitOptions({ unitList: crossSystemUnitList, metricUnit: 'seconds', isEnumMetric: false });
assert.deepEqual(
  secondsOptions.map((u) => u.unit_id),
  ['seconds', 'minutes']
);

// 枚举类型:返回空
const enumOptions = getThresholdUnitOptions({ unitList: crossSystemUnitList, metricUnit: 'bytes', isEnumMetric: true });
assert.equal(enumOptions.length, 0);

console.log('monitor-strategy-detail logic validation passed');
