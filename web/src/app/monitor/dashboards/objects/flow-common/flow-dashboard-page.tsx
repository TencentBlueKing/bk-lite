'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Empty, Spin } from 'antd';
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
  resolveFlowHostMonitorObject,
  resolveInstanceTypeFromObjectName,
} from './constants';
import { createFlowDashboardConfig } from './create-flow-config';
import { FlowConversationTable } from './conversation-table';
import { FlowProtocolBreakdown } from './protocol-breakdown';
import styles from './index.module.scss';

const SUMMARY_TITLES = ['总流量速率', '总包速率', '平均包大小', '有效采样率'];

interface FlowDashboardPageProps {
  protocol: FlowProtocol;
}

interface FlowDashboardMetricsViewProps {
  protocol: FlowProtocol;
  instanceType: string;
  objectName: string;
  objectDisplayName: string;
}

/** 仅在设备类型已识别时挂载，避免用 Switch 兜底配置误拉 PromQL。 */
function FlowDashboardMetricsView({
  protocol,
  instanceType,
  objectName,
  objectDisplayName,
}: FlowDashboardMetricsViewProps) {
  const config = useMemo(
    () =>
      createFlowDashboardConfig({
        protocol,
        instanceType,
        objectFallbackName: objectName,
        objectDisplayName,
      }),
    [instanceType, objectDisplayName, objectName, protocol],
  );

  const dashboard = useSimpleDashboardData(config);
  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, SUMMARY_TITLES);

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={
        <>
          <div className={styles.sectionLabel}>流量概览</div>
          <KpiSection dashboard={dashboard} summaryCards={summaryCards} kpiCols={5} styles={styles} />

          <div className={styles.sectionLabel}>流量分析</div>
          <section className={styles.dashboardSection}>
            <div className={`${styles.sectionGrid} ${styles.flowAnalysisGrid}`}>
              <FlowConversationTable
                dashboard={dashboard}
                protocol={protocol}
                instanceType={instanceType}
                styles={styles}
              />
              <FlowProtocolBreakdown
                dashboard={dashboard}
                protocol={protocol}
                instanceType={instanceType}
                styles={styles}
              />
            </div>
          </section>
        </>
      }
    />
  );
}

function FlowDashboardPlaceholder({ children }: { children: React.ReactNode }) {
  return (
    <div className={styles.page}>
      <div className={styles.shell}>
        <div className="flex min-h-[240px] items-center justify-center py-12">{children}</div>
      </div>
    </div>
  );
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

  const flowHost = useMemo(
    () => (objectsLoaded ? resolveFlowHostMonitorObject(objects, monitorObjId) : undefined),
    [monitorObjId, objects, objectsLoaded],
  );

  const missingFlowContext = objectsLoaded && !monitorObjId && !flowHost;
  const unsupportedObject =
    objectsLoaded && Boolean(objectName) && !isFlowSupportedObjectName(objectName);
  const awaitingFlowResolution =
    !missingFlowContext &&
    !unsupportedObject &&
    Boolean(flowHost) &&
    (!monitorObjId || !instanceType);
  const readyForMetrics =
    Boolean(monitorObjId) &&
    Boolean(instanceType) &&
    isFlowSupportedObjectName(objectName) &&
    !missingFlowContext &&
    !unsupportedObject;

  if (missingFlowContext) {
    return (
      <FlowDashboardPlaceholder>
        <Empty description="当前环境暂无支持 Flow 分析的网络设备（Switch/Router/Firewall/Loadbalance），请先在集成中接入后再进入。" />
      </FlowDashboardPlaceholder>
    );
  }

  if (unsupportedObject) {
    return (
      <FlowDashboardPlaceholder>
        <Alert
          type="warning"
          showIcon
          message="当前监控对象不支持 Flow 分析"
          description="请从 Switch、Router、Firewall 或 Loadbalance 的 Flow 实例进入此仪表盘。"
        />
      </FlowDashboardPlaceholder>
    );
  }

  if (!readyForMetrics) {
    if (!objectsLoaded || awaitingFlowResolution) {
      return (
        <FlowDashboardPlaceholder>
          <Spin />
        </FlowDashboardPlaceholder>
      );
    }

    return (
      <FlowDashboardPlaceholder>
        <Alert
          type="info"
          showIcon
          message="无法识别设备类型"
          description="URL 中缺少有效的 monitorObjId，请从监控视图选择网络设备 Flow 实例进入。"
        />
      </FlowDashboardPlaceholder>
    );
  }

  return (
    <FlowDashboardMetricsView
      protocol={protocol}
      instanceType={instanceType!}
      objectName={objectName}
      objectDisplayName={objectDisplayName}
    />
  );
}
