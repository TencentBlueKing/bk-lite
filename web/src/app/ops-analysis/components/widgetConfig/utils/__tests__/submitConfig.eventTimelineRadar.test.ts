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
});
