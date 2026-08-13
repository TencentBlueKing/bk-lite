import assert from 'node:assert/strict';
import test from 'node:test';
import {
  buildTopologyMapEdgeCells,
  buildTopologyMapNodeCell,
  getTopologyMapAlertStatus,
  getTopologyMapAlertVisual,
} from '../topologyMapGraph';
import {
  applyPreservedNodePosition,
  buildTopologyMapStructureSignature,
} from '../topologyMapViewerSession';
import { TOPOLOGY_MAP_NODE_SIZE } from '@/app/ops-analysis/utils/topologyMapData';

test('alert status follows count-first topology semantics', () => {
  assert.equal(getTopologyMapAlertStatus('0', 0), 'normal');
  assert.equal(getTopologyMapAlertStatus('0', 3), 'critical');
  assert.equal(getTopologyMapAlertStatus('1', 3), 'error');
  assert.equal(getTopologyMapAlertStatus('2', 3), 'warning');
  assert.equal(getTopologyMapAlertStatus('future', 3), 'unknown');
});

test('critical and error remain statically distinguishable without pulse', () => {
  const critical = getTopologyMapAlertVisual('0', 2);
  const error = getTopologyMapAlertVisual('1', 2);
  assert.equal(critical.color, error.color);
  assert.equal(critical.color, 'var(--color-fail)');
  assert.notEqual(critical.strokeWidth, error.strokeWidth);
  assert.equal(critical.criticalRingOpacity, 1);
  assert.equal(error.criticalRingOpacity, 0);
  assert.equal(critical.pulse, true);
  assert.equal(error.pulse, false);
});

test('unknown alert level keeps its real count with a neutral badge', () => {
  const cell = buildTopologyMapNodeCell({
    id: 'a',
    instance_id: 1,
    instance_name: 'A',
    model_name: 'Host',
    alert_count: 108,
    alert_level: 'future',
    x: 0,
    y: 0,
  });
  assert.equal(cell.attrs.badgeText.text, '99+');
  assert.equal(cell.attrs.badgeText.opacity, 1);
  assert.equal(cell.attrs.badge.fill, 'var(--color-text-3)');
});

test('zero alert count ignores level and hides alert treatment', () => {
  const visual = getTopologyMapAlertVisual('0', 0);
  assert.equal(visual.color, 'var(--color-primary)');
  assert.equal(visual.pulse, false);

  const cell = buildTopologyMapNodeCell({
    id: 'a',
    instance_id: 1,
    instance_name: 'A',
    model_name: 'Host',
    alert_count: 0,
    alert_level: '0',
    x: 0,
    y: 0,
  });
  assert.equal(cell.attrs.badgeText.opacity, 0);
  assert.equal(cell.attrs.subtitle.text, '');
  assert.equal(cell.attrs.subtitle.opacity, 0);
  assert.equal(cell.attrs.title.refY, 27);
  assert.equal(cell.attrs.model.refY, 52);
  assert.equal(cell.attrs.badgeText.refX, 180);
  assert.equal(cell.attrs.badgeText.refY, 24);
});

test('node keeps independent title, model and subtitle lines without changing outer size', () => {
  const withSubtitle = buildTopologyMapNodeCell({
    id: 'payment',
    instance_id: 1,
    instance_name: 'Payment Service',
    model_name: 'Application',
    subtitle: 'Cluster A',
    alert_count: 8,
    alert_level: '1',
    x: 0,
    y: 0,
  });
  const withoutSubtitle = buildTopologyMapNodeCell({
    id: 'payment',
    instance_id: 1,
    instance_name: 'Payment Service',
    model_name: 'Application',
    alert_count: 8,
    alert_level: '1',
    x: 0,
    y: 0,
  });

  assert.equal(withSubtitle.width, TOPOLOGY_MAP_NODE_SIZE.width);
  assert.equal(withSubtitle.height, TOPOLOGY_MAP_NODE_SIZE.height);
  assert.equal(withoutSubtitle.width, TOPOLOGY_MAP_NODE_SIZE.width);
  assert.equal(withoutSubtitle.height, TOPOLOGY_MAP_NODE_SIZE.height);

  assert.equal(withSubtitle.attrs.title.text, 'Payment Service');
  assert.equal(withSubtitle.attrs.model.text, 'Application');
  assert.equal(withSubtitle.attrs.subtitle.text, 'Cluster A');
  assert.equal(withSubtitle.attrs.subtitle.opacity, 1);
  assert.equal(withSubtitle.attrs.title.refY, 18);
  assert.equal(withSubtitle.attrs.model.refY, 40);
  assert.equal(withSubtitle.attrs.subtitle.refY, 62);

  assert.equal(withoutSubtitle.attrs.model.text, 'Application');
  assert.equal(withoutSubtitle.attrs.subtitle.text, '');
  assert.equal(withoutSubtitle.attrs.subtitle.opacity, 0);
  assert.equal(withoutSubtitle.attrs.title.refY, 27);
  assert.equal(withoutSubtitle.attrs.model.refY, 52);
  assert.equal(withSubtitle.attrs.badgeText.text, '8');
});

test('reverse edges receive distinct vertices without enabling same-direction multigraphs', () => {
  const nodes = [
    {
      id: 'a', instance_id: 1, instance_name: 'A', model_name: 'Host',
      alert_count: 0, x: 0, y: 0,
    },
    {
      id: 'b', instance_id: 2, instance_name: 'B', model_name: 'Host',
      alert_count: 0, x: 300, y: 0,
    },
  ];
  const cells = buildTopologyMapEdgeCells([
    { source: 'a', target: 'b', line_style: 'solid', connection_type: 'single' },
    { source: 'b', target: 'a', line_style: 'solid', connection_type: 'single' },
  ], nodes);
  assert.equal(cells.length, 2);
  assert.notDeepEqual(cells[0].vertices, cells[1].vertices);
});

test('edge markers are controlled only by connection_type', () => {
  const [none, single, double] = buildTopologyMapEdgeCells([
    { source: 'a', target: 'b', line_style: 'solid', connection_type: 'none' },
    { source: 'b', target: 'c', line_style: 'dashed', connection_type: 'single' },
    { source: 'c', target: 'd', line_style: 'solid', connection_type: 'double' },
  ], []);

  assert.equal(none.attrs.line.sourceMarker, undefined);
  assert.equal(none.attrs.line.targetMarker, undefined);
  assert.equal(single.attrs.line.sourceMarker, undefined);
  assert.ok(single.attrs.line.targetMarker);
  assert.ok(double.attrs.line.sourceMarker);
  assert.ok(double.attrs.line.targetMarker);
  assert.equal(single.attrs.line.strokeDasharray, '6 4');
  assert.equal(none.attrs.line.stroke, 'var(--color-primary)');
});

test('temporary drag position survives non-structural data refresh without relayout or fit', () => {
  const initial = {
    nodes: [{
      id: 'a',
      instance_id: 1,
      instance_name: 'Gateway',
      model_name: 'Service',
      alert_count: 0,
    }, {
      id: 'b',
      instance_id: 2,
      instance_name: 'Database',
      model_name: 'Store',
      alert_count: 1,
      alert_level: '2',
    }],
    edges: [{
      source: 'a',
      target: 'b',
      line_style: 'solid' as const,
      connection_type: 'single' as const,
    }],
  };
  const refreshed = {
    nodes: [{
      id: 'a',
      instance_id: 1,
      instance_name: 'API Gateway',
      model_name: 'Application',
      subtitle: 'region-east',
      alert_count: 5,
      alert_level: '0',
    }, {
      id: 'b',
      instance_id: 2,
      instance_name: 'Order Database',
      model_name: 'Database',
      alert_count: 2,
      alert_level: '1',
    }],
    edges: [{
      source: 'a',
      target: 'b',
      line_style: 'solid' as const,
      connection_type: 'single' as const,
    }],
  };
  const signature = buildTopologyMapStructureSignature(initial);
  assert.equal(signature, buildTopologyMapStructureSignature(refreshed));

  const dragged = applyPreservedNodePosition(refreshed.nodes[0], { x: 420, y: 260 });
  const cell = buildTopologyMapNodeCell(dragged);
  assert.equal(cell.x, 420);
  assert.equal(cell.y, 260);
  assert.equal(cell.attrs.title.text, 'API Gateway');
  assert.equal(cell.attrs.model.text, 'Application');
  assert.equal(cell.attrs.subtitle.text, 'region-east');
  assert.equal(cell.attrs.badgeText.text, '5');
  assert.equal(cell.attrs.body.strokeWidth, 3);
  assert.equal(cell.attrs.criticalRing.opacity, 1);
});

test('graph identity changes produce a new structure signature', () => {
  const previous = {
    nodes: [{
      id: 'a', instance_id: 1, instance_name: 'A', model_name: 'Host', alert_count: 0,
    }],
    edges: [],
  };
  const next = {
    nodes: [
      { id: 'a', instance_id: 1, instance_name: 'A', model_name: 'Host', alert_count: 0 },
      { id: 'b', instance_id: 2, instance_name: 'B', model_name: 'Host', alert_count: 0 },
    ],
    edges: [{
      source: 'a',
      target: 'b',
      line_style: 'solid' as const,
      connection_type: 'none' as const,
    }],
  };
  assert.notEqual(
    buildTopologyMapStructureSignature(previous),
    buildTopologyMapStructureSignature(next),
  );
});
