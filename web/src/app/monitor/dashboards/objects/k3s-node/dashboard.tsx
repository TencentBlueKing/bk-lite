'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import useViewApi from '@/app/monitor/api/view';
import { TimeValuesProps } from '@/app/monitor/types';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import {
  DashboardShell,
  KpiSection,
  TrendSection,
  FlexiblePanelSection,
  DetailPanelCard, DashboardSectionLabel } from '../common/dashboard-components';
import { RingChartPanel, HorizontalBarPanel } from '../../shared/widgets';
import { buildSearchParams, parseLegacyParamList, normalizeDisplayText } from '../../shared/utils';
import { buildTopBars, coresDisplay, bytesDisplay } from '../k3s-cluster/parse';
import { createNodeTopPodLoadCoordinator } from '../common/nodeTopPodLoad';
import { NODE_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';
import { K3S_NODE_TOP_POD_CPU, K3S_NODE_TOP_POD_MEM } from './queries';

export default function K3sNodeDashboardPage() {
  const dashboard = useSimpleDashboardData(NODE_DASHBOARD_CONFIG);

  const { getInstanceQuery } = useViewApi();
  const searchParams = useSearchParams();
  const instanceIdKeys = (searchParams.get('instance_id_keys') || 'instance_id,node').split(',').filter(Boolean);
  const idValues = useMemo(() => {
    const explicit = parseLegacyParamList(searchParams.get('instance_id_values'));
    if (explicit.length > 0) return explicit;
    const legacy = parseLegacyParamList(searchParams.get('instance_id') || '');
    if (legacy.length > 0) return legacy;
    const normalized = normalizeDisplayText(searchParams.get('instance_id') || '');
    return normalized ? [normalized] : [];
  }, [searchParams]);
  const idValuesKey = idValues.join('|');

  const [topPodCpuRaw, setTopPodCpuRaw] = useState<any>(null);
  const [topPodMemRaw, setTopPodMemRaw] = useState<any>(null);

  useEffect(() => {
    if (!dashboard.isDashboardMode || idValues.length === 0) {
      setTopPodCpuRaw(null);
      setTopPodMemRaw(null);
      return;
    }
    const coordinator = createNodeTopPodLoadCoordinator();
    const generation = coordinator.begin();
    const tv: TimeValuesProps = dashboard.timeValues;
    getInstanceQuery(buildSearchParams(K3S_NODE_TOP_POD_CPU, 'none', idValues, instanceIdKeys, tv, undefined, false, dashboard.currentInstanceInterval, {
      monitorObjectId: dashboard.monitorObjectId,
      instanceId: dashboard.instanceId,
    }))
      .then((r) => { if (coordinator.shouldApply(generation)) setTopPodCpuRaw(r); })
      .catch(() => { if (coordinator.shouldApply(generation)) setTopPodCpuRaw(null); });
    // 内存为字节类指标:禁用服务端单位自动换算,否则与前端 bytesDisplay 双重换算(见 k3s-cluster 同因)。
    getInstanceQuery(buildSearchParams(K3S_NODE_TOP_POD_MEM, 'bytes', idValues, instanceIdKeys, tv, undefined, false, dashboard.currentInstanceInterval, {
      monitorObjectId: dashboard.monitorObjectId,
      instanceId: dashboard.instanceId,
    }))
      .then((r) => { if (coordinator.shouldApply(generation)) setTopPodMemRaw(r); })
      .catch(() => { if (coordinator.shouldApply(generation)) setTopPodMemRaw(null); });
    return () => { coordinator.begin(); };
  }, [idValuesKey, dashboard.currentInstanceInterval, dashboard.timeValues, dashboard.loadTick, dashboard.isDashboardMode]);

  const nodeTopPodCpuBars = useMemo(() => buildTopBars(topPodCpuRaw, 'pod', '#9254de', coresDisplay), [topPodCpuRaw]);
  const nodeTopPodMemBars = useMemo(() => buildTopBars(topPodMemRaw, 'pod', '#13c2c2', bytesDisplay), [topPodMemRaw]);

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={
        <>
          <DashboardSectionLabel styles={styles}>健康概览</DashboardSectionLabel>
          <KpiSection dashboard={dashboard} summaryCards={dashboard.summaryCards} kpiCols={6} styles={styles} />
          <DashboardSectionLabel styles={styles}>资源趋势</DashboardSectionLabel>
          <TrendSection
            charts={dashboard.chartPanels}
            onXRangeChange={dashboard.onXRangeChange}
            loading={dashboard.loading}
            spanClass={() => `${styles.span6} ${styles.compactTrend}`}
            styles={styles}
          />
          <DashboardSectionLabel styles={styles}>分布与详情</DashboardSectionLabel>
          <FlexiblePanelSection styles={styles}>
            {dashboard.ringPanels.map((ring) => (
              <RingChartPanel
                key={ring.panel.title}
                title={ring.panel.title}
                subtitle={ring.panel.subtitle}
                guide={ring.panel.guide}
                data={ring.data}
                centerValue={ring.centerValue}
                centerCaption={ring.panel.centerCaption}
                isEmpty={ring.isEmpty}
                className={styles.span4}
                styles={styles}
              />
            ))}
            {dashboard.detailPanels.map((detailPanel) => (
              <DetailPanelCard
                key={detailPanel.panel.title}
                detailPanel={detailPanel}
                className={styles.span4}
                styles={styles}
              />
            ))}
          </FlexiblePanelSection>
          <DashboardSectionLabel styles={styles}>Pod 资源排行</DashboardSectionLabel>
          <FlexiblePanelSection styles={styles}>
            <HorizontalBarPanel
              title="Top Pod · CPU"
              subtitle="核数 · 5m"
              guide={[{ label: 'Top Pod · CPU', detail: '本节点上 CPU 消耗最高的 Pod。' }]}
              items={nodeTopPodCpuBars}
              tiered
              className={styles.span6}
              styles={styles}
            />
            <HorizontalBarPanel
              title="Top Pod · 内存"
              guide={[{ label: 'Top Pod · 内存', detail: '本节点上内存占用最高的 Pod。' }]}
              items={nodeTopPodMemBars}
              tiered
              className={styles.span6}
              styles={styles}
            />
          </FlexiblePanelSection>
        </>
      }
    />
  );
}
