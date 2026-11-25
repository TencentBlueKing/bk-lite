import assert from 'node:assert/strict';
import test from 'node:test';
import {
  buildAddedDashboardWidgetValueConfig,
  buildWidgetSubmitConfig,
  mergeSanitizedWidgetValueConfig,
  mergeScreenWidgetValueConfig,
} from '../submitConfig';

const baseInput = {
  showChartThemeMode: false,
  showTableFilterFields: false,
  selectedFields: ['cpu'],
  thresholdColors: [],
  filterBindings: {},
  displayColumns: [],
  filterFields: [],
  actions: [],
};

test('single and gauge persist a calculation and drop it when cleared', () => {
  const saved = buildWidgetSubmitConfig({
    ...baseInput,
    chartType: 'single',
    values: {
      name: '平均 CPU',
      chartType: 'single',
      compare: false,
      scalarCalcMethod: 'avg',
      scalarCalcTimeField: 'time',
    },
  });
  assert.equal(saved.error, undefined);
  assert.deepEqual(saved.config?.scalarCalc, { method: 'avg', field: 'cpu' });

  const latest = buildWidgetSubmitConfig({
    ...baseInput,
    chartType: 'gauge',
    values: {
      name: '最新 CPU',
      chartType: 'gauge',
      compare: true,
      scalarCalcMethod: 'latest',
      scalarCalcTimeField: 'time',
      gaugeMin: 0,
      gaugeMax: 100,
    },
  });
  assert.deepEqual(latest.config?.scalarCalc, {
    method: 'latest',
    field: 'cpu',
    timeField: 'time',
  });

  const cleared = buildWidgetSubmitConfig({
    ...baseInput,
    chartType: 'single',
    values: {
      name: '平均 CPU',
      chartType: 'single',
      compare: false,
    },
  });
  assert.equal(cleared.config?.scalarCalc, undefined);

  const merged = mergeSanitizedWidgetValueConfig(
    { chartType: 'single', scalarCalc: { method: 'count' } },
    { chartType: 'single', scalarCalc: cleared.config?.scalarCalc },
    'single',
  );
  assert.equal(merged.scalarCalc, undefined);

  const screen = mergeScreenWidgetValueConfig(
    { chartType: 'gauge', scalarCalc: { method: 'sum', field: 'cpu' } },
    {
      name: '仪表盘',
      chartType: 'gauge',
      selectedFields: ['cpu'],
    },
    'gauge',
  );
  assert.equal(screen.scalarCalc, undefined);
});

test('a newly added dashboard widget keeps the calculation', () => {
  const saved = buildAddedDashboardWidgetValueConfig({
    name: '主机数',
    chartType: 'single',
    dataSource: 209,
    selectedFields: ['cpu'],
    scalarCalc: { method: 'count' },
    compare: true,
    compareMode: 'value',
  });
  assert.deepEqual(saved.scalarCalc, { method: 'count' });
  assert.equal(saved.compareMode, 'value');
  assert.deepEqual(saved.selectedFields, ['cpu']);
});

test('dashboard save keeps pie fields and scene widget config', () => {
  const pie = buildAddedDashboardWidgetValueConfig({
    name: '分布',
    chartType: 'pie',
    pieScalarFields: [{ field: 'cpu', label: 'CPU' }, { field: 'mem', label: '内存' }],
  });
  assert.deepEqual(pie.pieScalarFields, [
    { field: 'cpu', label: 'CPU' },
    { field: 'mem', label: '内存' },
  ]);

  const room = buildAddedDashboardWidgetValueConfig({
    name: '机房',
    chartType: 'room3D',
    sceneWidgetType: 'room3D',
    room3D: { rackTopLine1: '名称', rackTopLine2: 'U位' },
  });
  assert.deepEqual(room.room3D, { rackTopLine1: '名称', rackTopLine2: 'U位' });
});

test('a line chart does not keep a single-value calculation', () => {
  const merged = mergeSanitizedWidgetValueConfig(
    { chartType: 'single', scalarCalc: { method: 'count' }, singleStyle: { align: 'left' } },
    { chartType: 'line' },
    'line',
  );
  assert.equal(merged.scalarCalc, undefined);
  assert.equal(merged.singleStyle, undefined);
});
