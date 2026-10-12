'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import useMonitorApi from '@/app/monitor/api';
import { DashboardShell } from '../common/dashboard-components';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import { HOST_DASHBOARD_CONFIG } from './config';
import {
  HOST_DISK_ENTITY_QUERIES,
  HOST_GPU_ENTITY_QUERIES,
  HOST_NET_ENTITY_QUERIES,
  HOST_PROCESS_ENTITY_QUERIES
} from './queries';
import { useHostEntityMetrics } from './use-entity-metrics';
import { resolveHostProcessMetricsTarget } from './host-process-metrics-tab';
import HostCategoryLayout from './category-layout';
import HostLegacyLayout from './legacy-layout';
import {
  HOST_DETAIL_LAYOUT_OPTIONS,
  isHostDetailLayout,
  readHostDetailLayout,
  writeHostDetailLayout
} from './detail-layout';
import styles from './index.module.scss';

export default function HostDashboardPage() {
  const dashboard = useSimpleDashboardData(HOST_DASHBOARD_CONFIG);
  const router = useRouter();
  const monitorApi = useMonitorApi();
  const apiRef = useRef(monitorApi);
  apiRef.current = monitorApi;
  const searchParams = useSearchParams();
  const instanceIdKeys = useMemo(
    () => (searchParams.get('instance_id_keys') || 'instance_id').split(',').filter(Boolean),
    [searchParams]
  );
  const [processReady, setProcessReady] = useState(false);
  const [categoryTab, setCategoryTab] = useState('system');
  const layout = readHostDetailLayout(new URLSearchParams(searchParams.toString()));

  const {
    idValues,
    timeValues,
    isDashboardMode,
    currentInstanceInterval,
    monitorObjectId,
    instanceId
  } = dashboard;

  const entityOnClassic = layout === 'dashboard';
  const entityOnCategory = layout === 'category';
  const entityArgs = {
    idValues,
    instanceIdKeys,
    timeValues,
    monitorObjectId,
    instanceId,
    minStepSeconds: currentInstanceInterval,
    isDashboardMode
  };
  const diskState = useHostEntityMetrics({
    ...entityArgs,
    enabled: entityOnClassic || (entityOnCategory && categoryTab === 'disk'),
    queries: HOST_DISK_ENTITY_QUERIES
  });
  const netState = useHostEntityMetrics({
    ...entityArgs,
    enabled: entityOnClassic || (entityOnCategory && categoryTab === 'net'),
    queries: HOST_NET_ENTITY_QUERIES
  });
  const gpuState = useHostEntityMetrics({
    ...entityArgs,
    enabled: entityOnClassic || (entityOnCategory && categoryTab === 'gpu'),
    queries: HOST_GPU_ENTITY_QUERIES
  });
  const processState = useHostEntityMetrics({
    ...entityArgs,
    enabled: entityOnCategory && categoryTab === 'process' && processReady,
    queries: processReady ? HOST_PROCESS_ENTITY_QUERIES : []
  });

  useEffect(() => {
    let active = true;
    resolveHostProcessMetricsTarget({
      getMonitorObject: (params) => apiRef.current.getMonitorObject(params),
      getMonitorPlugin: (params) => apiRef.current.getMonitorPlugin(params)
    }).then((target) => {
      if (active) setProcessReady(Boolean(target));
    });
    return () => {
      active = false;
    };
  }, [monitorObjectId]);

  const onLayoutChange = (mode: string) => {
    if (!isHostDetailLayout(mode) || mode === layout) return;
    const params = writeHostDetailLayout(new URLSearchParams(searchParams.toString()), mode);
    router.replace(`?${params.toString()}`, { scroll: false });
  };

  useEffect(() => {
    if (layout === 'category' && categoryTab === 'process' && !processReady) {
      setCategoryTab('system');
    }
  }, [layout, categoryTab, processReady]);

  const layoutProps = {
    styles,
    dashboard,
    instanceIdKeys,
    diskState,
    netState,
    gpuState,
    processReady,
    processState,
    layout,
    onLayoutChange,
    categoryTab,
    onCategoryTabChange: setCategoryTab
  };

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      preserveLayouts
      viewSwitcher={{
        mode: layout,
        onChange: onLayoutChange,
        control: 'select',
        options: HOST_DETAIL_LAYOUT_OPTIONS
      }}
      dashboardContent={<HostLegacyLayout {...layoutProps} />}
      categoryContent={<HostCategoryLayout {...layoutProps} />}
    />
  );
}
