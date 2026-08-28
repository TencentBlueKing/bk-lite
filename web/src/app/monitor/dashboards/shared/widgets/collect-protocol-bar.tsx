'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Segmented } from 'antd';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import useApiClient from '@/utils/request';
import useMonitorApi from '@/app/monitor/api';
import type { FlowDashboardPlugin } from '../utils/flow-dashboard-route';
import { getDashboardDisplayModeFromParams } from '../utils/display-mode-route';
import {
  flowPluginCacheKey,
  getCachedFlowPlugins,
  setCachedFlowPlugins,
} from '../utils/flow-plugin-cache';
import {
  buildFlowViewSwitchUrl,
  FLOW_VIEW_LABELS,
  getAvailableFlowViews,
  isFlowViewSwitchContext,
  resolveCurrentFlowView,
  shouldShowFlowViewSwitch,
  type FlowViewKind,
} from '../utils/flow-view-navigation';
import { normalizeDashboardKey } from '../utils';

export interface CollectProtocolBarProps {
  routeKey?: string;
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
  routeKey = '',
  monitorObjectName,
  monitorObjectId,
  instanceId,
  styles,
}: CollectProtocolBarProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const params = useParams<{ objectKey?: string }>();
  const activeRouteKey =
    normalizeDashboardKey(params?.objectKey) || normalizeDashboardKey(routeKey);
  const { isLoading } = useApiClient();
  const { getEffectivePlugins } = useMonitorApi();

  const resolvedMonitorObjectId =
    monitorObjectId != null
      ? String(monitorObjectId)
      : searchParams.get('monitorObjId') || '';
  const resolvedInstanceId =
    instanceId != null ? String(instanceId) : searchParams.get('instance_id') || '';
  const pluginCacheKey =
    resolvedMonitorObjectId && resolvedInstanceId
      ? flowPluginCacheKey(resolvedMonitorObjectId, resolvedInstanceId)
      : '';

  const [plugins, setPlugins] = useState<FlowDashboardPlugin[] | null>(() =>
    pluginCacheKey ? getCachedFlowPlugins(pluginCacheKey) ?? null : null,
  );
  const [pluginsLoading, setPluginsLoading] = useState(false);

  const resolvedObjectName = monitorObjectName || searchParams.get('name') || '';
  const isDashboardMode = getDashboardDisplayModeFromParams(searchParams) === 'dashboard';

  useEffect(() => {
    if (!pluginCacheKey) {
      setPlugins(null);
      setPluginsLoading(false);
      return;
    }

    const cached = getCachedFlowPlugins(pluginCacheKey);
    if (cached) {
      setPlugins(cached);
    }

    if (isLoading) return;

    let active = true;
    const silentRefresh = Boolean(cached);
    if (!silentRefresh) {
      setPluginsLoading(true);
    }

    const loadPlugins = async () => {
      try {
        const data = await getEffectivePlugins(resolvedMonitorObjectId, {
          instance_id: resolvedInstanceId,
        });
        if (!active) return;
        const next = Array.isArray(data) ? data : [];
        setCachedFlowPlugins(pluginCacheKey, next);
        setPlugins(next);
      } catch {
        if (!active) return;
        if (!silentRefresh) {
          setCachedFlowPlugins(pluginCacheKey, []);
          setPlugins([]);
        }
      } finally {
        if (active && !silentRefresh) {
          setPluginsLoading(false);
        }
      }
    };

    void loadPlugins();

    return () => {
      active = false;
    };
  }, [
    isLoading,
    pluginCacheKey,
    resolvedInstanceId,
    resolvedMonitorObjectId,
  ]);

  const resolvedPlugins = useMemo(() => plugins ?? [], [plugins]);

  const availableViews = useMemo(
    () => getAvailableFlowViews(resolvedPlugins),
    [resolvedPlugins],
  );
  const currentView = resolveCurrentFlowView(activeRouteKey);
  const inFlowContext = isFlowViewSwitchContext(activeRouteKey, resolvedObjectName);

  const visible = useMemo(
    () =>
      shouldShowFlowViewSwitch({
        routeKey: activeRouteKey,
        monitorObjectName: resolvedObjectName,
        availableViews,
      }),
    [activeRouteKey, availableViews, resolvedObjectName],
  );

  const options = useMemo(
    () => availableViews.map((view) => ({ label: FLOW_VIEW_LABELS[view], value: view })),
    [availableViews],
  );

  const awaitingPlugins =
    Boolean(pluginCacheKey)
    && (plugins === null || pluginsLoading);
  const shouldRenderBar =
    isDashboardMode &&
    inFlowContext &&
    currentView &&
    (visible || awaitingPlugins);

  if (!shouldRenderBar) return null;

  const segmentedOptions =
    options.length >= 2
      ? options
      : ([currentView] as FlowViewKind[]).map((view) => ({
        label: FLOW_VIEW_LABELS[view],
        value: view,
      }));

  const interactionBlocked = pluginsLoading && options.length < 2;

  const onChange = (value: FlowViewKind) => {
    if (value === currentView || interactionBlocked) return;
    const url = buildFlowViewSwitchUrl(value, {
      monitorObjectName: resolvedObjectName,
      searchParams,
    });
    if (url) router.push(url);
  };

  return (
    <div
      className={styles.protocolBar}
      role="region"
      aria-label="采集视图切换"
      aria-busy={pluginsLoading}
    >
      <span className={styles.protocolBarLabel}>采集视图</span>
      <Segmented
        size="middle"
        className={styles.protocolSegmented}
        value={currentView}
        options={segmentedOptions}
        disabled={interactionBlocked}
        onChange={(value) => onChange(value as FlowViewKind)}
        aria-label="采集协议"
      />
    </div>
  );
}

/** @deprecated 使用 CollectProtocolBar */
export const FlowViewSwitch = CollectProtocolBar;
export type FlowViewSwitchProps = CollectProtocolBarProps;
