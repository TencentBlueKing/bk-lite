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
