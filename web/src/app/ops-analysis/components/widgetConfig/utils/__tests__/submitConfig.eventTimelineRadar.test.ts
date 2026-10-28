import assert from 'node:assert/strict';
import test from 'node:test';
import { buildWidgetSubmitConfig } from '../submitConfig';

test('eventTimeline submit keeps sort order only', () => {
  const result = buildWidgetSubmitConfig({
    values: {
      name: '事件时间线',
      chartType: 'eventTimeline',
      eventTimeline: {
        sortOrder: 'asc',
        timeField: 'time',
        titleField: 'title',
      },
      gaugeMin: 1,
      gaugeMax: 99,
      gaugeShape: 'circle',
    },
    chartType: 'eventTimeline',
    showChartThemeMode: false,
    showTableFilterFields: false,
    selectedFields: [],
    thresholdColors: [],
    filterBindings: {},
    displayColumns: [],
    filterFields: [],
    actions: [],
  });

  assert.equal(result.error, undefined);
  assert.deepEqual(result.config?.eventTimeline, {
    sortOrder: 'asc',
    timeField: 'time',
    titleField: 'title',
  });
  assert.equal('gaugeMin' in (result.config || {}), false);
  assert.equal('gaugeMax' in (result.config || {}), false);
  assert.equal('gaugeShape' in (result.config || {}), false);
});

test('radar submit persists indicators and range', () => {
  const result = buildWidgetSubmitConfig({
    values: {
      name: '雷达图',
      chartType: 'radar',
      radar: {
        min: 10,
        max: 120,
        indicators: [
          { key: 'cpu', label: 'CPU' },
          { key: 'memory', label: '内存' },
          { key: '  ', label: '忽略空 key' },
        ],
      },
    },
    chartType: 'radar',
    showChartThemeMode: false,
    showTableFilterFields: false,
    selectedFields: [],
    thresholdColors: [],
    filterBindings: {},
    displayColumns: [],
    filterFields: [],
    actions: [],
  });

  assert.equal(result.error, undefined);
  assert.deepEqual(result.config?.radar, {
    min: 10,
    max: 120,
    indicators: [
      { key: 'cpu', label: 'CPU' },
      { key: 'memory', label: '内存' },
    ],
  });
  assert.equal('gaugeMin' in (result.config || {}), false);
  assert.equal('gaugeMax' in (result.config || {}), false);
  assert.equal('gaugeShape' in (result.config || {}), false);
});

test('eventTable and eventTimeline submit keep the data link', () => {
  const interaction = {
    kind: 'data' as const,
    name: '查看',
    url: '/ops/event?id=$__data.fields.id$',
    openMode: 'sameTab' as const,
  };
  const eventTable = buildWidgetSubmitConfig({
    values: {
      name: '事件表',
      chartType: 'eventTable',
      interaction,
    },
    chartType: 'eventTable',
    showChartThemeMode: false,
    showTableFilterFields: false,
    selectedFields: [],
    thresholdColors: [],
    filterBindings: {},
    displayColumns: [
      { id: 'id', key: 'id', title: 'ID', visible: true, order: 0 },
    ],
    filterFields: [],
    actions: [],
  });
  assert.equal(eventTable.error, undefined);
  assert.deepEqual(eventTable.config?.interaction, interaction);
  assert.equal('actions' in (eventTable.config || {}), false);

  const eventTimeline = buildWidgetSubmitConfig({
    values: {
      name: '事件时间线',
      chartType: 'eventTimeline',
      eventTimeline: { sortOrder: 'desc', timeField: 'time', titleField: 'title' },
      interaction,
    },
    chartType: 'eventTimeline',
    showChartThemeMode: false,
    showTableFilterFields: false,
    selectedFields: [],
    thresholdColors: [],
    filterBindings: {},
    displayColumns: [],
    filterFields: [],
    actions: [],
  });
  assert.equal(eventTimeline.error, undefined);
  assert.deepEqual(eventTimeline.config?.interaction, interaction);
  assert.equal(eventTimeline.config?.eventTimeline?.timeField, 'time');
});

test('gauge submit keeps gauge fields', () => {
  const result = buildWidgetSubmitConfig({
    values: {
      name: '仪表盘',
      chartType: 'gauge',
      selectedFields: ['v'],
      gaugeMin: 1,
      gaugeMax: 99,
      gaugeShape: 'circle',
    },
    chartType: 'gauge',
    showChartThemeMode: false,
    showTableFilterFields: false,
    selectedFields: ['v'],
    thresholdColors: [],
    filterBindings: {},
    displayColumns: [],
    filterFields: [],
    actions: [],
  });

  assert.equal(result.error, undefined);
  assert.equal(result.config?.gaugeMin, 1);
  assert.equal(result.config?.gaugeMax, 99);
  assert.equal(result.config?.gaugeShape, 'circle');
  assert.equal(result.config?.compare, false);
  assert.equal(result.config?.compareMode, 'percent');
  assert.equal(result.config?.pieScalarFields, undefined);
});

test('gauge submit keeps an opted-in period compare', () => {
  const result = buildWidgetSubmitConfig({
    values: {
      name: '仪表盘',
      chartType: 'gauge',
      selectedFields: ['avg_cpu'],
      compare: true,
      compareMode: 'value',
    },
    chartType: 'gauge',
    showChartThemeMode: false,
    showTableFilterFields: false,
    selectedFields: ['avg_cpu'],
    thresholdColors: [],
    filterBindings: {},
    displayColumns: [],
    filterFields: [],
    actions: [],
  });

  assert.equal(result.config?.compare, true);
  assert.equal(result.config?.compareMode, 'value');
});

test('pie submit keeps two scalar fields and rejects a single field', () => {
  const kept = buildWidgetSubmitConfig({
    values: {
      name: '环',
      chartType: 'pie',
      pieScalarFields: [
        { field: 'collected_instance_count', label: '已采集' },
        { field: ' uncollected_instance_count ', label: ' 未采集 ' },
        { field: ' ', label: '空' },
      ],
    },
    chartType: 'pie',
    showChartThemeMode: false,
    showTableFilterFields: false,
    selectedFields: [],
    thresholdColors: [],
    filterBindings: {},
    displayColumns: [],
    filterFields: [],
    actions: [],
  });
  assert.deepEqual(kept.config?.pieScalarFields, [
    { field: 'collected_instance_count', label: '已采集' },
    { field: 'uncollected_instance_count', label: '未采集' },
  ]);

  const rejected = buildWidgetSubmitConfig({
    values: {
      name: '环',
      chartType: 'pie',
      pieScalarFields: [{ field: 'only_one' }],
    },
    chartType: 'pie',
    showChartThemeMode: false,
    showTableFilterFields: false,
    selectedFields: [],
    thresholdColors: [],
    filterBindings: {},
    displayColumns: [],
    filterFields: [],
    actions: [],
  });
  assert.equal(rejected.error, 'chartRoleFieldPairRequired');
});
