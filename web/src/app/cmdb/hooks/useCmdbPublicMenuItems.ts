'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useInstanceApi } from '@/app/cmdb/api';
import { resolveCmdbInstUuid } from '@/app/cmdb/utils/instUuid';
import { resolveCmdbPublicMenuItems } from '@/app/cmdb/utils/cmdbPublicMenus';
import { useAppWidget } from '@/context/appCapabilities';
import type { AppWidgetKey } from '@/context/appCapabilities';

export function useCmdbPublicMenuItems() {
  const searchParams = useSearchParams();
  const modelId = searchParams.get('model_id') || '';
  const instUuid = resolveCmdbInstUuid(searchParams.get('inst_uuid')) || '';
  const { getInstanceDetail } = useInstanceApi();
  const instanceApiRef = useRef({ getInstanceDetail });
  instanceApiRef.current = { getInstanceDetail };
  const monitorView = useAppWidget('monitor.monitorView');
  const alertList = useAppWidget('monitor.alertList');
  const monitorPolicy = useAppWidget('monitor.monitorPolicy');
  const nodeStatus = useAppWidget('node.nodeStatus');
  const [monitorId, setMonitorId] = useState('');
  const [nodeId, setNodeId] = useState('');

  useEffect(() => {
    if (!instUuid) {
      setMonitorId('');
      setNodeId('');
      return;
    }
    let cancelled = false;
    instanceApiRef.current.getInstanceDetail(instUuid)
      .then((detail: { monitor_id?: string; node_id?: string }) => {
        if (!cancelled) {
          setMonitorId(String(detail?.monitor_id || '').trim());
          setNodeId(String(detail?.node_id || '').trim());
        }
      })
      .catch(() => {
        if (!cancelled) {
          setMonitorId('');
          setNodeId('');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [instUuid]);

  const widgets = useMemo<Partial<Record<AppWidgetKey, boolean>>>(
    () => ({
      'monitor.monitorView': monitorView.declared,
      'monitor.alertList': alertList.declared,
      'monitor.monitorPolicy': monitorPolicy.declared,
      'node.nodeStatus': nodeStatus.declared,
    }),
    [
      alertList.declared,
      monitorPolicy.declared,
      monitorView.declared,
      nodeStatus.declared,
    ],
  );

  return resolveCmdbPublicMenuItems({
    modelId,
    monitorId,
    nodeId,
    widgets,
  });
}
