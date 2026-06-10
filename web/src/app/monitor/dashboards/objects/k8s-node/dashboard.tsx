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
  DetailPanelCard
} from '../common/dashboard-components';
import { RingChartPanel, HorizontalBarPanel } from '../../shared/widgets';
import { buildSearchParams, parseLegacyParamList, normalizeDisplayText } from '../../shared/utils';
import { buildTopBars, coresDisplay, bytesDisplay } from '../k8s-cluster/parse';
import { TOP_N } from '../k8s-cluster/queries';
import { NODE_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

export default function K8sNodeDashboardPage() {
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);
  const idValuesKey = idValues.join('|');

  const [topPodCpuRaw, setTopPodCpuRaw] = useState<any>(null);
  const [topPodMemRaw, setTopPodMemRaw] = useState<any>(null);

  const NODE_TOP_POD_CPU = `topk(${TOP_N}, sum by (pod) (rate(prometheus_remote_write_container_cpu_usage_seconds_total{instance_type="k8s",__$labels__}[5m])))`;
  const NODE_TOP_POD_MEM = `topk(${TOP_N}, sum by (pod) (prometheus_remote_write_container_memory_working_set_bytes{instance_type="k8s",__$labels__}))`;

  useEffect(() => {
    if (idValues.length === 0) return;
    let active = true;
    const tv: TimeValuesProps = dashboard.timeValues;
    getInstanceQuery(buildSearchParams(NODE_TOP_POD_CPU, 'none', idValues, instanceIdKeys, tv))
      .then((r) => { if (active) setTopPodCpuRaw(r); })
      .catch(() => { if (active) setTopPodCpuRaw(null); });
    // 内存为字节类指标:禁用服务端单位自动换算,否则与前端 bytesDisplay 双重换算(见 k8s-cluster 同因)。
    getInstanceQuery(buildSearchParams(NODE_TOP_POD_MEM, 'bytes', idValues, instanceIdKeys, tv, undefined, false))
      .then((r) => { if (active) setTopPodMemRaw(r); })
      .catch(() => { if (active) setTopPodMemRaw(null); });
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idValuesKey, dashboard.timeValues]);

  const nodeTopPodCpuBars = useMemo(() => buildTopBars(topPodCpuRaw, 'pod', '#9254de', coresDisplay), [topPodCpuRaw]);
  const nodeTopPodMemBars = useMemo(() => buildTopBars(topPodMemRaw, 'pod', '#13c2c2', bytesDisplay), [topPodMemRaw]);

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={
        <>
          <KpiSection dashboard={dashboard} summaryCards={dashboard.summaryCards} kpiCols={6} styles={styles} />
          <TrendSection
            charts={dashboard.chartPanels}
            onXRangeChange={dashboard.onXRangeChange}
            loading={dashboard.loading}
            spanClass={() => `${styles.span6} ${styles.compactTrend}`}
            styles={styles}
          />
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
