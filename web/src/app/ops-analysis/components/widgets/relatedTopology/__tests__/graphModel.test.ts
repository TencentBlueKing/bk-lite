import { describe, expect, it } from 'vitest';
import {
  alertBadgeFill,
  alertCardStroke,
  ALERT_CARD_STROKE_WIDTH,
  buildRelatedTopologyGraph,
  formatAlertBadgeText,
  isEmptyRelatedTopology,
  resolveAssociationLabel,
} from '../graphModel';
import { RELATED_TOPOLOGY_VISUAL } from '../visual';
import { cssVariableMap, legacyVariableMap } from '@/theme/css-adapter';
import type { RelatedTopologyResponse } from '../types';

function isRegisteredThemeVar(value: string) {
  const name = value.match(/^var\((--[a-z0-9-]+)\)$/i)?.[1];
  if (!name) {
    return false;
  }
  return (
    Object.prototype.hasOwnProperty.call(legacyVariableMap, name)
    || Object.values(cssVariableMap).includes(name as `--${string}`)
  );
}

const CENTER = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const NEIGHBOR = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const INTERFACE = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc';
const PEER = 'dddddddd-dddd-4ddd-8ddd-dddddddddddd';

const payload = (
  overrides: Partial<RelatedTopologyResponse> = {},
): RelatedTopologyResponse => ({
  center_inst_uuid: CENTER,
  src_result: {
    inst_uuid: CENTER,
    inst_name: 'core-host',
    model_id: 'host',
    model_name: '主机',
    monitor_id: 'mon-center',
    alert_count: 3,
    max_level: 'error',
    children: [
      {
        inst_uuid: NEIGHBOR,
        inst_name: 'edge-switch',
        model_id: 'switch',
        model_name: '交换机',
        asst_id: 'connect',
        asst_name: '连接',
        monitor_id: '',
        alert_count: null,
        max_level: null,
        children: [],
      },
    ],
  },
  dst_result: {
    inst_uuid: CENTER,
    inst_name: 'core-host',
    model_id: 'host',
    model_name: '主机',
    monitor_id: 'mon-center',
    alert_count: 3,
    max_level: 'error',
    children: [],
  },
  ...overrides,
});

describe('formatAlertBadgeText', () => {
  it('hides unmapped and quiet nodes, and caps at 99+', () => {
    expect(formatAlertBadgeText(null)).toBeNull();
    expect(formatAlertBadgeText(0)).toBeNull();
    expect(formatAlertBadgeText(12)).toBe('12');
    expect(formatAlertBadgeText(99)).toBe('99');
    expect(formatAlertBadgeText(100)).toBe('99+');
  });
});

describe('alertBadgeFill', () => {
  it('uses fail token for critical/error and warning otherwise', () => {
    expect(alertBadgeFill('critical')).toBe('var(--color-fail)');
    expect(alertBadgeFill('error')).toBe('var(--color-fail)');
    expect(alertBadgeFill('warning')).toBe('var(--color-warning)');
  });

  it('only uses CSS variables that the theme adapter actually emits', () => {
    expect(isRegisteredThemeVar(alertBadgeFill('error'))).toBe(true);
    expect(isRegisteredThemeVar(alertBadgeFill('warning'))).toBe(true);
  });
});

describe('alertCardStroke', () => {
  it('tints the card outline with the badge color and keeps a 1px stroke', () => {
    expect(alertCardStroke(null, 'error')).toBeNull();
    expect(alertCardStroke(0, 'warning')).toBeNull();
    expect(alertCardStroke(2, 'error')).toEqual({
      stroke: 'var(--color-fail)',
      strokeWidth: ALERT_CARD_STROKE_WIDTH,
    });
    expect(alertCardStroke(1, 'warning')).toEqual({
      stroke: 'var(--color-warning)',
      strokeWidth: ALERT_CARD_STROKE_WIDTH,
    });
    expect(ALERT_CARD_STROKE_WIDTH).toBe(1);
    expect(ALERT_CARD_STROKE_WIDTH).toBeLessThan(
      RELATED_TOPOLOGY_VISUAL.card.activeBody.strokeWidth,
    );
  });
});

describe('buildRelatedTopologyGraph', () => {
  it('keeps a single center, left neighbor, and unmapped vs noisy badge state', () => {
    const graph = buildRelatedTopologyGraph(payload());
    expect(graph.empty).toBe(false);
    expect(graph.nodes.map((node) => node.id)).toEqual([CENTER, NEIGHBOR]);
    const center = graph.nodes.find((node) => node.id === CENTER)!;
    const neighbor = graph.nodes.find((node) => node.id === NEIGHBOR)!;
    expect(center.isCenter).toBe(true);
    expect(center.x).toBe(0);
    expect(neighbor.x).toBeLessThan(0);
    expect(formatAlertBadgeText(center.alertCount)).toBe('3');
    expect(formatAlertBadgeText(neighbor.alertCount)).toBeNull();
    expect(neighbor.monitorId).toBe('');
    expect(center.modelName).toBe('主机');
    expect(neighbor.modelName).toBe('交换机');
    expect(graph.edges[0]).toMatchObject({
      source: CENTER,
      target: NEIGHBOR,
      label: '连接',
    });
  });

  it('uses CMDB dst arrow direction: child points back to parent', () => {
    const graph = buildRelatedTopologyGraph(
      payload({
        src_result: {
          inst_uuid: CENTER,
          inst_name: 'test_2',
          model_id: 'switch',
          model_name: '交换机',
          children: [],
        },
        dst_result: {
          inst_uuid: CENTER,
          inst_name: 'test_2',
          model_id: 'switch',
          model_name: '交换机',
          children: [
            {
              inst_uuid: INTERFACE,
              inst_name: 'test_2',
              model_id: 'interface',
              model_name: '网络设备接口',
              asst_id: 'belong',
              asst_name: '属于',
              children: [
                {
                  inst_uuid: PEER,
                  inst_name: '123',
                  model_id: 'interface',
                  model_name: '网络设备接口',
                  asst_id: 'connect',
                  asst_name: '关联',
                  children: [],
                },
              ],
            },
          ],
        },
      }),
    );
    expect(graph.edges).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          source: INTERFACE,
          target: CENTER,
          label: '属于',
        }),
        expect.objectContaining({
          source: PEER,
          target: INTERFACE,
          label: '关联',
        }),
      ]),
    );
  });

  it('translates asst_id to the same Chinese labels as CMDB when asst_name is absent', () => {
    expect(resolveAssociationLabel('', 'belong')).toBe('属于');
    expect(resolveAssociationLabel(null, 'contains')).toBe('包含');
    expect(resolveAssociationLabel('连接', 'connect')).toBe('连接');
  });

  it('marks empty associations when both sides have no children', () => {
    const emptyPayload = payload({
      src_result: {
        inst_uuid: CENTER,
        inst_name: 'core-host',
        children: [],
      },
      dst_result: {
        inst_uuid: CENTER,
        inst_name: 'core-host',
        children: [],
      },
    });
    expect(isEmptyRelatedTopology(emptyPayload)).toBe(true);
    expect(buildRelatedTopologyGraph(emptyPayload).empty).toBe(true);
    expect(buildRelatedTopologyGraph(emptyPayload).nodes).toHaveLength(1);
  });

  it('does not treat count 0 as unmapped', () => {
    const quiet = payload({
      src_result: {
        inst_uuid: CENTER,
        inst_name: 'core-host',
        monitor_id: 'mon-center',
        alert_count: 0,
        max_level: null,
        children: [],
      },
      dst_result: {},
    });
    const graph = buildRelatedTopologyGraph(quiet);
    expect(graph.nodes[0].monitorId).toBe('mon-center');
    expect(graph.nodes[0].alertCount).toBe(0);
    expect(formatAlertBadgeText(graph.nodes[0].alertCount)).toBeNull();
  });

  it('keeps column and row gaps larger than the card so nodes cannot overlap', () => {
    expect(RELATED_TOPOLOGY_VISUAL.rowGap).toBeGreaterThan(
      RELATED_TOPOLOGY_VISUAL.nodeHeight,
    );
    expect(RELATED_TOPOLOGY_VISUAL.columnGap).toBeGreaterThan(
      RELATED_TOPOLOGY_VISUAL.nodeWidth,
    );
    const graph = buildRelatedTopologyGraph(payload());
    const neighbor = graph.nodes.find((node) => node.id === NEIGHBOR)!;
    expect(neighbor.x).toBe(-RELATED_TOPOLOGY_VISUAL.columnGap);
  });

  it('reuses the system topology canvas, grid, and card chrome', () => {
    expect(RELATED_TOPOLOGY_VISUAL.canvas.background).toContain('radial-gradient');
    expect(RELATED_TOPOLOGY_VISUAL.grid.color).toContain('116, 145, 181');
    expect(RELATED_TOPOLOGY_VISUAL.card.defaultBody.filter).toContain('drop-shadow');
    expect(RELATED_TOPOLOGY_VISUAL.card.activeBody.stroke).toBe('#0070fa');
  });
});
