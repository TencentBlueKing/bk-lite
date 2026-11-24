'use client';

import { useEffect, useRef, useState } from 'react';
import { useArchitectureApi } from '@/app/ops-analysis/api/architecture';
import { isTransportCanceled } from '@/utils/requestCancellation';
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
    const controller = new AbortController();
    getMonitorLinkRef.current(id, controller.signal)
      .then((payload) => {
        if (!controller.signal.aborted) setContext(monitorLinkContextFromPayload(id, payload));
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted || isTransportCanceled(error)) return;
        setContext(null);
      });
    return () => {
      controller.abort();
    };
  }, [monitorId]);

  return context;
}
