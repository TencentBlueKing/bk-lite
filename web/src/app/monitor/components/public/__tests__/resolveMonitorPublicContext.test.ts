import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  objectsFromMonitorLookup,
  resetMonitorPublicContextCache,
  resolveMonitorPublicContext,
} from '../resolveMonitorPublicContext';

const hostLookup = {
  monitor_object: {
    id: 46,
    name: 'Host',
    display_name: '主机',
    instance_id_keys: ['instance_id'],
  },
  instance: {
    instance_id: "('app3d-demo-host-01',)",
    instance_name: 'web-1',
    instance_id_values: ['app3d-demo-host-01'],
    instance_id_keys: ['instance_id'],
  },
};

describe('resolveMonitorPublicContext', () => {
  afterEach(() => {
    resetMonitorPublicContextCache();
  });

  it('bootstraps object, plugins, and instance form from monitorId only', async () => {
    const lookupInstance = vi.fn(async () => ({
      monitor_object: {
        id: 11,
        name: 'Host',
        display_name: '主机',
        instance_id_keys: ['instance_id'],
      },
      instance: {
        instance_id: 'mon-1',
        instance_name: 'web-1',
        instance_id_values: ['web-1'],
        instance_id_keys: ['instance_id'],
      },
    }));
    const getEffectivePlugins = vi.fn(async () => [
      { id: 7, name: 'Host', display_name: '主机' },
    ]);

    const context = await resolveMonitorPublicContext('mon-1', {
      lookupInstance,
      getEffectivePlugins,
    });

    expect(context).toEqual({
      monitorObject: 11,
      monitorName: 'Host',
      plugins: [{ label: '主机', value: '7' }],
      objects: [
        {
          id: 11,
          name: 'Host',
          display_name: '主机',
          type: '',
          description: '',
          icon: undefined,
        },
      ],
      form: {
        instance_id: 'mon-1',
        instance_name: 'web-1',
        instance_id_values: ['web-1'],
        instance_id_keys: ['instance_id'],
        title: 'web-1',
        dimensions: [],
        showInstName: false,
      },
    });
    expect(lookupInstance).toHaveBeenCalledTimes(1);
    expect(lookupInstance).toHaveBeenCalledWith({ instance_id: 'mon-1' });
    expect(getEffectivePlugins).toHaveBeenCalledTimes(1);
  });

  it('does not probe instance list per monitor object type', async () => {
    const lookupInstance = vi.fn(async () => hostLookup);
    const getEffectivePlugins = vi.fn(async () => [
      { id: 7, name: 'Host', display_name: '主机' },
    ]);

    const context = await resolveMonitorPublicContext('app3d-demo-host-01', {
      lookupInstance,
      getEffectivePlugins,
    });

    expect(context.monitorObject).toBe(46);
    expect(lookupInstance).toHaveBeenCalledTimes(1);
    expect(getEffectivePlugins).toHaveBeenCalledTimes(1);
    expect(getEffectivePlugins).toHaveBeenCalledWith(46, {
      instance_id: 'app3d-demo-host-01',
    });
    expect(context.plugins).toEqual([{ label: '主机', value: '7' }]);
  });

  it('drops plugins without id so the view does not send a name as monitor_plugin_id', async () => {
    const lookupInstance = vi.fn(async () => hostLookup);
    const context = await resolveMonitorPublicContext('app3d-demo-host-01', {
      lookupInstance,
      getEffectivePlugins: async () => [
        { name: 'Host', display_name: '主机' },
        { id: 12, name: 'Host', display_name: '主机' },
      ],
    });
    expect(context.plugins).toEqual([{ label: '主机', value: '12' }]);
  });

  it('fails closed when the instance does not exist', async () => {
    const lookupInstance = vi.fn(async () => null);
    await expect(
      resolveMonitorPublicContext('missing', {
        lookupInstance,
        getEffectivePlugins: async () => [],
      }),
    ).rejects.toThrow('not_found');
    expect(lookupInstance).toHaveBeenCalledTimes(1);
  });

  it('shares one in-flight lookup for the same monitorId', async () => {
    let release: ((value: typeof hostLookup) => void) | undefined;
    const lookupInstance = vi.fn(
      () =>
        new Promise<typeof hostLookup>((resolve) => {
          release = resolve;
        }),
    );
    const apis = {
      lookupInstance,
      getEffectivePlugins: vi.fn(async () => [
        { id: 7, name: 'Host', display_name: '主机' },
      ]),
    };

    const first = resolveMonitorPublicContext('shared-1', apis);
    const second = resolveMonitorPublicContext('shared-1', apis);
    await Promise.resolve();
    expect(lookupInstance).toHaveBeenCalledTimes(1);

    release?.(hostLookup);
    await Promise.all([first, second]);
    expect(lookupInstance).toHaveBeenCalledTimes(1);
  });

  it('reuses a completed lookup for the same monitorId until refresh', async () => {
    const lookupInstance = vi.fn(async () => hostLookup);
    const apis = {
      lookupInstance,
      getEffectivePlugins: vi.fn(async () => [
        { id: 7, name: 'Host', display_name: '主机' },
      ]),
    };

    await resolveMonitorPublicContext('cached-1', apis);
    await resolveMonitorPublicContext('cached-1', apis);
    expect(lookupInstance).toHaveBeenCalledTimes(1);

    await resolveMonitorPublicContext('cached-1', apis, { refresh: true });
    expect(lookupInstance).toHaveBeenCalledTimes(2);
  });

  it('builds a one-object list from lookup metadata', () => {
    expect(objectsFromMonitorLookup(undefined)).toEqual([]);
    expect(
      objectsFromMonitorLookup({
        id: 46,
        name: 'Host',
        display_name: '主机',
      }),
    ).toEqual([
      {
        id: 46,
        name: 'Host',
        display_name: '主机',
        type: '',
        description: '',
        icon: undefined,
      },
    ]);
  });
});
