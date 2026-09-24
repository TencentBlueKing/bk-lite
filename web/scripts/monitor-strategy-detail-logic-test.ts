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
  insertAlertNameVariableAtCursor,
  isVacantThresholdUnit,
  pruneNoticeUsers,
  collectMetricQueryTexts,
  queriesContainRateFunction,
  rateAlgorithmConflictsWithQuery,
  mapQuantityToRateUnit,
  resolveFunctionDelayMinutes,
  scheduleValueToMinutes,
  resolveFormulaResultUnit,
  resolveEffectiveCalculationUnit,
  resolveInitialMetricPluginId,
  resolveEditFormCollectType,
  shouldHydrateMetricOnEdit,
  extractMetricIdsFromQueryCondition,
  resolvePluginIdFromMetricPlugins,
  resolveMetricDisplayUnit,
  resolvePreviewChartUnit,
  resolveThresholdUnit,
  resolveUnitOnMetricSelect,
  restoreCalculationUnitState,
  shouldRequireNoticeUsers,
  shouldShowThresholdUnitSelector,
  getEnabledCompareModes,
  getCompareModeSelectOptions,
  buildPolicyRestatement,
  coerceThresholdsForCompareMode,
  coerceRecoveryForThresholds,
  groupAlgorithmOptions,
  formatAlgorithmDisplayLabel,
  getAlgorithmShortName,
  shouldAnnotatePerSecond,
  formatUnitLabelWithRateSuffix,
  resolveCompareFieldsForSave,
  compareOffsetHoursConflict,
  compareSpanConflict,
  compareSpanIssue,
  compareResultFamily,
  clearThresholdNumbers,
  partitionTimeleftPreviewSeries,
  formatDryRunDimensionLabel,
  compareBaselineFamily,
  resolveLoadedCompareOffset,
  resolveForecastTargetUnit,
  resolveRecoveryThresholdForSave,
  resolveNoDataPeriodsForSave,
  resolvePolicyResultUnit,
  resolveThresholdUnitBase,
  shouldDrawPreviewThreshold,
  formatDryRunHitCountCopy,
  resolveDryRunReason,
  formatDryRunNumber,
  formatDryRunThreshold,
  DRY_RUN_VERDICT_I18N,
  completedThresholds,
  isFilledThresholdValue,
  timeleftRequiresLowSideThresholds,
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
}), undefined);
assert.equal(resolveInitialMetricPluginId({
  type: 'edit',
  pluginList: plugins,
  policyCollectType: 99,
  metricResolvedPluginId: 2,
}), 2);
assert.equal(resolveInitialMetricPluginId({
  type: 'edit',
  pluginList: plugins,
  policyCollectType: '',
  policyDetailReady: true,
  metricResolvedPluginId: 2,
}), 2);
assert.deepEqual(
  extractMetricIdsFromQueryCondition({ type: 'metric', metric_id: 17 }),
  [17]
);
assert.deepEqual(
  extractMetricIdsFromQueryCondition({
    type: 'formula',
    queries: [{ metric_id: 17 }, { metric_id: 17 }, { metric_id: 8 }],
  }),
  [17, 8]
);
assert.equal(
  resolvePluginIdFromMetricPlugins(plugins, [
    { monitor_plugin: 2 },
    { monitor_plugin: 2 },
  ]),
  2
);
assert.equal(
  resolvePluginIdFromMetricPlugins(plugins, [
    { monitor_plugin: 1 },
    { monitor_plugin: 2 },
  ]),
  undefined
);
assert.equal(resolveEditFormCollectType(99, plugins), '');
assert.equal(resolveEditFormCollectType(99, plugins, 3), 3);
assert.equal(resolveEditFormCollectType('', plugins, 2), 2);

assert.equal(resolveInitialMetricPluginId({
  type: 'edit',
  pluginList: plugins,
  policyCollectType: '',
}), undefined);
assert.equal(resolveInitialMetricPluginId({
  type: 'edit',
  pluginList: [{ label: 'BifrostPull', value: 452 }],
  policyCollectType: '',
}), undefined);
assert.equal(resolveInitialMetricPluginId({
  type: 'edit',
  pluginList: [{ label: 'BifrostPull', value: 452 }],
  policyCollectType: '',
  policyDetailReady: true,
}), 452);
assert.equal(resolveInitialMetricPluginId({
  type: 'edit',
  pluginList: plugins,
  policyCollectType: '',
  policyDetailReady: true,
}), undefined);
assert.equal(resolveInitialMetricPluginId({
  type: 'edit',
  pluginList: [{ label: 'BifrostPull', value: 452 }],
  policyCollectType: null,
  policyDetailReady: true,
}), 452);

assert.equal(resolveEditFormCollectType('', [{ label: 'BifrostPull', value: 452 }]), 452);
assert.equal(resolveEditFormCollectType('452', plugins), 452);
assert.equal(resolveEditFormCollectType('', plugins), '');

assert.equal(shouldHydrateMetricOnEdit({
  type: 'add',
  initMetricCount: 0,
  policyId: 17,
}), false);
assert.equal(shouldHydrateMetricOnEdit({
  type: 'edit',
  initMetricCount: 0,
  policyId: undefined,
}), false);
assert.equal(shouldHydrateMetricOnEdit({
  type: 'edit',
  initMetricCount: 0,
  policyId: 17,
}), true);
assert.equal(shouldHydrateMetricOnEdit({
  type: 'edit',
  initMetricCount: 3,
  policyId: undefined,
}), true);

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

// none/short：保存时三字段均为空，避免后端 get_effective_units 提升后校验失败
assert.deepEqual(
  resolveMetricExpressionUnits({
    queryType: 'metric',
    metricUnit: 'none',
    calculationUnit: null,
    thresholdUnit: null,
  }),
  { metricUnit: '', calculationUnit: '', thresholdUnit: '' }
);
assert.deepEqual(
  resolveMetricExpressionUnits({
    queryType: 'metric',
    metricUnit: 'short',
    calculationUnit: null,
    thresholdUnit: null,
  }),
  { metricUnit: '', calculationUnit: '', thresholdUnit: '' }
);

assert.equal(isVacantThresholdUnit(null), true);
assert.equal(isVacantThresholdUnit(undefined), true);
assert.equal(isVacantThresholdUnit(''), true);
assert.equal(isVacantThresholdUnit('none'), true);
assert.equal(isVacantThresholdUnit('short'), true);
assert.equal(isVacantThresholdUnit('bytes'), false);
assert.equal(isVacantThresholdUnit('counts'), false);

assert.equal(
  shouldShowThresholdUnitSelector({
    isFormulaMode: false,
    isEnumMetric: false,
    calculationUnit: 'bytes',
    unitList,
  }),
  true
);
assert.equal(
  shouldShowThresholdUnitSelector({
    isFormulaMode: true,
    isEnumMetric: false,
    calculationUnit: 'percent',
    unitList,
  }),
  true
);
assert.equal(
  shouldShowThresholdUnitSelector({
    isFormulaMode: false,
    isEnumMetric: true,
    calculationUnit: 'bytes',
    unitList,
  }),
  false
);
// none/short/空：不展示单位下拉
assert.equal(
  shouldShowThresholdUnitSelector({
    isFormulaMode: false,
    isEnumMetric: false,
    calculationUnit: 'none',
    unitList,
  }),
  false
);
assert.equal(
  shouldShowThresholdUnitSelector({
    isFormulaMode: false,
    isEnumMetric: false,
    calculationUnit: null,
    unitList,
  }),
  false
);
assert.equal(
  shouldShowThresholdUnitSelector({
    isFormulaMode: false,
    isEnumMetric: false,
    calculationUnit: 'short',
    unitList,
  }),
  false
);
// 有效 unit_id 但不在单位表可选集中：隐藏，避免空下拉+必填
assert.equal(
  shouldShowThresholdUnitSelector({
    isFormulaMode: false,
    isEnumMetric: false,
    calculationUnit: 'unknown-unit',
    unitList,
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

// resolveUnitOnMetricSelect: none/short 不得回落到 cps 等独立单位
assert.equal(resolveUnitOnMetricSelect('none'), null);
assert.equal(resolveUnitOnMetricSelect('short'), null);
assert.equal(resolveUnitOnMetricSelect(null), null);
assert.equal(resolveUnitOnMetricSelect('cps'), 'cps');
assert.equal(resolveUnitOnMetricSelect('bytes'), 'bytes');
assert.equal(resolveUnitOnMetricSelect('[{"id":1,"name":"up"}]'), null);

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

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const strategyDetailPath = fileURLToPath(
  new URL(
    '../src/app/monitor/(pages)/event/strategy/detail/page.tsx',
    import.meta.url
  )
);
const strategyDetailSource = readFileSync(strategyDetailPath, 'utf8');
assert.match(
  strategyDetailSource,
  /else if \(formData\?\.id != null\)/,
  '编辑策略必须等详情 id 就绪后再 dealDetail，避免空数据冲掉频率'
);
assert.match(
  strategyDetailSource,
  /policyDetailReady: formData\?\.id != null/,
  '编辑态空 collect_type 必须等详情 id 就绪后再决定是否回退插件'
);
assert.match(
  strategyDetailSource,
  /extractMetricIdsFromQueryCondition/,
  '多插件空/无效 collect_type 须能从 query_condition 抽 metric_id'
);
assert.match(
  strategyDetailSource,
  /resolvePluginIdFromMetricPlugins/,
  'metric→plugin 反查必须接到编辑回填路径'
);
assert.match(
  strategyDetailSource,
  /metricResolvedPluginId/,
  '反查结果须进入 resolveInitialMetricPluginId / 表单回填'
);
assert.match(
  strategyDetailSource,
  /formData\?\.collect_type, formData\?\.id, monitorObjId/,
  '插件目录加载必须在策略 id 到达后重跑，避免空 collect_type 错过回退'
);
assert.match(
  strategyDetailSource,
  /shouldHydrateMetricOnEdit/,
  '编辑回填不得只等指标目录，详情 id 到达后也要按 metric_id 补名称'
);
assert.match(
  strategyDetailSource,
  /resolveEditFormCollectType\(collect_type, pluginList, metricResolvedPluginId\)/,
  '编辑回填空 collect_type 且单插件时写入表单，避免再次存成空串'
);
assert.match(
  strategyDetailSource,
  /setUnit\(schedule\?\.type \|\| 'min'\)/,
  '频率单位缺失时回退 min，避免空单位导致输入框不可用'
);
assert.match(
  strategyDetailSource,
  /getAllUsers\(orgIds\)/,
  '通知人列表必须按策略所属组织拉取'
);
assert.match(
  strategyDetailSource,
  /pruneNoticeUsers/,
  '组织变更后必须自动剔除越界通知人'
);

assert.deepEqual(
  pruneNoticeUsers([1, '2', 3], [
    { id: 1, username: 'a' },
    { id: 2, username: 'b' },
  ]),
  [1, '2']
);
assert.deepEqual(pruneNoticeUsers([1, 2], []), []);
assert.deepEqual(pruneNoticeUsers(undefined, [{ id: 1 }]), []);

assert.equal(
  shouldRequireNoticeUsers({
    notice: true,
    noticeTypeIds: [1],
    channelList: [{ id: 1, channel_type: 'email' }],
  }),
  true
);
assert.equal(
  shouldRequireNoticeUsers({
    notice: true,
    noticeTypeIds: [1],
    channelList: [{ id: 1, channel_type: 'nats' }],
  }),
  false
);
assert.equal(
  shouldRequireNoticeUsers({
    notice: false,
    noticeTypeIds: [1],
    channelList: [{ id: 1, channel_type: 'email' }],
  }),
  false
);

assert.deepEqual(
  insertAlertNameVariableAtCursor(
    'SCP宿主机 ${resource_name}磁盘使用率过高',
    '${value}',
    'SCP宿主机 ${resource_name}'.length,
    'SCP宿主机 ${resource_name}'.length
  ),
  {
    value: 'SCP宿主机 ${resource_name}${value}磁盘使用率过高',
    cursor: 'SCP宿主机 ${resource_name}${value}'.length,
  }
);
assert.deepEqual(insertAlertNameVariableAtCursor('告警', '${level}', 0, 0), {
  value: '${level}告警',
  cursor: '${level}'.length,
});
assert.deepEqual(insertAlertNameVariableAtCursor('告警', '${level}'), {
  value: '告警${level}',
  cursor: '告警${level}'.length,
});
assert.deepEqual(
  insertAlertNameVariableAtCursor('api告警', '${metric_name}', 3, 4),
  {
    value: 'api${metric_name}警',
    cursor: 3 + '${metric_name}'.length,
  }
);

assert.equal(scheduleValueToMinutes(5, 'min'), 5);
assert.equal(scheduleValueToMinutes(1, 'hour'), 60);
assert.equal(scheduleValueToMinutes(null, 'min'), 0);

assert.equal(
  resolveFunctionDelayMinutes(['sum(cpu_usage{__$labels__}) by (instance_id)']),
  null
);
assert.equal(
  resolveFunctionDelayMinutes([
    'sum(rate(net_bytes_recv{__$labels__}[5m])) by (instance_id)',
  ]),
  5
);
assert.equal(
  resolveFunctionDelayMinutes([
    'sum(rate(net_bytes_recv{__$labels__}[30s])) by (instance_id)',
  ]),
  1
);
assert.equal(
  resolveFunctionDelayMinutes([
    'sum(rate(a{__$labels__}[5m]))',
    'sum(rate(b{__$labels__}[15m]))',
  ]),
  15
);
assert.equal(
  resolveFunctionDelayMinutes([
    'sum(rate(net_bytes_recv{__$labels__}[__$window__])) by (instance_id)',
  ], 5),
  5
);
assert.equal(
  resolveFunctionDelayMinutes([
    'sum(rate(net_bytes_recv{__$labels__}[__$window__])) by (instance_id)',
  ], 0),
  null
);
assert.equal(
  resolveFunctionDelayMinutes([
    'avg_over_time(sqlserver_cpu{__$labels__}[1h:1m])',
  ]),
  60
);

assert.deepEqual(
  collectMetricQueryTexts({
    rows: [{ metricId: 1, metricName: 'cpu' }],
    metrics: [
      { id: 1, name: 'cpu', query: 'rate(cpu[5m])' },
      { id: 2, name: 'mem', query: 'mem_used' },
    ] as any,
    formulaExpression: 'a / b * 100',
  }),
  ['rate(cpu[5m])', 'a / b * 100']
);
assert.deepEqual(
  collectMetricQueryTexts({
    rows: [{ metricId: 1, metricName: 'cpu' }],
    metrics: [{ id: 1, name: 'cpu', query: 'rate(cpu[5m])' }] as any,
  }),
  ['rate(cpu[5m])']
);

assert.equal(queriesContainRateFunction(['cpu_usage_total']), false);
assert.equal(queriesContainRateFunction(['rate(if_octets[5m])']), true);
assert.equal(queriesContainRateFunction(['irate(if_octets[1m])']), true);
assert.equal(queriesContainRateFunction(['increase(if_octets[5m])', 'cpu']), true);
assert.equal(
  rateAlgorithmConflictsWithQuery('rate', ['rate(if_octets[5m])']),
  true
);
assert.equal(
  rateAlgorithmConflictsWithQuery('avg_over_time', ['rate(if_octets[5m])']),
  false
);
assert.equal(mapQuantityToRateUnit('bytes'), 'byteps');
assert.equal(mapQuantityToRateUnit('kibibytes'), 'kibyteps');
assert.equal(mapQuantityToRateUnit('bits'), 'bitps');
assert.equal(mapQuantityToRateUnit('counts'), 'cps');
assert.equal(mapQuantityToRateUnit('byteps'), 'byteps');
assert.equal(mapQuantityToRateUnit('percent'), 'percent');
assert.deepEqual(
  resolvePolicyResultUnit({
    calculationUnit: 'kibibytes',
    metricUnit: 'bytes',
    algorithm: 'rate',
  }),
  { unit: 'byteps', conversionEnabled: false }
);
assert.equal(
  resolveThresholdUnitBase({
    calculationUnit: 'percent',
    metricUnit: 'bytes',
    algorithm: 'deriv',
  }),
  'byteps'
);
assert.equal(
  resolveThresholdUnitBase({
    calculationUnit: 'percent',
    metricUnit: 'percent',
    algorithm: 'rate',
  }),
  'percent'
);

assert.deepEqual(getEnabledCompareModes({ periodType: 'min', periodValue: 5 }), [
  'absolute',
  'previous_window',
  'offset_hours',
  'offset_days',
  'baseline_days',
  'baseline_weeks',
  'timeleft',
]);
assert.ok(getEnabledCompareModes({ periodType: 'hour', periodValue: 1 }).includes('offset_hours'));
assert.ok(getEnabledCompareModes({ periodType: 'day', periodValue: 7 }).includes('offset_days'));
assert.ok(compareOffsetHoursConflict(1, 'hour', 1));
assert.ok(!compareOffsetHoursConflict(3, 'hour', 1));
assert.ok(compareSpanConflict('offset_days', 1, 'day', 1));
assert.ok(!compareSpanConflict('offset_days', 7, 'day', 1));
assert.ok(compareSpanConflict('baseline_weeks', 4, 'day', 7));
assert.ok(!compareSpanConflict('baseline_weeks', 4, 'day', 1));
assert.ok(compareSpanConflict('baseline_days', 7, 'day', 1));
assert.ok(compareSpanConflict('baseline_days', 7, 'day', 7));
assert.ok(!compareSpanConflict('baseline_days', 7, 'hour', 1));
assert.equal(compareBaselineFamily('baseline_days'), 'yoy');
assert.deepEqual(resolveLoadedCompareOffset({ mode: 'offset_1h' }), {
  mode: 'offset_hours',
  amount: 1,
});
assert.deepEqual(resolveLoadedCompareOffset({ mode: 'offset_24h' }), {
  mode: 'offset_hours',
  amount: 24,
});
assert.deepEqual(resolveLoadedCompareOffset({ mode: 'offset_7d' }), {
  mode: 'offset_days',
  amount: 7,
});
assert.deepEqual(resolveLoadedCompareOffset({ mode: 'offset_30d' }), {
  mode: 'offset_days',
  amount: 30,
});
assert.deepEqual(resolveLoadedCompareOffset({ mode: 'baseline_4w' }), {
  mode: 'baseline_weeks',
  amount: 4,
});
assert.deepEqual(
  resolveLoadedCompareOffset({ mode: 'baseline_days', days: 7 }),
  { mode: 'baseline_days', amount: 7 }
);
assert.equal(compareBaselineFamily('previous_window'), 'previous_window');
assert.equal(compareBaselineFamily('offset_hours'), 'yoy');
assert.equal(compareBaselineFamily('offset_days'), 'yoy');
assert.equal(compareBaselineFamily('baseline_weeks'), 'yoy');
assert.equal(compareBaselineFamily('timeleft'), 'timeleft');
assert.equal(compareBaselineFamily('absolute'), 'absolute');
assert.deepEqual(getEnabledCompareModes({ periodType: 'min', periodValue: 5, algorithm: 'count_if_over_time' }), [
  'absolute',
]);
assert.ok(!getEnabledCompareModes({ periodType: 'min', periodValue: 5, algorithm: 'p95_over_time' }).includes('timeleft'));
assert.ok(
  timeleftRequiresLowSideThresholds('absolute', [{ method: '>' }])
);
assert.ok(
  timeleftRequiresLowSideThresholds('timeleft', [{ method: '<' }])
);
assert.ok(
  timeleftRequiresLowSideThresholds('timeleft', [{ method: '<=' }])
);
assert.ok(
  !timeleftRequiresLowSideThresholds('timeleft', [{ method: '>' }])
);
assert.equal(isFilledThresholdValue(null), false);
assert.equal(isFilledThresholdValue(''), false);
assert.equal(isFilledThresholdValue(0), true);
assert.deepEqual(
  completedThresholds([
    { level: 'critical', method: '<', value: 2 },
    { level: 'error', method: '>', value: null },
    { level: 'warning', method: '>', value: undefined }
  ]).map((item) => item.level),
  ['critical']
);
assert.ok(
  timeleftRequiresLowSideThresholds(
    'timeleft',
    completedThresholds([
      { method: '<', value: 1 },
      { method: '>', value: null }
    ])
  )
);

assert.deepEqual(
  resolveCompareFieldsForSave({
    isTrap: true,
    compareMode: 'offset_1h',
    compareValueKind: 'percent',
  }),
  {
    compare_mode: 'absolute',
    compare_value_kind: '',
    count_predicate: {},
    forecast_target: null,
    forecast_target_unit: '',
    forecast_lookback: {},
    compare_offset_hours: null,
    compare_offset_days: null,
    compare_baseline_weeks: null,
  }
);
assert.deepEqual(
  resolveCompareFieldsForSave({
    isTrap: false,
    compareMode: 'previous_window',
    compareValueKind: 'percent',
  }),
  {
    compare_mode: 'previous_window',
    compare_value_kind: 'percent',
    count_predicate: {},
    forecast_target: null,
    forecast_target_unit: '',
    forecast_lookback: {},
    compare_offset_hours: null,
    compare_offset_days: null,
    compare_baseline_weeks: null,
  }
);
assert.deepEqual(
  resolveCompareFieldsForSave({
    isTrap: false,
    compareMode: 'offset_hours',
    compareValueKind: 'percent',
    compareOffsetHours: 3,
  }),
  {
    compare_mode: 'offset_hours',
    compare_value_kind: 'percent',
    count_predicate: {},
    forecast_target: null,
    forecast_target_unit: '',
    forecast_lookback: {},
    compare_offset_hours: 3,
    compare_offset_days: null,
    compare_baseline_weeks: null,
  }
);
assert.deepEqual(
  resolveCompareFieldsForSave({
    isTrap: false,
    compareMode: 'offset_days',
    compareValueKind: 'percent',
    compareOffsetHours: 30,
  }),
  {
    compare_mode: 'offset_days',
    compare_value_kind: 'percent',
    count_predicate: {},
    forecast_target: null,
    forecast_target_unit: '',
    forecast_lookback: {},
    compare_offset_hours: null,
    compare_offset_days: 30,
    compare_baseline_weeks: null,
  }
);
assert.deepEqual(
  resolveCompareFieldsForSave({
    isTrap: false,
    compareMode: 'baseline_weeks',
    compareValueKind: 'delta',
    compareOffsetHours: 4,
  }),
  {
    compare_mode: 'baseline_weeks',
    compare_value_kind: 'delta',
    count_predicate: {},
    forecast_target: null,
    forecast_target_unit: '',
    forecast_lookback: {},
    compare_offset_hours: null,
    compare_offset_days: null,
    compare_baseline_weeks: 4,
  }
);
assert.deepEqual(
  resolveCompareFieldsForSave({
    isTrap: false,
    compareMode: 'baseline_days',
    compareValueKind: 'delta',
    compareOffsetHours: 7,
  }),
  {
    compare_mode: 'baseline_days',
    compare_value_kind: 'delta',
    count_predicate: {},
    forecast_target: null,
    forecast_target_unit: '',
    forecast_lookback: {},
    compare_offset_hours: null,
    compare_offset_days: 7,
    compare_baseline_weeks: null,
  }
);
assert.deepEqual(
  resolveCompareFieldsForSave({
    isTrap: false,
    compareMode: 'timeleft',
    compareValueKind: 'hours',
    forecastTarget: 90,
    forecastTargetUnit: 'gibibytes',
    forecastLookback: { type: 'hour', value: 4 },
  }),
  {
    compare_mode: 'timeleft',
    compare_value_kind: 'hours',
    count_predicate: {},
    forecast_target: 90,
    forecast_target_unit: 'gibibytes',
    forecast_lookback: { type: 'hour', value: 4 },
    compare_offset_hours: null,
    compare_offset_days: null,
    compare_baseline_weeks: null,
  }
);
assert.equal(
  resolveForecastTargetUnit({
    isFormulaMode: false,
    metricUnit: 'bytes',
    forecastTargetUnit: 'kibibytes',
    unitOptions: crossSystemUnitList.filter((item) => item.system === 'bytes'),
  }),
  'kibibytes'
);
assert.equal(
  resolveForecastTargetUnit({
    isFormulaMode: false,
    metricUnit: 'bytes',
    forecastTargetUnit: 'percent',
    unitOptions: crossSystemUnitList.filter((item) => item.system === 'bytes'),
  }),
  'bytes'
);
assert.equal(
  resolveForecastTargetUnit({
    isFormulaMode: true,
    metricUnit: 'bytes',
    forecastTargetUnit: 'gibibytes',
    unitOptions: crossSystemUnitList.filter((item) => item.system === 'bytes'),
  }),
  ''
);

assert.deepEqual(
  resolvePolicyResultUnit({ compareValueKind: 'percent', calculationUnit: 'bytes' }),
  { unit: 'percent', conversionEnabled: false }
);
assert.deepEqual(
  resolvePolicyResultUnit({ compareValueKind: 'ratio', calculationUnit: 'bytes' }),
  { unit: null, conversionEnabled: false }
);
assert.equal(
  resolveThresholdUnitBase({ compareValueKind: 'percent', calculationUnit: 'bytes' }),
  'percent'
);
assert.equal(
  resolveThresholdUnitBase({ compareValueKind: 'ratio', calculationUnit: 'bytes' }),
  null
);
assert.equal(
  resolveThresholdUnitBase({
    compareValueKind: '',
    calculationUnit: 'percent',
    algorithm: 'count_if_over_time',
  }),
  'count'
);
assert.equal(
  resolveThresholdUnitBase({
    compareValueKind: 'hours',
    calculationUnit: 'percent',
    algorithm: 'last_over_time',
  }),
  'hour'
);
assert.equal(
  shouldShowThresholdUnitSelector({
    isFormulaMode: false,
    isEnumMetric: false,
    calculationUnit: resolveThresholdUnitBase({
      compareValueKind: 'ratio',
      calculationUnit: 'bytes',
    }),
    unitList: [],
  }),
  false
);
assert.equal(shouldDrawPreviewThreshold(), true);
assert.equal(
  shouldDrawPreviewThreshold({ overlay: true, compareValueKind: 'percent' }),
  false
);
assert.equal(
  shouldDrawPreviewThreshold({ overlay: true, compareValueKind: 'ratio' }),
  false
);
assert.equal(
  shouldDrawPreviewThreshold({ overlay: true, compareValueKind: 'delta' }),
  true
);

assert.equal(formatDryRunHitCountCopy(1, 1), null);
assert.equal(formatDryRunHitCountCopy(2, 2), null);
assert.equal(
  formatDryRunHitCountCopy(1, 3),
  '本轮命中 1/3，现网不会建告警'
);
assert.equal(
  resolveDryRunReason({
    verdict: 'ok',
    reason: '对照缺失或留存不足',
    hit_count: 1,
    trigger_count: 3,
  }),
  '对照缺失或留存不足'
);
assert.equal(
  resolveDryRunReason({
    verdict: 'ok',
    reason: '',
    hit_count: 1,
    trigger_count: 2,
  }),
  ''
);
assert.equal(formatDryRunNumber(null), '—');
assert.equal(formatDryRunNumber(90), '90');
assert.equal(formatDryRunThreshold({ method: '>', value: 80, level: 'critical' }), '> 80 critical');
assert.equal(DRY_RUN_VERDICT_I18N.would_trigger, 'monitor.events.dryRunVerdictWouldTrigger');
assert.equal(DRY_RUN_VERDICT_I18N.no_data, 'monitor.events.dryRunVerdictNoData');
assert.equal(DRY_RUN_VERDICT_I18N.missing_baseline, 'monitor.events.dryRunVerdictMissingBaseline');
assert.equal(DRY_RUN_VERDICT_I18N.insufficient_samples, 'monitor.events.dryRunVerdictInsufficientSamples');
assert.equal(DRY_RUN_VERDICT_I18N.would_recover, 'monitor.events.dryRunVerdictWouldRecover');
assert.equal(DRY_RUN_VERDICT_I18N.hold, 'monitor.events.dryRunVerdictHold');

assert.deepEqual(
  resolveRecoveryThresholdForSave({
    isTrap: false,
    recoveryThreshold: { method: '<', value: 70 },
  }),
  { method: '<', value: 70 }
);
assert.deepEqual(
  resolveRecoveryThresholdForSave({
    isTrap: false,
    recoveryThreshold: { method: '<', value: null },
  }),
  {}
);
assert.deepEqual(
  resolveRecoveryThresholdForSave({
    isTrap: true,
    recoveryThreshold: { method: '<', value: 70 },
  }),
  {}
);
assert.deepEqual(
  resolveNoDataPeriodsForSave({
    enabled: true,
    detectionValue: 10,
    detectionUnit: 'min',
    recoveryValue: 2,
    recoveryUnit: 'min',
  }),
  {
    no_data_period: { type: 'min', value: 10 },
    no_data_recovery_period: { type: 'min', value: 2 },
  }
);
assert.deepEqual(
  resolveNoDataPeriodsForSave({
    enabled: false,
    detectionValue: 10,
    detectionUnit: 'min',
    recoveryValue: 2,
    recoveryUnit: 'min',
  }),
  {
    no_data_period: { type: 'min', value: 10 },
    no_data_recovery_period: { type: 'min', value: 10 },
  }
);

const offsetHoursOption = getCompareModeSelectOptions({
  periodType: 'hour',
  periodValue: 1,
}).find((item) => item.value === 'offset_hours');
assert.equal(offsetHoursOption?.disabled, false);

const countIfCompare = getCompareModeSelectOptions({
  algorithm: 'count_if_over_time',
});
assert.equal(
  countIfCompare.find((item) => item.value === 'absolute')?.disabled,
  false
);
assert.equal(
  countIfCompare.find((item) => item.value === 'offset_hours')?.disabled,
  true
);
assert.equal(
  countIfCompare.find((item) => item.value === 'offset_hours')?.reasonKey,
  'monitor.events.compareModeDisabledCountIf'
);

assert.deepEqual(
  coerceThresholdsForCompareMode('timeleft', [
    { level: 'critical', method: '>', value: 24 },
    { level: 'error', method: '>=', value: 48 },
  ]),
  [
    { level: 'critical', method: '<', value: 24 },
    { level: 'error', method: '<=', value: 48 },
  ]
);
assert.deepEqual(
  coerceRecoveryForThresholds({ method: '<', value: 70 }, [{ method: '<' }]),
  { method: '', value: null }
);
assert.deepEqual(
  coerceRecoveryForThresholds({ method: '<', value: 70 }, [{ method: '>' }]),
  { method: '<', value: 70 }
);

const timeleftOnP95 = getCompareModeSelectOptions({
  algorithm: 'p95_over_time',
}).find((item) => item.value === 'timeleft');
assert.equal(timeleftOnP95?.disabled, true);
assert.equal(
  timeleftOnP95?.reasonKey,
  'monitor.events.compareModeDisabledTimeleft'
);
assert.equal(
  getCompareModeSelectOptions({
    algorithm: 'last_over_time',
  }).find((item) => item.value === 'timeleft')?.disabled,
  false
);
assert.ok(
  !getEnabledCompareModes({ algorithm: 'p95_over_time' }).includes('timeleft')
);
assert.ok(
  getEnabledCompareModes({ algorithm: 'last_over_time' }).includes('timeleft')
);

const t = (
  _key: string,
  fallback = _key,
  vars: Record<string, string | number> = {}
) =>
  Object.entries(vars).reduce(
    (text, [name, value]) => text.replaceAll(`{${name}}`, String(value)),
    fallback
  );

assert.equal(
  buildPolicyRestatement({
    t,
    metricLabel: 'CPU 使用率',
    algorithmLabel: 'P95',
    algorithm: 'p95_over_time',
    compareMode: 'offset_1h',
    compareValueKind: 'percent',
    compareModeLabel: '1 小时前同窗',
    thresholdMethod: '>',
    thresholdValue: 50,
  }),
  '这条策略在判断：CPU 使用率的P95，比 1 小时前高出 50%。'
);
assert.equal(
  buildPolicyRestatement({
    t,
    metricLabel: 'CPU 使用率',
    algorithmLabel: 'P95',
    algorithm: 'p95_over_time',
    compareMode: 'offset_hours',
    compareValueKind: 'percent',
    compareOffsetHours: 3,
    thresholdMethod: '>',
    thresholdValue: 50,
  }),
  '这条策略在判断：CPU 使用率的P95，比 3 小时前高出 50%。'
);
assert.equal(
  buildPolicyRestatement({
    t,
    metricLabel: 'CPU 使用率',
    algorithmLabel: '平均',
    algorithm: 'avg_over_time',
    compareMode: 'offset_days',
    compareValueKind: 'percent',
    compareOffsetHours: 30,
    thresholdMethod: '>',
    thresholdValue: 20,
  }),
  '这条策略在判断：CPU 使用率的平均，比 30 天前高出 20%。'
);
assert.equal(
  buildPolicyRestatement({
    t,
    metricLabel: '磁盘用量',
    algorithmLabel: '平均',
    algorithm: 'avg_over_time',
    compareMode: 'baseline_weeks',
    compareValueKind: 'percent',
    compareOffsetHours: 4,
    thresholdMethod: '>',
    thresholdValue: 10,
  }),
  '这条策略在判断：磁盘用量的平均，比 近 4 周同窗均值高出 10%。'
);
assert.equal(
  buildPolicyRestatement({
    t,
    metricLabel: '磁盘用量',
    algorithmLabel: '平均',
    algorithm: 'avg_over_time',
    compareMode: 'baseline_days',
    compareValueKind: 'delta',
    compareOffsetHours: 7,
    thresholdMethod: '>',
    thresholdValue: 5,
  }),
  '这条策略在判断：磁盘用量的平均，比 近 7 天同窗均值高出 5。'
);
assert.equal(
  buildPolicyRestatement({
    t,
    metricLabel: '磁盘使用率',
    algorithmLabel: '平均',
    algorithm: 'avg_over_time',
    compareMode: 'baseline_days',
    compareValueKind: 'delta',
    compareOffsetHours: 3,
    thresholdMethod: '>',
    thresholdValue: 5,
    thresholdUnitLabel: '%',
  }),
  '这条策略在判断：磁盘使用率的平均，比 近 3 天同窗均值高出 5 个百分点。'
);
assert.equal(
  compareSpanIssue({
    mode: 'baseline_weeks',
    amount: 1,
    t,
  }),
  '周数至少为 2'
);
assert.equal(
  compareSpanIssue({
    mode: 'baseline_days',
    amount: 3,
    periodType: 'day',
    periodValue: 1,
    t,
  }),
  '对照窗不能等于汇聚周期'
);
assert.equal(
  compareSpanIssue({
    mode: 'baseline_weeks',
    amount: 4,
    periodType: 'min',
    periodValue: 5,
    t,
  }),
  null
);
assert.equal(compareResultFamily('timeleft', 'hours'), 'hours');
assert.equal(compareResultFamily('baseline_days', 'percent'), 'percent');
assert.equal(compareResultFamily('baseline_days', 'delta'), 'metric');
assert.deepEqual(
  clearThresholdNumbers([
    { level: 'critical', method: '>', value: 5 },
    { level: 'error', method: '>', value: 3 },
  ]),
  [
    { level: 'critical', method: '>', value: null },
    { level: 'error', method: '>', value: null },
  ]
);
assert.equal(
  partitionTimeleftPreviewSeries(
    [{ values: [[1, '40']] }, { values: [[1, '3700000']] }],
    [5, 3]
  ).omitted,
  1
);
assert.equal(
  partitionTimeleftPreviewSeries(
    [{ values: [[1, '40']] }, { values: [[1, '3700000']] }],
    [5, 3]
  ).kept.length,
  1
);
assert.equal(
  formatDryRunDimensionLabel(
    "('host', 'vda1', '/etc/hostname', 'ext4')",
    [
      { name: 'instance_id', description: 'Instance' },
      { name: 'device', description: '磁盘设备' },
      { name: 'path', description: '挂载路径' },
      { name: 'fstype', description: '文件系统类型' },
    ]
  ),
  '磁盘设备: vda1-挂载路径: /etc/hostname-文件系统类型: ext4'
);
assert.equal(
  buildPolicyRestatement({
    t,
    metricLabel: 'CPU使用率',
    algorithmLabel: '平均',
    algorithm: 'avg_over_time',
    compareMode: 'previous_window',
    compareValueKind: 'percent',
    compareModeLabel: '相对上一等长窗',
    thresholdMethod: '>',
    thresholdValue: 0,
  }),
  '这条策略在判断：CPU使用率的平均，比 上一等长窗高出 0%。'
);
assert.equal(
  buildPolicyRestatement({
    t,
    metricLabel: '磁盘用量',
    algorithmLabel: '末值',
    algorithm: 'last_over_time',
    compareMode: 'timeleft',
    compareValueKind: 'hours',
    thresholdMethod: '<',
    thresholdValue: 24,
  }),
  '这条策略在判断：磁盘用量距容量线还剩不足 24 小时（请填写容量线）。'
);
assert.equal(
  buildPolicyRestatement({
    t,
    algorithm: 'count_if_over_time',
    compareMode: 'absolute',
    thresholdMethod: '>=',
    thresholdValue: 3,
    thresholdUnitLabel: 'count',
    countPredicateMethod: '>',
    countPredicateValue: 0,
  }),
  '这条策略在判断：窗口内满足 > 0 的点数 >= 3 count。'
);

assert.equal(shouldAnnotatePerSecond('percent', 'rate'), true);
assert.equal(shouldAnnotatePerSecond('bytes', 'rate'), false);
assert.equal(shouldAnnotatePerSecond('byteps', 'rate'), false);
assert.equal(formatUnitLabelWithRateSuffix('%', 'percent', 'rate'), '%/s');
assert.equal(formatUnitLabelWithRateSuffix('B/s', 'byteps', 'rate'), 'B/s');

assert.deepEqual(
  groupAlgorithmOptions([
    { value: 'avg_over_time' },
    { value: 'p95_over_time' },
    { value: 'rate' },
    { value: 'changes' },
  ]).map((group) => ({
    key: group.key,
    values: group.options.map((item) => item.value),
  })),
  [
    { key: 'window', values: ['avg_over_time', 'p95_over_time'] },
    { key: 'change', values: ['rate', 'changes'] },
  ]
);

assert.equal(formatAlgorithmDisplayLabel('平均', 'avg_over_time'), '平均（AVG_OVER_TIME）');
assert.equal(formatAlgorithmDisplayLabel('最大', 'max_over_time'), '最大（MAX_OVER_TIME）');
assert.equal(formatAlgorithmDisplayLabel('P95', 'p95_over_time'), 'P95（P95_OVER_TIME）');
assert.equal(formatAlgorithmDisplayLabel('速率', 'rate'), '速率（RATE）');
assert.equal(getAlgorithmShortName('count_if_over_time'), 'COUNT_IF_OVER_TIME');

console.log('monitor-strategy-detail logic validation passed');
