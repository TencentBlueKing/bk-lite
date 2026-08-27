'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Alert } from 'antd';
import { useSearchParams } from 'next/navigation';
import useApiClient from '@/utils/request';
import useMonitorApi from '@/app/monitor/api';
import { ObjectItem } from '@/app/monitor/types';
import { findByMonitorId } from '@/app/monitor/utils/monitorIds';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import {
  DashboardShell,
  KpiSection,
  useFilteredSummaryCards,
} from '../common/dashboard-components';
import type { FlowProtocol } from './constants';
import {
  isFlowSupportedObjectName,
  resolveInstanceTypeFromObjectName,
} from './constants';
import { createFlowDashboardConfig } from './create-flow-config';
import { FlowConversationTable } from './conversation-table';
import styles from './index.module.scss';

const SUMMARY_TITLES = ['总流量速率', '总包速率', '平均包大小', '有效采样率'];

interface FlowDashboardPageProps {
  protocol: FlowProtocol;
}

export function FlowDashboardPage({ protocol }: FlowDashboardPageProps) {
  const searchParams = useSearchParams();
  const { isLoading } = useApiClient();
  const { getMonitorObject } = useMonitorApi();
  const monitorObjId = searchParams.get('monitorObjId');
  const [objects, setObjects] = useState<ObjectItem[]>([]);
  const [objectsLoaded, setObjectsLoaded] = useState(false);

  useEffect(() => {
    if (isLoading) return;
    let active = true;

    const loadObjects = async () => {
      try {
        const data = await getMonitorObject({});
        if (!active) return;
        setObjects(data || []);
      } finally {
        if (active) setObjectsLoaded(true);
      }
    };

    loadObjects();

    return () => {
      active = false;
    };
  }, [getMonitorObject, isLoading]);

  const monitorObject = useMemo(
    () => findByMonitorId(objects, monitorObjId || ''),
    [monitorObjId, objects],
  );

  const objectName = monitorObject?.name || searchParams.get('name') || '';
  const objectDisplayName =
    monitorObject?.display_name || searchParams.get('monitorObjDisplayName') || objectName;
  const instanceType = useMemo(
    () => resolveInstanceTypeFromObjectName(objectName),
    [objectName],
  );

  const config = useMemo(() => {
    if (!instanceType) {
      return createFlowDashboardConfig({
        protocol,
        instanceType: 'switch',
        objectFallbackName: objectName || 'Switch',
        objectDisplayName,
      });
    }
    return createFlowDashboardConfig({
      protocol,
      instanceType,
      objectFallbackName: objectName,
      objectDisplayName,
    });
  }, [instanceType, objectDisplayName, objectName, protocol]);

  const dashboard = useSimpleDashboardData(config);
  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, SUMMARY_TITLES);
  const unsupportedObject =
    objectsLoaded && Boolean(objectName) && !isFlowSupportedObjectName(objectName);

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={
        <>
          {unsupportedObject ? (
            <Alert
              type="warning"
              showIcon
              className="mb-3"
              message="当前监控对象不支持 Flow 分析"
              description="请从 Switch、Router、Firewall 或 Loadbalance 的 Flow 实例进入此仪表盘。"
            />
          ) : null}
          {!instanceType && objectsLoaded ? (
            <Alert
              type="info"
              showIcon
              className="mb-3"
              message="无法识别设备类型"
              description="URL 中缺少有效的 monitorObjId，请从监控视图选择网络设备 Flow 实例进入。"
            />
          ) : null}

          <div className={styles.sectionLabel}>流量概览</div>
          <KpiSection dashboard={dashboard} summaryCards={summaryCards} kpiCols={4} styles={styles} />

          <div className={styles.sectionLabel}>Top 会话</div>
          {instanceType ? (
            <FlowConversationTable
              dashboard={dashboard}
              protocol={protocol}
              instanceType={instanceType}
              styles={styles}
            />
          ) : null}
        </>
      }
    />
  );
}
