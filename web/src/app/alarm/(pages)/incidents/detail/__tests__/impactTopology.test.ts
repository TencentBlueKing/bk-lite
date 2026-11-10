import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import {
  buildImpactGraph,
  collectSeedUuids,
  IMPACT_NODE_WIDTH,
  type ImpactAlertRef,
} from '../impactTopology';

const here = dirname(fileURLToPath(import.meta.url));
const HOST = '00000000-0000-4000-8000-000000000001';
const APP = '00000000-0000-4000-8000-000000000003';
const SYSTEM = '00000000-0000-4000-8000-000000000020';

function alert(partial: ImpactAlertRef): ImpactAlertRef {
  return partial;
}

describe('incident impact topology merge', () => {
  it('sends each cmdb id once', () => {
    expect(collectSeedUuids([
      alert({
        id: 1,
        monitor_objects: [{ cmdb_id: HOST.toUpperCase() }, { cmdb_id: HOST }, { cmdb_id: '' }],
      }),
      alert({ id: 2, monitor_objects: [{ cmdb_id: HOST }] }),
    ])).toEqual([HOST]);
  });

  it('merges one node per uuid and keeps the more severe level', () => {
    const model = buildImpactGraph(
      [
        alert({
          id: 1,
          title: '超时',
          level: 2,
          monitor_objects: [{ cmdb_id: HOST, resource_type: '主机', resource_name: 'web-01' }],
        }),
        alert({
          id: 2,
          title: '宕机',
          level: '0',
          monitor_objects: [
            { cmdb_id: HOST, resource_type: '主机', resource_name: 'web-01' },
            { cmdb_id: null, resource_type: '进程', resource_name: '未绑定' },
          ],
        }),
      ],
      {
        relation_status: 'ok',
        nodes: [{ inst_uuid: HOST, inst_name: 'web-01', layer: 'host', role: 'seed', found: true }],
        links: [],
      },
      [
        { level_id: 0, level_display_name: '严重' },
        { level_id: 2, level_display_name: '警告' },
      ],
      { 0: '#aa0000', 2: '#ffaa00' },
    );
    const host = model.nodes.find((node) => node.id === HOST);
    const unbound = model.nodes.find((node) => node.kind === 'unbound');
    expect(model.nodes.filter((node) => node.id === HOST)).toHaveLength(1);
    expect(host?.detail).toBe('2 条告警');
    expect(host?.color).toBe('#aa0000');
    expect(host?.levelName).toBe('严重');
    expect(host?.alerts.map((item) => item.title)).toEqual(['超时', '宕机']);
    expect(unbound?.label).toBe('未绑定');
    expect(model.edges.some((edge) => edge.source === unbound?.id || edge.target === unbound?.id)).toBe(false);
  });

  it('places system above host and does not count child alerts on a bridge', () => {
    const model = buildImpactGraph(
      [
        alert({
          id: 1,
          title: '主机告警',
          level: 1,
          monitor_objects: [{ cmdb_id: HOST, resource_type: '主机', resource_name: 'web-01' }],
        }),
        alert({
          id: 2,
          title: '系统告警',
          level: 1,
          monitor_objects: [{ cmdb_id: SYSTEM, resource_type: '系统', resource_name: '交易' }],
        }),
        alert({
          id: 3,
          title: '主机告警',
          level: 1,
          monitor_objects: [{ cmdb_id: HOST, resource_name: 'web-01' }],
        }),
      ],
      {
        relation_status: 'ok',
        nodes: [
          { inst_uuid: SYSTEM, inst_name: '交易', layer: 'system', role: 'seed', found: true },
          { inst_uuid: HOST, inst_name: 'web-01', layer: 'host', role: 'seed', found: true },
          { inst_uuid: APP, inst_name: '支付中台', layer: 'service', role: 'bridge', found: true },
        ],
        links: [
          {
            src_inst_uuid: APP,
            dst_inst_uuid: HOST,
            asst_id: 'run',
            asst_name: '运行于',
            model_asst_id: 'application_run_host',
          },
        ],
      },
    );
    const system = model.nodes.find((node) => node.id === SYSTEM);
    const host = model.nodes.find((node) => node.id === HOST);
    const bridge = model.nodes.find((node) => node.id === APP);
    expect(system && host && system.y < host.y).toBe(true);
    expect(bridge?.detail).toBe('桥接');
    expect(bridge?.color).toBeNull();
    expect(bridge?.linkedObjects.map((item) => item.label)).toEqual(['web-01']);
    expect(bridge?.linkedObjects[0].alerts.map((item) => item.id)).toEqual([1, 3]);
    expect(host?.detail).toBe('2 条告警');
    expect(host?.relations).toEqual(['支付中台 运行于 web-01']);
  });

  it('draws no graph when cmdb is not purchased', () => {
    const model = buildImpactGraph(
      [alert({ id: 1, title: '超时', monitor_objects: [{ cmdb_id: HOST, resource_name: 'web-01' }] })],
      { relation_status: 'not_purchased', message: '未购买 CMDB', nodes: [], links: [] },
    );
    expect(model.mode).toBe('not_purchased');
    expect(model.nodes).toEqual([]);
    expect(model.message).toBe('未购买 CMDB');
  });

  it('keeps snapshot nodes and drops bridges when relations are unavailable or truncated', () => {
    const alerts = [alert({
      id: 1,
      title: '超时',
      monitor_objects: [{ cmdb_id: HOST, resource_type: '主机', resource_name: 'web-01' }],
    })];
    const unavailable = buildImpactGraph(alerts, {
      relation_status: 'unavailable',
      message: '配置关系暂时查不到',
      nodes: [{ inst_uuid: APP, inst_name: '支付中台', role: 'bridge', found: true }],
      links: [],
    });
    expect(unavailable.nodes.map((node) => node.label)).toEqual(['web-01']);
    expect(unavailable.edges).toEqual([]);
    expect(unavailable.hint).toBe('配置关系暂时查不到');

    const truncated = buildImpactGraph(alerts, {
      relation_status: 'ok',
      truncated: true,
      nodes: [{ inst_uuid: HOST, found: false, role: 'seed' }],
      links: [],
    });
    expect(truncated.nodes[0].label).toBe('web-01');
    expect(truncated.hint).toBe('关系未展开');
    expect(truncated.edges).toEqual([]);
  });

  it('uses the alert title when there are no monitor objects and does not merge equal names', () => {
    const model = buildImpactGraph([
      alert({ id: 1, title: '同名', resource_name: '裸对象' }),
      alert({ id: 2, title: '另一条', resource_name: '裸对象' }),
      alert({ id: 3, title: '只有标题', resource_type: '主机', resource_name: '' }),
    ], { relation_status: 'ok', nodes: [], links: [] });
    expect(model.nodes).toHaveLength(3);
    expect(model.nodes.map((node) => node.id)).toEqual(['unbound:1:0', 'unbound:2:0', 'unbound:3:0']);
    expect(model.nodes.map((node) => node.label)).toEqual(['裸对象', '裸对象', '只有标题']);
    expect(model.hint).toBe('这些告警没有绑定 CMDB 对象');
  });

  it('centers a shorter layer on the widest layer', () => {
    const hostB = '00000000-0000-4000-8000-000000000004';
    const model = buildImpactGraph(
      [
        alert({ id: 1, title: '应用', level: 1, monitor_objects: [{ cmdb_id: APP, resource_name: 'app' }] }),
        alert({ id: 2, title: '主机1', level: 1, monitor_objects: [{ cmdb_id: HOST, resource_name: 'h1' }] }),
        alert({ id: 3, title: '主机2', level: 1, monitor_objects: [{ cmdb_id: hostB, resource_name: 'h2' }] }),
      ],
      {
        relation_status: 'ok',
        nodes: [
          { inst_uuid: APP, inst_name: 'app', layer: 'service', role: 'seed', found: true },
          { inst_uuid: HOST, inst_name: 'h1', layer: 'host', role: 'seed', found: true },
          { inst_uuid: hostB, inst_name: 'h2', layer: 'host', role: 'seed', found: true },
        ],
        links: [],
      },
    );
    const app = model.nodes.find((node) => node.id === APP);
    const hosts = model.nodes.filter((node) => node.layer === 'host').sort((a, b) => a.x - b.x);
    const appCenter = (app?.x || 0) + IMPACT_NODE_WIDTH / 2;
    const hostCenter = hosts[0].x + (hosts[1].x + IMPACT_NODE_WIDTH - hosts[0].x) / 2;
    expect(appCenter).toBe(hostCenter);
  });

  it('keeps the page on the alarm api and the three alert views', () => {
    const page = readFileSync(resolve(here, '../page.tsx'), 'utf8');
    const api = readFileSync(resolve(here, '../../../../api/incidents.ts'), 'utf8');
    expect(page).toContain("t('incidents.impactTopology')");
    expect(page).toContain("t('incidents.refreshTopology')");
    expect(page).toContain("value: 'topology'");
    expect(page).toContain('getImpactTopology');
    expect(page).not.toMatch(/from ['"]@\/app\/cmdb/);
    expect(api).toContain('/impact_topology/');
    expect(api).toContain('suppressErrorNotification: true');
  });
});
