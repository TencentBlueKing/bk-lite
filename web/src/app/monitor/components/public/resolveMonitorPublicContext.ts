import type { Key } from 'react';
import type { ChartProps, ObjectItem } from '@/app/monitor/types';
import type { ViewPluginOption } from '@/app/monitor/types/view';
import { sameMonitorId } from '@/app/monitor/utils/monitorIds';
import { formatMonitorViewPluginTabs } from '@/app/monitor/utils/monitorViewPlugins';

export interface MonitorPublicContext {
  monitorObject: Key;
  monitorName: string;
  plugins: ViewPluginOption[];
  form: ChartProps;
  objects: ObjectItem[];
}

interface MonitorInstanceRow {
  instance_id?: string;
  instance_name?: string;
  name?: string;
  instance_id_values?: string[];
  instance_id_keys?: string[];
}

export interface MonitorInstanceLookup {
  monitor_object?: {
    id?: Key;
    name?: string;
    display_name?: string;
    icon?: string;
    instance_id_keys?: string[];
  };
  instance?: MonitorInstanceRow;
}

interface MonitorPublicApis {
  lookupInstance: (params: {
    instance_id: string;
  }) => Promise<MonitorInstanceLookup | null | undefined>;
  getEffectivePlugins: (
    objectId?: Key,
    params?: { instance_id?: string },
  ) => Promise<Array<{ id?: Key; name?: string; display_name?: string }>>;
}

export function objectsFromMonitorLookup(
  object: MonitorInstanceLookup['monitor_object'],
): ObjectItem[] {
  if (object?.id == null) {
    return [];
  }
  return [
    {
      id: Number(object.id),
      name: String(object.name || object.display_name || ''),
      display_name: String(object.display_name || object.name || ''),
      type: '',
      description: '',
      icon: object.icon,
    },
  ];
}

const pickInstance = (
  rows: MonitorInstanceRow[] | undefined,
  monitorId: string,
): MonitorInstanceRow | undefined => {
  const list = rows || [];
  return (
    list.find((row) => sameMonitorId(row.instance_id, monitorId)) ||
    list.find((row) =>
      (row.instance_id_values || []).some((value) =>
        sameMonitorId(value, monitorId),
      ),
    ) ||
    (list.length === 1 ? list[0] : undefined)
  );
};

const inflight = new Map<string, Promise<MonitorPublicContext>>();
const results = new Map<string, MonitorPublicContext>();

export function resetMonitorPublicContextCache() {
  inflight.clear();
  results.clear();
}

export async function resolveMonitorPublicContext(
  monitorId: string,
  apis: MonitorPublicApis,
  options: { refresh?: boolean } = {},
): Promise<MonitorPublicContext> {
  const id = monitorId.trim();
  if (!id) {
    throw new Error('not_found');
  }
  if (!options.refresh) {
    const cached = results.get(id);
    if (cached) {
      return cached;
    }
    const pending = inflight.get(id);
    if (pending) {
      return pending;
    }
  }
  const request = resolveMonitorPublicContextOnce(id, apis)
    .then((context) => {
      results.set(id, context);
      return context;
    })
    .finally(() => {
      if (inflight.get(id) === request) {
        inflight.delete(id);
      }
    });
  inflight.set(id, request);
  return request;
}

async function resolveMonitorPublicContextOnce(
  id: string,
  apis: MonitorPublicApis,
): Promise<MonitorPublicContext> {
  const lookup = await apis.lookupInstance({ instance_id: id });
  const object = lookup?.monitor_object;
  const instance = pickInstance(
    lookup?.instance ? [lookup.instance] : undefined,
    id,
  );
  if (object?.id == null || !instance) {
    throw new Error('not_found');
  }
  const plugins = await apis.getEffectivePlugins(object.id, {
    instance_id: id,
  });
  const instanceName = String(instance.instance_name || instance.name || id);
  const instanceIdKeys =
    Array.isArray(instance.instance_id_keys) && instance.instance_id_keys.length
      ? instance.instance_id_keys
      : Array.isArray(object.instance_id_keys) &&
          object.instance_id_keys.length
        ? object.instance_id_keys
        : ['instance_id'];
  return {
    monitorObject: object.id,
    monitorName: String(object.name || object.display_name || ''),
    plugins: formatMonitorViewPluginTabs(plugins),
    objects: objectsFromMonitorLookup(object),
    form: {
      instance_id: id,
      instance_name: instanceName,
      instance_id_values:
        Array.isArray(instance.instance_id_values) &&
        instance.instance_id_values.length
          ? instance.instance_id_values
          : [id],
      instance_id_keys: instanceIdKeys,
      title: instanceName,
      dimensions: [],
      showInstName: false,
    },
  };
}
