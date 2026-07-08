import assert from 'node:assert/strict';

import {
  FORMULA_DEFAULT_RESULT_UNIT,
  getThresholdUnitFilterBase,
  getThresholdUnitOptions,
  getValidThresholdUnitOptions,
  resolveFormulaResultUnit,
  resolveInitialMetricPluginId,
} from '../src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils';
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

console.log('monitor-strategy-detail logic validation passed');
