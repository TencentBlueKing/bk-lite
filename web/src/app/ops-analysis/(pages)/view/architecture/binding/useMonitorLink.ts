'use client';

import { useEffect, useState } from 'react';
import useMonitorApi from '@/app/monitor/api';
import { resolveMonitorPublicContext } from '@/app/monitor/components/public/resolveMonitorPublicContext';
import {
  readArchitectureEffectivePlugins,
  type ArchitectureEffectivePlugin,
  type MonitorLinkContext,
} from './links';

export interface ArchitectureMonitorLinkApis {
  lookupInstance: (params: { instance_id: string }) => Promise<unknown>;
  getEffectivePlugins: (
    objectId?: unknown,
    params?: { instance_id?: string },
  ) => Promise<unknown>;
}

/**
 * Resolve the monitor instance with the exported context helper so the request
 * shares that helper's id cache. collect_type stays on this side: the exported
 * plugin list does not carry it, and effective_plugins does.
 *
 * Shared by the hover prefetch hook and the click fallback: a slow first
 * click may still be resolving when the drawer opens a monitor or alert link.
 */
export async function resolveArchitectureMonitorContext(
  monitorId: string,
  apis: ArchitectureMonitorLinkApis,
): Promise<MonitorLinkContext | null> {
  const id = monitorId.trim();
  if (!id) return null;
  let captured: ArchitectureEffectivePlugin[] | null = null;
  try {
    const resolved = await resolveMonitorPublicContext(id, {
      lookupInstance: (params) => apis.lookupInstance(params),
      getEffectivePlugins: async (objectId, params) => {
        const plugins = await apis.getEffectivePlugins(objectId, params);
        captured = readArchitectureEffectivePlugins(plugins);
        return plugins as Array<{ id?: string | number; name?: string; display_name?: string }>;
      },
    });
    let plugins = captured;
    if (!plugins) {
      try {
        plugins = readArchitectureEffectivePlugins(
          await apis.getEffectivePlugins(resolved.monitorObject, { instance_id: id }),
        );
      } catch {
        plugins = [];
      }
    }
    return {
      monitorObject: resolved.monitorObject,
      monitorName: resolved.monitorName,
      objects: resolved.objects,
      form: resolved.form,
      linkPlugins: plugins,
    };
  } catch {
    return null;
  }
}

export function useArchitectureMonitorLink(monitorId: string): MonitorLinkContext | null {
  const { lookupInstance, getEffectivePlugins } = useMonitorApi();
  const [context, setContext] = useState<MonitorLinkContext | null>(null);

  useEffect(() => {
    const id = monitorId.trim();
    setContext(null);
    if (!id) return undefined;
    let cancelled = false;
    resolveArchitectureMonitorContext(id, { lookupInstance, getEffectivePlugins }).then(
      (resolved) => {
        if (!cancelled) setContext(resolved);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [getEffectivePlugins, lookupInstance, monitorId]);

  return context;
}
