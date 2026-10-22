'use client';

import { useEffect, useState } from 'react';
import useMonitorApi from '@/app/monitor/api';
import { resolveMonitorPublicContext } from '@/app/monitor/components/public/resolveMonitorPublicContext';
import {
  readArchitectureEffectivePlugins,
  type ArchitectureEffectivePlugin,
  type MonitorLinkContext,
} from './links';

/**
 * Resolve the monitor instance with the exported context helper so the request
 * shares that helper's id cache. collect_type stays on this side: the exported
 * plugin list does not carry it, and effective_plugins does.
 */
export function useArchitectureMonitorLink(monitorId: string): MonitorLinkContext | null {
  const { lookupInstance, getEffectivePlugins } = useMonitorApi();
  const [context, setContext] = useState<MonitorLinkContext | null>(null);

  useEffect(() => {
    const id = monitorId.trim();
    setContext(null);
    if (!id) return undefined;
    let cancelled = false;
    let captured: ArchitectureEffectivePlugin[] | null = null;
    resolveMonitorPublicContext(id, {
      lookupInstance: (params) => lookupInstance(params),
      getEffectivePlugins: async (objectId, params) => {
        const plugins = await getEffectivePlugins(objectId, params);
        captured = readArchitectureEffectivePlugins(plugins);
        return plugins;
      },
    })
      .then(async (resolved) => {
        if (cancelled) return;
        let plugins = captured;
        if (!plugins) {
          try {
            plugins = readArchitectureEffectivePlugins(
              await getEffectivePlugins(resolved.monitorObject, { instance_id: id }),
            );
          } catch {
            plugins = [];
          }
        }
        if (!cancelled) {
          setContext({
            monitorObject: resolved.monitorObject,
            monitorName: resolved.monitorName,
            objects: resolved.objects,
            form: resolved.form,
            linkPlugins: plugins,
          });
        }
      })
      .catch(() => {
        if (!cancelled) setContext(null);
      });
    return () => {
      cancelled = true;
    };
  }, [getEffectivePlugins, lookupInstance, monitorId]);

  return context;
}
