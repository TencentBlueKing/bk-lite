'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Segmented } from 'antd';
import { useRouter, useSearchParams } from 'next/navigation';
import useApiClient from '@/utils/request';
import useMonitorApi from '@/app/monitor/api';
import { resolveFlowViewSwitchPlugins } from '@/app/monitor/mocks/monitor-flow-mock';
import { isMonitorViewDemoEnabled } from '@/app/monitor/mocks/monitor-view-demo-data';
import type { FlowDashboardPlugin } from '../utils/flow-dashboard-route';
import {
  buildFlowViewSwitchUrl,
  FLOW_VIEW_LABELS,
  getAvailableFlowViews,
  isFlowViewSwitchContext,
  resolveCurrentFlowView,
  shouldShowFlowViewSwitch,
  type FlowViewKind,
} from '../utils/flow-view-navigation';

export interface CollectProtocolBarProps {
  routeKey: string;
  monitorObjectName?: string | null;
  monitorObjectId?: React.Key | null;
  instanceId?: React.Key | null;
  styles: {
    protocolSegmented?: string;
    protocolBar?: string;
    protocolBarLabel?: string;
  };
}

/** 内容区顶部的一级导航：SNMP / NetFlow / sFlow 采集视图切换（替代分区标题的第一层）。 */
export function CollectProtocolBar({
  routeKey,
  monitorObjectName,
  monitorObjectId,
  instanceId,
  styles,
}: CollectProtocolBarProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { isLoading } = useApiClient();
  const { getEffectivePlugins } = useMonitorApi();
  const [plugins, setPlugins] = useState<FlowDashboardPlugin[] | null>(null);

  const resolvedObjectName = monitorObjectName || searchParams.get('name') || '';

  useEffect(() => {
    const normalizedMonitorObjectId = monitorObjectId != null ? String(monitorObjectId) : '';
    const normalizedInstanceId = instanceId != null ? String(instanceId) : '';

    if (!normalizedMonitorObjectId || !normalizedInstanceId) {
      setPlugins(null);
      return;
    }

    if (isLoading) return;

    let active = true;

    const loadPlugins = async () => {
      try {
        const data = await getEffectivePlugins(normalizedMonitorObjectId, {
          instance_id: normalizedInstanceId,
        });
        if (!active) return;
        setPlugins(Array.isArray(data) ? data : []);
      } catch {
        if (active) setPlugins([]);
      }
    };

    void loadPlugins();

    return () => {
      active = false;
    };
  }, [getEffectivePlugins, instanceId, isLoading, monitorObjectId]);

  const resolvedPlugins = useMemo(
    () => resolveFlowViewSwitchPlugins(plugins, {
      routeKey,
      monitorObjectName: resolvedObjectName,
    }),
    [plugins, resolvedObjectName, routeKey],
  );

  const availableViews = useMemo(
    () => getAvailableFlowViews(resolvedPlugins),
    [resolvedPlugins],
  );
  const currentView = resolveCurrentFlowView(routeKey);
  const visible = useMemo(
    () => shouldShowFlowViewSwitch({
      routeKey,
      monitorObjectName: resolvedObjectName,
      availableViews,
    }),
    [availableViews, resolvedObjectName, routeKey],
  );

  const options = useMemo(
    () => availableViews.map((view) => ({ label: FLOW_VIEW_LABELS[view], value: view })),
    [availableViews],
  );

  const waitingForPlugins = plugins === null && !isMonitorViewDemoEnabled();
  const inFlowContext = isFlowViewSwitchContext(routeKey, resolvedObjectName);

  if (!inFlowContext || !visible || !currentView || waitingForPlugins) return null;

  const onChange = (value: FlowViewKind) => {
    if (value === currentView) return;
    const url = buildFlowViewSwitchUrl(value, {
      monitorObjectName: resolvedObjectName,
      searchParams,
    });
    if (url) router.push(url);
  };

  return (
    <div className={styles.protocolBar} role="region" aria-label="采集视图切换">
      <span className={styles.protocolBarLabel}>采集视图</span>
      <Segmented
        size="middle"
        className={styles.protocolSegmented}
        value={currentView}
        options={options}
        onChange={(value) => onChange(value as FlowViewKind)}
        aria-label="采集协议"
      />
    </div>
  );
}

/** @deprecated 使用 CollectProtocolBar */
export const FlowViewSwitch = CollectProtocolBar;
export type FlowViewSwitchProps = CollectProtocolBarProps;
