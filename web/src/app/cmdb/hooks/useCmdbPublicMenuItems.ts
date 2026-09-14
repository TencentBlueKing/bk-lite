'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useInstanceApi } from '@/app/cmdb/api';
import { resolveCmdbInstUuid } from '@/app/cmdb/utils/instUuid';
import { resolveCmdbPublicMenuItems } from '@/app/cmdb/utils/cmdbPublicMenus';
import { hasAppAccess, useAppWidget } from '@/context/appCapabilities';
import type { AppWidgetKey } from '@/context/appCapabilities';
import { useClientData } from '@/context/client';

export function useCmdbPublicMenuItems() {
  const searchParams = useSearchParams();
  const modelId = searchParams.get('model_id') || '';
  const instUuid = resolveCmdbInstUuid(searchParams.get('inst_uuid')) || '';
  const { getInstanceDetail, getTopoThemes } = useInstanceApi();
  const instanceApiRef = useRef({ getInstanceDetail, getTopoThemes });
  instanceApiRef.current = { getInstanceDetail, getTopoThemes };
  const { clientData } = useClientData();
  const hasOpsAnalysis = hasAppAccess(clientData, 'ops-analysis');
  const monitorView = useAppWidget('monitor.monitorView');
  const alertList = useAppWidget('monitor.alertList');
  const networkStatus = useAppWidget('ops-analysis.networkStatusTopology');
  const application3D = useAppWidget('ops-analysis.application3D');
  const [monitorId, setMonitorId] = useState('');
  const [isNetworkDevice, setIsNetworkDevice] = useState(false);

  useEffect(() => {
    if (!instUuid) {
      setMonitorId('');
      return;
    }
    let cancelled = false;
    instanceApiRef.current.getInstanceDetail(instUuid)
      .then((detail: { monitor_id?: string }) => {
        if (!cancelled) {
          setMonitorId(String(detail?.monitor_id || '').trim());
        }
      })
      .catch(() => {
        if (!cancelled) setMonitorId('');
      });
    return () => {
      cancelled = true;
    };
  }, [instUuid]);

  useEffect(() => {
    if (!modelId) {
      setIsNetworkDevice(false);
      return;
    }
    let cancelled = false;
    instanceApiRef.current.getTopoThemes(modelId)
      .then((res: { themes?: string[] }) => {
        if (!cancelled) {
          setIsNetworkDevice(Boolean(res?.themes?.includes('network')));
        }
      })
      .catch(() => {
        if (!cancelled) setIsNetworkDevice(false);
      });
    return () => {
      cancelled = true;
    };
  }, [modelId]);

  const widgets = useMemo<Partial<Record<AppWidgetKey, boolean>>>(
    () => ({
      'monitor.monitorView': monitorView.declared,
      'monitor.alertList': alertList.declared,
      'ops-analysis.networkStatusTopology': networkStatus.declared,
      'ops-analysis.application3D': application3D.declared,
    }),
    [
      alertList.declared,
      application3D.declared,
      monitorView.declared,
      networkStatus.declared,
    ],
  );

  return resolveCmdbPublicMenuItems({
    instUuid,
    modelId,
    monitorId,
    isNetworkDevice,
    hasOpsAnalysis,
    widgets,
  });
}
