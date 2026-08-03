'use client';

import React, { useEffect, useState } from 'react';
import { Empty, Segmented, Spin } from 'antd';
import MetricViews from '@/app/monitor/components/metric-views';
import useMonitorApi from '@/app/monitor/api';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import { TitleWithGuide } from '../../shared/widgets';
import { resolveProcessObjectId } from './host-metrics-process-object';

type MetricsTab = 'host' | 'process';

interface HostMetricsSectionProps {
  dashboard: ReturnType<typeof useSimpleDashboardData>;
  styles: Record<string, string>;
}

/**
 * 主机全量指标：主机 OS 指标 + 同 instance_id 下的进程指标历史折线。
 */
export function HostMetricsSection({
  dashboard,
  styles
}: HostMetricsSectionProps) {
  const { getMonitorObject } = useMonitorApi();
  const [tab, setTab] = useState<MetricsTab>('host');
  const [processObjectId, setProcessObjectId] = useState('');
  const [processObjectLoading, setProcessObjectLoading] = useState(false);

  useEffect(() => {
    let active = true;
    setProcessObjectLoading(true);
    // 注意：useMonitorApi() 每次渲染都会返回新的函数引用，不能放进依赖，
    // 否则会反复 setLoading(true) 并卸载 MetricViews，进程指标页永远转圈。
    getMonitorObject({ name: 'Process', include_invisible: true })
      .then((data: unknown) => {
        if (!active) return;
        setProcessObjectId(resolveProcessObjectId(data));
      })
      .catch(() => {
        if (active) setProcessObjectId('');
      })
      .finally(() => {
        if (active) setProcessObjectLoading(false);
      });
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount-once; getMonitorObject identity is unstable
  }, []);

  const commonProps = {
    instanceId: dashboard.instanceId,
    instanceName: dashboard.resolvedInstanceName,
    idValues: dashboard.idValues,
    externalTimeValues: dashboard.timeValues,
    externalTimeDefaultValue: dashboard.timeDefaultValue,
    externalFrequence: dashboard.frequence,
    externalRefreshSignal: dashboard.metricsRefreshSignal,
    collectionInterval: dashboard.currentInstanceInterval,
    hideTimeSelector: true as const,
    onExternalXRangeChange: dashboard.onXRangeChange
  };

  return (
    <div className={styles.metricsMode}>
      <div className={`${styles.panel} ${styles.fullPanel}`}>
        <div className={styles.sectionHeading}>
          <h3 className={styles.panelTitle}>
            <TitleWithGuide
              title="监控指标全量"
              items={[
                {
                  label: '主机指标',
                  detail: '当前主机 OS 采集的完整指标历史曲线。'
                },
                {
                  label: '进程指标',
                  detail:
                    '按与主机相同的 instance_id 关联 Process 对象指标，可查看该主机下各进程的历史折线。'
                }
              ]}
              styles={styles}
            />
          </h3>
          <Segmented
            value={tab}
            options={[
              { label: '主机指标', value: 'host' },
              { label: '进程指标', value: 'process' }
            ]}
            onChange={(value) => setTab(value as MetricsTab)}
          />
        </div>

        {tab === 'host' ? (
          <MetricViews
            key={`host-${dashboard.instanceId}`}
            monitorObjectId={dashboard.monitorObjectId}
            monitorObjectName={dashboard.monitorObjectName}
            {...commonProps}
          />
        ) : processObjectLoading ? (
          <div className="flex min-h-[240px] items-center justify-center">
            <Spin />
          </div>
        ) : processObjectId ? (
          <MetricViews
            key={`process-${dashboard.instanceId}`}
            monitorObjectId={processObjectId}
            monitorObjectName="Process"
            queryInstanceIdKeys={['instance_id']}
            {...commonProps}
          />
        ) : (
          <Empty
            className="py-[48px]"
            description="未找到进程监控对象，请先接入 Process 插件"
          />
        )}
      </div>
    </div>
  );
}
