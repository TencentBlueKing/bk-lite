import { describe, expect, it } from 'vitest';
import {
  buildAlarmHref,
  buildMonitorDetailHref,
  buildMonitorHrefFromContext,
  monitorLinkContextFromPayload,
  monitorObjectIdFromContext,
  readArchitectureEffectivePlugins,
} from '../links';

describe('architecture detail links', () => {
  it('builds alarm and monitor links', () => {
    // The alarm entry shares the badge's monitor-caliber source: the monitor
    // alert list filtered by instance id, never the alert-center tickets.
    const alarm = new URL(buildAlarmHref('mon-web'), 'http://local');
    expect(alarm.pathname).toBe('/monitor/event/alert');
    expect(alarm.searchParams.get('instanceId')).toBe('mon-web');
    expect(alarm.searchParams.get('objId')).toBeNull();
    const alarmWithObject = new URL(buildAlarmHref('mon-web', '11'), 'http://local');
    expect(alarmWithObject.searchParams.get('instanceId')).toBe('mon-web');
    expect(alarmWithObject.searchParams.get('objId')).toBe('11');

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

    expect(monitorObjectIdFromContext(null)).toBe('');
    expect(monitorObjectIdFromContext({ monitorObject: 11, monitorName: 'Host' })).toBe('11');
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

  it('maps the ops-analysis monitor link payload onto a specialized dashboard', () => {
    expect(monitorLinkContextFromPayload('mon-web', null)).toBeNull();
    expect(monitorLinkContextFromPayload('mon-web', {
      monitor_object: null,
      instance: null,
      plugins: [],
    })).toBeNull();
    const context = monitorLinkContextFromPayload('app3d-demo-host-01', {
      monitor_object: {
        id: 11,
        name: 'Host',
        display_name: '主机',
        instance_id_keys: ['instance_id'],
      },
      instance: {
        instance_id: "('app3d-demo-host-01',)",
        instance_name: 'web-01',
        instance_id_values: ['app3d-demo-host-01'],
        instance_id_keys: ['instance_id'],
      },
      plugins: [{ id: 7, name: 'Host', collect_type: 'netflow', display_name: '主机' }],
    });
    const href = new URL(buildMonitorHrefFromContext(context), 'http://local');
    expect(context?.form?.instance_id).toBe('app3d-demo-host-01');
    expect(context?.monitorName).toBe('Host');
    expect(href.pathname).toBe('/monitor/view/dashboard/netflow');
    expect(href.searchParams.get('monitorObjId')).toBe('11');
    expect(href.searchParams.get('instance_id')).toBe('app3d-demo-host-01');
    expect(href.searchParams.get('instance_name')).toBe('web-01');
  });
});
