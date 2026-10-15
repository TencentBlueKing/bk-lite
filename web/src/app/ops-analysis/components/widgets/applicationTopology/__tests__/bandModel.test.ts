import { describe, expect, it } from 'vitest';
import { ALERT_LEVEL_COLORS } from '@/constants/observabilityChart';
import {
  applicationTopologyToneColor,
  APPLICATION_TOPOLOGY_LAYOUT,
  buildApplicationTopologyLayout,
  formatAlertBadge,
  resolveApplicationTopologyHover,
  resolveApplicationTopologyTone,
} from '../bandModel';

const CENTER = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const HOST = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const CACHE = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc';
const HIDDEN = 'dddddddd-dddd-4ddd-8ddd-dddddddddddd';

describe('application topology tone', () => {
  it('keeps unmonitored and quiet nodes apart, and caps the badge', () => {
    expect(resolveApplicationTopologyTone(null, null)).toBe('unknown');
    expect(resolveApplicationTopologyTone(0, null)).toBe('normal');
    expect(resolveApplicationTopologyTone(2, 'critical')).toBe('critical');
    expect(resolveApplicationTopologyTone(1, 'error')).toBe('error');
    expect(resolveApplicationTopologyTone(4, 'info')).toBe('warning');
    expect(formatAlertBadge(null)).toBeNull();
    expect(formatAlertBadge(0)).toBeNull();
    expect(formatAlertBadge(3)).toBe('3');
    expect(formatAlertBadge(100)).toBe('99+');
  });

  it('uses the monitor alert palette for active levels', () => {
    expect(applicationTopologyToneColor('critical')).toBe(ALERT_LEVEL_COLORS.critical);
    expect(applicationTopologyToneColor('error')).toBe(ALERT_LEVEL_COLORS.error);
    expect(applicationTopologyToneColor('warning')).toBe(ALERT_LEVEL_COLORS.warning);
    expect(applicationTopologyToneColor('critical')).not.toBe(applicationTopologyToneColor('error'));
  });
});

describe('application topology bands', () => {
  it('places nodes on CMDB bands and drops unclassified nodes', () => {
    const layout = buildApplicationTopologyLayout({
      centerId: CENTER,
      laneWidth: 900,
      nodes: [
        {
          id: CENTER,
          name: '系统甲',
          model_id: 'system',
          app_topo_layer: 'system',
          alert_count: 3,
          max_level: 'critical',
        },
        {
          id: HOST,
          name: 'host-01',
          model_id: 'host',
          app_topo_layer: 'host',
          alert_count: null,
          max_level: null,
        },
        {
          id: CACHE,
          name: '缓存甲',
          model_id: 'redis',
          category: 'cache',
          app_topo_layer: 'appService',
          monitor_id: 'm-1',
          alert_count: 0,
          max_level: null,
        },
        {
          id: HIDDEN,
          name: '未分类',
          model_id: 'custom',
          app_topo_layer: 'none',
          alert_count: 9,
          max_level: 'critical',
        },
      ],
      links: [
        { id: 'a', source: CENTER, target: HOST },
        { id: 'b', source: HOST, target: CACHE },
        { id: 'c', source: CENTER, target: HIDDEN },
      ],
    });

    const byId = Object.fromEntries(layout.nodes.map((node) => [node.id, node]));
    expect(layout.bands.map((band) => band.key)).toEqual([
      'root',
      'service',
      'host',
      'appService',
      'infrastructure',
    ]);
    expect(layout.bands.find((band) => band.key === 'service')?.empty).toBe(true);
    expect(layout.bands.find((band) => band.key === 'infrastructure')?.empty).toBe(true);
    expect(byId[CENTER].layer).toBe('root');
    expect(byId[CENTER].tone).toBe('critical');
    expect(byId[CENTER].badge).toBe('3');
    expect(byId[HOST].layer).toBe('host');
    expect(byId[HOST].tone).toBe('unknown');
    expect(byId[HOST].badge).toBeNull();
    expect(byId[CACHE].layer).toBe('appService');
    expect(byId[CACHE].tone).toBe('normal');
    expect(byId[HIDDEN]).toBeUndefined();
    expect(layout.edges.map((edge) => edge.id)).toEqual(['a', 'b']);
  });

  it('labels associations and bends edges that skip a layer', () => {
    const layout = buildApplicationTopologyLayout({
      centerId: CENTER,
      laneWidth: 900,
      nodes: [
        { id: CENTER, name: '系统甲', model_id: 'system', app_topo_layer: 'system' },
        { id: HOST, name: 'host-01', model_id: 'host', app_topo_layer: 'host' },
      ],
      links: [{ id: 'contains-link', source: CENTER, target: HOST, asst_id: 'contains' }],
    });
    const edge = layout.edges.find((item) => item.id === 'contains-link');
    expect(edge?.label).toBe('contains ↓');
    expect(edge?.points.length).toBeGreaterThan(2);
    expect(edge?.markerEnd).toBe(true);
    expect(edge?.sourceId).toBe(CENTER);
    expect(edge?.targetId).toBe(HOST);
    const service = layout.bands.find((band) => band.key === 'service');
    const host = layout.bands.find((band) => band.key === 'host');
    expect(host && service ? host.top - (service.top + service.height) : 0).toBe(
      APPLICATION_TOPOLOGY_LAYOUT.layerGap,
    );
  });
});

describe('application topology hover', () => {
  const edges = [
    { id: 'system-service', sourceId: 'system', targetId: 'service' },
    { id: 'service-host', sourceId: 'service', targetId: 'host' },
  ];

  it('lights both ends and the relationship when the line is hovered', () => {
    const focus = resolveApplicationTopologyHover({ kind: 'edge', id: 'system-service' }, edges);
    expect([...focus.nodeIds].sort()).toEqual(['service', 'system']);
    expect([...focus.edgeIds]).toEqual(['system-service']);
  });

  it('lights the node, the lines that touch it, and the nodes on the other end', () => {
    const focus = resolveApplicationTopologyHover({ kind: 'node', id: 'service' }, edges);
    expect([...focus.nodeIds].sort()).toEqual(['host', 'service', 'system']);
    expect([...focus.edgeIds].sort()).toEqual(['service-host', 'system-service']);
  });
});
