'use client';

import { useEffect, useRef, useState } from 'react';
import { useArchitectureApi } from '@/app/ops-analysis/api/architecture';
import {
  monitorLinkContextFromPayload,
  type MonitorLinkContext,
} from './links';

export function useArchitectureMonitorLink(monitorId: string): MonitorLinkContext | null {
  const { getMonitorLink } = useArchitectureApi();
  const getMonitorLinkRef = useRef(getMonitorLink);
  getMonitorLinkRef.current = getMonitorLink;
  const [context, setContext] = useState<MonitorLinkContext | null>(null);

  useEffect(() => {
    const id = monitorId.trim();
    setContext(null);
    if (!id) return undefined;
    let cancelled = false;
    getMonitorLinkRef.current(id)
      .then((payload) => {
        if (!cancelled) setContext(monitorLinkContextFromPayload(id, payload));
      })
      .catch(() => {
        if (!cancelled) setContext(null);
      });
    return () => {
      cancelled = true;
    };
  }, [monitorId]);

  return context;
}
