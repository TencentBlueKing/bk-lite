import { describe, expect, it } from 'vitest';
import {
  buildAlarmHref,
  buildCmdbDetailHref,
  buildMonitorDetailHref,
  buildMonitorHrefFromContext,
  readArchitectureEffectivePlugins,
} from '../links';

describe('architecture detail links', () => {
  it('builds cmdb, alarm and monitor links', () => {
    const cmdb = new URL(buildCmdbDetailHref({
      modelId: 'host',
      instUuid: 'uuid-web',
      instName: 'web-01',
    }), 'http://local');
    expect(cmdb.pathname).toBe('/cmdb/assetData/detail/baseInfo');
    expect(cmdb.searchParams.get('model_id')).toBe('host');
    expect(cmdb.searchParams.get('inst_uuid')).toBe('uuid-web');
    expect(cmdb.searchParams.get('inst_name')).toBe('web-01');

    const alarm = new URL(buildAlarmHref('mon-web'), 'http://local');
    expect(alarm.pathname).toBe('/alarm/alarms');
    expect(alarm.searchParams.get('resource_id')).toBe('mon-web');

    const monitor = new URL(buildMonitorDetailHref({
      monitorObjectId: '11',
      name: 'zz-unlisted-object',
      displayName: 'zz-unlisted-object',
      instanceId: 'mon-web',
      instanceName: 'web-01',
      instanceIdValues: ['web-01'],
      instanceIdKeys: ['instance_id'],
    }), 'http://local');
    expect(monitor.pathname).toBe('/monitor/view/detail');
    expect(monitor.searchParams.get('monitorObjId')).toBe('11');
    expect(monitor.searchParams.get('instance_id')).toBe('mon-web');
    expect(monitor.searchParams.get('instance_name')).toBe('web-01');
    expect(monitor.searchParams.get('return_object_id')).toBe('11');

    expect(buildMonitorHrefFromContext(null)).toBe('');
    expect(buildMonitorHrefFromContext({
      monitorObject: '',
      monitorName: 'Host',
      form: { instance_id: 'mon-web' },
    })).toBe('');
    const fromContext = new URL(buildMonitorHrefFromContext({
      monitorObject: 11,
      monitorName: 'zz-unlisted-object',
      objects: [{ display_name: '未登记对象' }],
      form: {
        instance_id: 'mon-web',
        instance_name: 'web-01',
        instance_id_values: ['web-01'],
        instance_id_keys: ['instance_id'],
      },
    }), 'http://local');
    expect(fromContext.pathname).toBe('/monitor/view/detail');
    expect(fromContext.searchParams.get('instance_id')).toBe('mon-web');
    expect(fromContext.searchParams.get('monitorObjDisplayName')).toBe('未登记对象');
    const professional = new URL(buildMonitorHrefFromContext({
      monitorObject: 11,
      monitorName: 'Host',
      objects: [{ display_name: '主机' }],
      form: { instance_id: 'mon-web', instance_name: 'web-01' },
    }), 'http://local');
    expect(professional.pathname).toBe('/monitor/view/dashboard/host');

    const plugins = readArchitectureEffectivePlugins([
      { id: 7, name: 'Host', display_name: '主机', collect_type: 'netflow' },
      'skip',
    ]);
    expect(plugins).toEqual([{ collect_type: 'netflow', name: 'Host' }]);
    const flow = new URL(buildMonitorHrefFromContext({
      monitorObject: 11,
      monitorName: 'Host',
      objects: [{ display_name: '主机' }],
      form: { instance_id: 'mon-web', instance_name: 'web-01' },
      linkPlugins: plugins,
    }), 'http://local');
    expect(flow.pathname).toBe('/monitor/view/dashboard/netflow');
    expect(readArchitectureEffectivePlugins({ items: [] })).toEqual([]);
  });
});
