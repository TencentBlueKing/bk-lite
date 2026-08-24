import assert from 'node:assert/strict';

import { buildWidgetSubmitConfig } from '../src/app/ops-analysis/components/widgetConfig/utils/submitConfig';
import { buildWidgetRequestParams } from '../src/app/ops-analysis/utils/widgetDataTransform';
import { buildFilterConfigConfirmSnapshot } from '../src/app/ops-analysis/utils/unifiedFilterState';
import type { UnifiedFilterDefinition } from '../src/app/ops-analysis/types/dashBoard';

const hostFilterMultiple: UnifiedFilterDefinition = {
  id: 'instance_ids__string',
  key: 'instance_ids',
  name: '主机',
  type: 'string',
  order: 0,
  enabled: true,
  inputConfig: {
    control: 'select',
    multiple: true,
    optionsSource: { type: 'static', staticItems: [] },
  },
};

const hostFilterScalar: UnifiedFilterDefinition = {
  ...hostFilterMultiple,
  inputConfig: {
    control: 'select',
    multiple: false,
    optionsSource: { type: 'static', staticItems: [] },
  },
};

const initialValues = { [hostFilterMultiple.id]: ['h1', 'h2'] as const };

const widgetConfig = {
  chartType: 'single',
  dataSource: '1',
  dataSourceParams: [
    {
      name: 'instance_ids',
      alias_name: '主机',
      type: 'string',
      filterType: 'filter',
      value: null,
    },
  ],
  filterBindings: { [hostFilterMultiple.id]: true },
};

const buildRequestFromApplied = (
  definitions: UnifiedFilterDefinition[],
  appliedValues: Record<string, unknown>,
) =>
  buildWidgetRequestParams({
    config: widgetConfig,
    unifiedFilterValues: appliedValues as Record<string, never>,
    filterBindings: widgetConfig.filterBindings,
    filterDefinitions: definitions,
  });

/** Dashboard：配置确认后立即更新 applied definitions + values（不点查询）。 */
{
  const dashboardAppliedDefinitions = [hostFilterMultiple];
  const dashboardSnapshot = buildFilterConfigConfirmSnapshot(
    [hostFilterScalar],
    { ...initialValues },
    { ...initialValues },
  );

  assert.equal(
    dashboardSnapshot.appliedFilterValues[hostFilterScalar.id],
    'h1',
    'Dashboard applied value 应降为标量',
  );
  assert.equal(
    dashboardSnapshot.filterValues[hostFilterScalar.id],
    'h1',
    'Dashboard draft value 应降为标量',
  );

  const appliedDefinitions = dashboardSnapshot.definitions;
  const appliedValues = dashboardSnapshot.appliedFilterValues;

  assert.equal(
    appliedDefinitions[0].inputConfig &&
      appliedDefinitions[0].inputConfig.control !== 'input' &&
      !appliedDefinitions[0].inputConfig.multiple,
    true,
    'Dashboard applied definition 应为 multiple=false',
  );
  assert.notDeepEqual(
    dashboardAppliedDefinitions,
    appliedDefinitions,
    '配置确认后 applied definitions 应更新',
  );

  assert.deepEqual(
    buildRequestFromApplied(appliedDefinitions, appliedValues),
    { instance_ids: 'h1' },
    'Dashboard 配置确认后 widget 请求必须为标量',
  );
  assert.notDeepEqual(
    buildRequestFromApplied(dashboardAppliedDefinitions, appliedValues),
    { instance_ids: 'h1' },
    '旧 applied definition 会把标量重新包装成数组',
  );

  const clearedSnapshot = buildFilterConfigConfirmSnapshot(
    [hostFilterScalar],
    { [hostFilterScalar.id]: null },
    { [hostFilterScalar.id]: null },
  );
  assert.deepEqual(
    buildRequestFromApplied(
      clearedSnapshot.definitions,
      clearedSnapshot.appliedFilterValues,
    ),
    {},
    'Dashboard 清空后应省略参数',
  );
}

/** Report：与 Dashboard 相同 applied snapshot 合同。 */
{
  let appliedFilterDefinitions: UnifiedFilterDefinition[] = [hostFilterMultiple];
  let filterValues = { ...initialValues };
  let appliedFilterValues = { ...initialValues };

  const confirm = (definitions: UnifiedFilterDefinition[]) => {
    const snapshot = buildFilterConfigConfirmSnapshot(
      definitions,
      filterValues,
      appliedFilterValues,
    );
    appliedFilterDefinitions = snapshot.definitions;
    filterValues = snapshot.filterValues;
    appliedFilterValues = snapshot.appliedFilterValues;
  };

  confirm([hostFilterScalar]);

  assert.equal(appliedFilterValues[hostFilterScalar.id], 'h1');
  assert.equal(filterValues[hostFilterScalar.id], 'h1');
  assert.equal(
    appliedFilterDefinitions[0].inputConfig &&
      appliedFilterDefinitions[0].inputConfig.control !== 'input' &&
      !appliedFilterDefinitions[0].inputConfig.multiple,
    true,
  );
  assert.deepEqual(
    buildRequestFromApplied(appliedFilterDefinitions, appliedFilterValues),
    { instance_ids: 'h1' },
    'Report 配置确认后 widget 请求必须为标量',
  );
}

/** Screen：applyFilterConfigConfirm 与 Dashboard 使用同一 snapshot helper。 */
{
  let definitions: UnifiedFilterDefinition[] = [hostFilterMultiple];
  let filterValues = { ...initialValues };
  let appliedFilterValues = { ...initialValues };

  const applyFilterConfigConfirm = (nextDefinitions: UnifiedFilterDefinition[]) => {
    const snapshot = buildFilterConfigConfirmSnapshot(
      nextDefinitions,
      filterValues,
      appliedFilterValues,
    );
    definitions = snapshot.definitions;
    filterValues = snapshot.filterValues;
    appliedFilterValues = snapshot.appliedFilterValues;
  };

  applyFilterConfigConfirm([hostFilterScalar]);

  assert.equal(filterValues[hostFilterScalar.id], 'h1', 'Screen current 应为标量');
  assert.equal(appliedFilterValues[hostFilterScalar.id], 'h1', 'Screen applied 应为标量');
  assert.deepEqual(
    buildRequestFromApplied(definitions, appliedFilterValues),
    { instance_ids: 'h1' },
    'Screen 配置确认后请求必须为标量',
  );

  applyFilterConfigConfirm([hostFilterScalar]);
  const clearedValues = { [hostFilterScalar.id]: null };
  filterValues = { ...clearedValues };
  appliedFilterValues = { ...clearedValues };
  const cleared = buildFilterConfigConfirmSnapshot(
    [hostFilterScalar],
    filterValues,
    appliedFilterValues,
  );
  filterValues = cleared.filterValues;
  appliedFilterValues = cleared.appliedFilterValues;
  assert.deepEqual(
    buildRequestFromApplied(definitions, appliedFilterValues),
    {},
    'Screen 清空后应省略参数',
  );
}

/** 生产存盘：`{}` 不会写入 valueConfig（字段省略）；显式关闭为 `{ id: false }`。 */
{
  const submitBase = {
    showChartThemeMode: false,
    showTableFilterFields: false,
    selectedFields: [],
    thresholdColors: [],
    displayColumns: [],
    filterFields: [],
    actions: [],
    chartType: 'single',
    values: {
      name: '主机',
      chartType: 'single',
      compare: false,
    },
  };

  const submitEmpty = buildWidgetSubmitConfig({
    ...submitBase,
    filterBindings: {},
  });
  assert.equal(
    submitEmpty.config?.filterBindings,
    undefined,
    'buildWidgetSubmitConfig 不得持久化空 filterBindings 对象',
  );

  const submitDisabled = buildWidgetSubmitConfig({
    ...submitBase,
    filterBindings: { instance_ids__string: false },
  });
  assert.deepEqual(
    submitDisabled.config?.filterBindings,
    { instance_ids__string: false },
    '显式关闭绑定应持久化为 false',
  );
}

console.log('ops analysis filter config confirm tests passed');
