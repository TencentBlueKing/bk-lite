import assert from 'node:assert/strict';
import test from 'node:test';
import { buildDashboardRenderSignal } from '@/app/ops-analysis/renderContract';
import {
  hasRenderableChartData,
  validateTopologyMapWidgetData,
} from '../topologyMapWidgetContract';

test('DataSource graph object reaches topologyMap validation without items[] wrapping', () => {
  const datasourceResult = {
    nodes: [
      {
        id: 'host-a',
        instance_id: 1,
        instance_name: 'Host A',
        model_name: 'Host',
        alert_count: 0,
      },
    ],
    edges: [],
  };

  assert.deepEqual(
    validateTopologyMapWidgetData(datasourceResult, 'format mismatch'),
    { isValid: true },
  );
  assert.equal(hasRenderableChartData('topologyMap', datasourceResult), true);
});

test('empty topology resolves to empty terminal success and report-ready', () => {
  const datasourceResult = { nodes: [], edges: [] };
  assert.deepEqual(
    validateTopologyMapWidgetData(datasourceResult, 'format mismatch'),
    { isValid: true },
  );
  assert.equal(hasRenderableChartData('topologyMap', datasourceResult), false);

  const signal = buildDashboardRenderSignal(
    'dashboard-1',
    ['widget-1'],
    new Map([['widget-1', { widgetId: 'widget-1', status: 'empty' as const }]]),
  );
  assert.equal(signal?.type, 'report-ready');
});

test('all-zero pie slices and null KPI fields are not renderable data', () => {
  assert.equal(
    hasRenderableChartData('pie', [
      { name: '计算', value: 0 },
      { name: '存储', value: 0 },
    ]),
    false,
  );
  assert.equal(
    hasRenderableChartData('pie', [{ name: '计算', value: 12.5 }]),
    true,
  );
  assert.equal(
    hasRenderableChartData(
      'single',
      {
        total_cost: '0.00',
        instance_count: 0,
        avg_daily_cost: '0.00',
        mom_change_pct: null,
      },
      { selectedFields: ['mom_change_pct'] },
    ),
    false,
  );
  assert.equal(
    hasRenderableChartData(
      'single',
      {
        total_cost: '0.00',
        instance_count: 0,
        avg_daily_cost: '0.00',
        mom_change_pct: null,
      },
      { selectedFields: ['total_cost'] },
    ),
    true,
  );
});

test('line/bar empty envelopes are not renderable; categories still are', () => {
  assert.equal(
    hasRenderableChartData('line', { categories: [], values: [] }),
    false,
  );
  assert.equal(hasRenderableChartData('bar', { series: [] }), false);
  assert.equal(
    hasRenderableChartData('line', [{ name: '周一', value: 0 }]),
    true,
  );
});

test('table envelopes without rows are not renderable; item rows still are', () => {
  assert.equal(hasRenderableChartData('table', { count: 0 }), false);
  assert.equal(
    hasRenderableChartData('table', { items: [{ name: '账单' }] }),
    true,
  );
});

test('gauge follows numeric onReady, not any extracted string', () => {
  assert.equal(
    hasRenderableChartData('gauge', { value: '' }, { selectedFields: ['value'] }),
    false,
  );
  assert.equal(
    hasRenderableChartData('gauge', { value: 0 }, { selectedFields: ['value'] }),
    true,
  );
});

test('empty room3D racks are not renderable; racks keep async wait', () => {
  assert.equal(
    hasRenderableChartData('room3D', {
      room: { id: 'r1', name: '机房' },
      racks: [],
    }),
    false,
  );
  assert.equal(
    hasRenderableChartData('room3D', {
      room: { id: 'r1', name: '机房' },
      racks: [{ rack_id: 'a', rack_name: 'A', row: 1, col: 1 }],
    }),
    true,
  );
});

test('invalid topology is rejected before renderer and can terminate as failed', () => {
  const result = validateTopologyMapWidgetData(
    { nodes: [], edges: [{ source: 'a', target: 'b' }] },
    'format mismatch',
  );
  assert.equal(result.isValid, false);
  assert.equal(result.message, 'format mismatch');

  const signal = buildDashboardRenderSignal(
    'dashboard-1',
    ['widget-1'],
    new Map([
      [
        'widget-1',
        { widgetId: 'widget-1', status: 'failed' as const, error: result.message },
      ],
    ]),
  );
  assert.equal(signal?.type, 'report-failed');
});

test('nodeGraph session rows with complete mapping are renderable', () => {
  const rows = [
    { src: '10.0.0.1', dst: '10.0.0.2', value: 12 },
    { src: '10.0.0.2', dst: '10.0.0.3', value: 4 },
  ];
  assert.equal(
    hasRenderableChartData('nodeGraph', rows, {
      nodeGraphIdentityMode: 'ip',
      nodeGraphSourceField: 'src',
      nodeGraphTargetField: 'dst',
      nodeGraphValueField: 'value',
    }),
    true,
  );
});

test('nodeGraph empty rows or incomplete mapping are not renderable', () => {
  const mapping = {
    nodeGraphIdentityMode: 'ip' as const,
    nodeGraphSourceField: 'src',
    nodeGraphTargetField: 'dst',
    nodeGraphValueField: 'value',
  };
  assert.equal(hasRenderableChartData('nodeGraph', [], mapping), false);
  assert.equal(
    hasRenderableChartData('nodeGraph', [{ src: '10.0.0.1', dst: '10.0.0.2', value: 9 }], {
      nodeGraphSourceField: 'src',
    }),
    false,
  );
});
