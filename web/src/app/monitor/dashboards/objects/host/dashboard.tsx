'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import useMonitorApi from '@/app/monitor/api';
import { DashboardShell } from '../common/dashboard-components';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import { HOST_DASHBOARD_CONFIG } from './config';
import { HOST_CATEGORY_TAB_METRIC_NAMES } from './layered/performance-scope';
import type { HostCategoryTab } from './layered/tab-level';
import {
  HOST_DISK_ENTITY_QUERIES,
  HOST_DISK_OVERVIEW_ENTITY_QUERIES,
  HOST_GPU_ENTITY_QUERIES,
  HOST_NET_ENTITY_QUERIES,
  HOST_NET_OVERVIEW_ENTITY_QUERIES,
  HOST_PROCESS_ENTITY_QUERIES,
  HOST_PROCESS_OVERVIEW_ENTITY_QUERIES
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
  const router = useRouter();
  const monitorApi = useMonitorApi();
  const apiRef = useRef(monitorApi);
  apiRef.current = monitorApi;
  const searchParams = useSearchParams();
  const [processReady, setProcessReady] = useState(false);
  const [categoryTab, setCategoryTab] = useState('overview');
  const layout = readHostDetailLayout(new URLSearchParams(searchParams.toString()));
  const categoryMetricNames = HOST_CATEGORY_TAB_METRIC_NAMES[categoryTab as HostCategoryTab]
    ?? HOST_CATEGORY_TAB_METRIC_NAMES.overview;
  const dashboard = useSimpleDashboardData(
    HOST_DASHBOARD_CONFIG,
    layout === 'category'
      ? { metricNames: categoryMetricNames, reuseLoadedSeries: true }
      : undefined
  );
  const instanceIdKeys = useMemo(
    () => (searchParams.get('instance_id_keys') || 'instance_id').split(',').filter(Boolean),
    [searchParams]
  );

  const {
    idValues,
    timeValues,
    isDashboardMode,
    currentInstanceInterval,
    monitorObjectId,
    instanceId
  } = dashboard;

  const entityOnCategory = layout === 'category';
  const categoryDisk = entityOnCategory && (categoryTab === 'overview' || categoryTab === 'disk');
  const categoryNet = entityOnCategory && (categoryTab === 'overview' || categoryTab === 'net');
  const categoryProcess = entityOnCategory && processReady && (categoryTab === 'overview' || categoryTab === 'process');
  const categorySystem = entityOnCategory && categoryTab === 'system';
  const diskQueries = categoryTab === 'disk' ? HOST_DISK_ENTITY_QUERIES : HOST_DISK_OVERVIEW_ENTITY_QUERIES;
  const netQueries = categoryTab === 'net' ? HOST_NET_ENTITY_QUERIES : HOST_NET_OVERVIEW_ENTITY_QUERIES;
  const processQueries = processReady && categoryTab === 'process'
    ? HOST_PROCESS_ENTITY_QUERIES
    : HOST_PROCESS_OVERVIEW_ENTITY_QUERIES;
  const entityArgs = {
    idValues,
    instanceIdKeys,
    timeValues,
    monitorObjectId,
    instanceId,
    minStepSeconds: currentInstanceInterval,
    isDashboardMode,
    reloadKey: dashboard.loadTick
  };
  const diskState = useHostEntityMetrics({
    ...entityArgs,
    enabled: categoryDisk,
    queries: diskQueries
  });
  const netState = useHostEntityMetrics({
    ...entityArgs,
    enabled: categoryNet,
    queries: netQueries
  });
  const processState = useHostEntityMetrics({
    ...entityArgs,
    enabled: categoryProcess,
    queries: processReady ? processQueries : []
  });
  const gpuState = useHostEntityMetrics({
    ...entityArgs,
    enabled: categorySystem,
    queries: HOST_GPU_ENTITY_QUERIES
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
      setCategoryTab('overview');
    }
  }, [layout, categoryTab, processReady]);

  const layoutProps = {
    styles,
    dashboard,
    instanceIdKeys,
    diskState,
    netState,
    processReady,
    processState,
    gpuState,
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
      unifiedChrome
      viewSwitcher={{
        mode: layout,
        onChange: onLayoutChange,
        control: 'pill',
        options: HOST_DETAIL_LAYOUT_OPTIONS
      }}
      dashboardContent={<HostLegacyLayout {...layoutProps} />}
      categoryContent={<HostCategoryLayout {...layoutProps} />}
    />
  );
}
