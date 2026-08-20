'use client';

import React, { useState, useEffect, useMemo, useRef } from 'react';
import { Space, Card, Button, message, Tag, Popconfirm, Spin } from 'antd';
import { useIntl } from 'react-intl';
import PermissionWrapper from '@/components/permission';
import CustomTable from '@/components/custom-table';
import {
  ArrowRightOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  FileTextOutlined,
  DesktopOutlined,
  CheckCircleOutlined,
  EyeOutlined,
  WarningOutlined,
  ExclamationCircleOutlined,
  ToolOutlined,
  AlertOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import { useRouter } from 'next/navigation';
import useApiClient from '@/utils/request';
import usePatchManagerApi from '@/app/patch-manager/api';
import { PatchDashboardStats, ComplianceDistributionItem, RecentTaskItem, TopRiskItem } from '@/app/patch-manager/types';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import SeverityTag from '@/app/patch-manager/components/severity-tag';
import styles from './page.module.scss';
import {
  DASHBOARD_MIN_SECTION_HEIGHT,
  resolveDashboardSectionHeight,
  resolveDashboardTableScrollY,
} from './tableLayout';
import { formatCompactKpiValue } from './kpiPresentation';
import KpiGrid from './_components/kpi-grid';
import type { KpiCardProps } from './_components/kpi-card';

export default function HomePage() {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const api = usePatchManagerApi();
  const { isLoading } = useApiClient();
  const { locale } = useIntl();
  const router = useRouter();
  const [stats, setStats] = useState<PatchDashboardStats | null>(null);
  const [assessLoading, setAssessLoading] = useState(false);
  const [pageLoading, setPageLoading] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [tableHeight, setTableHeight] = useState(DASHBOARD_MIN_SECTION_HEIGHT);

  useEffect(() => {
    const updateHeight = () => {
      if (!bottomRef.current) return;
      const rect = bottomRef.current.getBoundingClientRect();
      const height = window.innerHeight - rect.top - 24;
      setTableHeight(resolveDashboardSectionHeight(height));
    };
    updateHeight();
    window.addEventListener('resize', updateHeight);
    return () => window.removeEventListener('resize', updateHeight);
  }, [stats]);

  useEffect(() => {
    if (isLoading) return;
    const loadStats = async () => {
      try {
        const data = await api.getPatchDashboardStats();
        setStats(data);
      } catch {
      } finally {
        setPageLoading(false);
      }
    };
    loadStats();
  }, [isLoading]);

  const handleImmediateAssess = async () => {
    setAssessLoading(true);
    try {
      const res = await api.getPatchTargetList({ page: 1, page_size: -1 });
      const visibleTargets = Array.isArray(res) ? res : (res.items || []);
      const targets = visibleTargets.filter((target: any) => target.permission?.includes('Operate'));
      if (targets.length === 0) {
        message.info(t('patchManager.dashboard.noManagedTargets'));
        return;
      }
      await api.createGovernanceTask({
        task_type: 'assess',
        target_list: targets.map((t: any) => t.id),
        execution_mode: 'now',
      });
      message.success(t('patchManager.dashboard.assessmentCreated', undefined, { count: targets.length }));
    } catch {
    } finally {
      setAssessLoading(false);
    }
  };

  const kpis: Omit<KpiCardProps, 'maxFontSize'>[] = [
    { label: t('patchManager.dashboard.managedTargets'), ...formatCompactKpiValue(stats?.target_total, locale), icon: <DesktopOutlined /> },
    { label: t('patchManager.dashboard.complianceRate'), value: stats?.compliance_rate != null ? `${stats.compliance_rate}%` : '--', tone: 'success', icon: <CheckCircleOutlined /> },
    { label: t('patchManager.dashboard.coverageRate'), value: stats?.coverage_rate != null ? `${stats.coverage_rate}%` : '--', icon: <EyeOutlined /> },
    { label: t('patchManager.dashboard.nonCompliantTargets'), ...formatCompactKpiValue(stats?.non_compliant_hosts, locale), tone: 'danger', icon: <WarningOutlined /> },
    { label: t('patchManager.dashboard.unconfiguredBaselines'), ...formatCompactKpiValue(stats?.unconfigured_hosts, locale), tone: 'warning', icon: <ExclamationCircleOutlined /> },
    { label: t('patchManager.dashboard.pendingRisks'), ...formatCompactKpiValue(stats?.pending_risk_count, locale), tone: 'warning', icon: <ToolOutlined /> },
    { label: t('patchManager.dashboard.remediationFailures'), ...formatCompactKpiValue(stats?.failed_tasks, locale), tone: 'danger', icon: <AlertOutlined /> },
  ];

  const dist: ComplianceDistributionItem[] = stats?.compliance_distribution || [];
  const distTotal = dist.reduce((sum: number, d) => sum + (d.count || 0), 0) || 1;
  const compliantCount = dist.find((d) => d.filter === 'compliant')?.count || 0;
  const nonCompliantCount = dist.find((d) => d.filter === 'non_compliant')?.count || 0;
  const failedCount = dist.find((d) => d.filter === 'failed')?.count || 0;
  const denom = compliantCount + nonCompliantCount;
  const rateHint = denom > 0 ? ` = ${compliantCount} / ${denom} ≈ ${Math.round(compliantCount / denom * 100)}%` : '';
  const assessedCount = compliantCount + nonCompliantCount + failedCount;
  const targetTotal = stats?.target_total ?? 0;
  const coverageHint = targetTotal > 0 ? ` = ${assessedCount} / ${targetTotal} ≈ ${Math.round(assessedCount / targetTotal * 100)}%` : '';
  const recentExecutionText = (record: RecentTaskItem) => {
    if (record.execution_mode !== 'window') return t('patchManager.risk.executeNow');
    const start = record.execution_window_start ? convertToLocalizedTime(record.execution_window_start) : '--';
    const end = record.execution_window_end ? convertToLocalizedTime(record.execution_window_end) : '--';
    return `${t('patchManager.risk.executionWindow')} ${start}–${end}`;
  };
  const tableScrollY = resolveDashboardTableScrollY(tableHeight);
  const tableBodyStyle = {
    '--dashboard-table-body-height': `${tableScrollY}px`,
  } as React.CSSProperties;

  const FILTER_COLORS: Record<string, string> = {
    compliant: '#1D9E75',
    non_compliant: '#E24B4A',
    pending: '#A4A19E',
    failed: '#6B7280',
    unconfigured: '#EF9F27',
  };

  const distributionOption = useMemo(() => ({
    grid: { left: 0, right: 0, top: 0, bottom: 0, height: 16 },
    tooltip: { trigger: 'item' },
    xAxis: {
      type: 'value',
      show: false,
      min: 0,
      max: distTotal,
    },
    yAxis: {
      type: 'category',
      show: false,
      data: [''],
    },
    series: dist.map((d) => ({
      name: t(`patchManager.complianceStatus.${d.filter}`, d.label),
      type: 'bar',
      stack: 'total',
      barWidth: 16,
      itemStyle: { color: FILTER_COLORS[d.filter || ''] || '#A4A19E', borderRadius: 0 },
      data: [d.count],
      emphasis: { focus: 'series' },
    })),
  }), [dist, distTotal, t]);

  return (
    <div className="relative overflow-x-hidden">
      {pageLoading && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-white/50">
          <Spin />
        </div>
      )}
      <KpiGrid items={kpis} />
      {/* 第2行：主机合规分布 */}
      <div className="mb-3.5 flex flex-wrap gap-3.5">
        <div className="flex min-h-0 min-w-0 max-w-full flex-[1_1_100%] flex-col overflow-hidden rounded-[10px] border border-[var(--color-border-1)] bg-[var(--color-bg-1)] px-4 py-3">
          <div className="mb-2.5 font-medium">{t('patchManager.dashboard.complianceDistribution')}</div>
          <div className="h-4 overflow-hidden rounded-lg">
            <ReactECharts
              option={distributionOption}
              className="h-full w-full"
              opts={{ renderer: 'svg' }}
            />
          </div>
          <Space size={16} wrap className="mt-2.5">
            {dist.map((d) => (
              <span key={d.label} className="text-xs text-[var(--color-text-2)]">
                <span className="mr-1.5 inline-block h-2 w-2 rounded-full" style={{ background: FILTER_COLORS[d.filter || ''] || '#A4A19E' }} />{d.label} {d.count}
              </span>
            ))}
          </Space>
          <div className="mt-2.5 text-xs text-[var(--color-text-3)]">
            {t('patchManager.dashboard.rateHelp', undefined, { rateHint, coverageHint })}
          </div>
        </div>
      </div>

      {/* 快捷操作 */}
      <Card
        title={<span><PlayCircleOutlined className="mr-1.5" />{t('patchManager.dashboard.quickActions')}</span>}
        className="mb-3.5 rounded-[10px]"
        styles={{ body: { padding: '12px 16px' } }}
      >
        <div className="flex flex-wrap gap-3">
          <Card size="small" className="min-w-[200px] flex-[1_1_200px] rounded-lg" styles={{ body: { padding: 14 } }}>
            <div className="mb-2 flex items-center gap-2.5">
              <div className="flex h-9 w-9 items-center justify-center rounded-full bg-[var(--color-fill-2)] text-[var(--color-primary)]"><PlayCircleOutlined /></div>
              <div className="font-medium">{t('patchManager.dashboard.assessNow')}</div>
            </div>
            <div className="mb-3 min-h-[34px] text-xs text-[var(--color-text-3)]">{t('patchManager.dashboard.assessNowDescription')}</div>
            <PermissionWrapper
              requiredPermissions={['Add']}
              permissionPath="/patch-manager/risk-execution"
              className="block!"
            >
              <Popconfirm title={t('patchManager.dashboard.confirmAssessAll')} onConfirm={handleImmediateAssess} okText={t('patchManager.confirm')} cancelText={t('patchManager.cancel')}>
                <Button type="primary" block icon={<PlayCircleOutlined />} loading={assessLoading}>{t('patchManager.dashboard.assessNow')}</Button>
              </Popconfirm>
            </PermissionWrapper>
          </Card>
          <Card size="small" className="min-w-[200px] flex-[1_1_200px] rounded-lg" styles={{ body: { padding: 14 } }}>
            <div className="mb-2 flex items-center gap-2.5">
              <div className="flex h-9 w-9 items-center justify-center rounded-full bg-[var(--color-fill-2)] text-[var(--color-primary)]"><PlusOutlined /></div>
              <div className="font-medium">{t('patchManager.dashboard.addTarget')}</div>
            </div>
            <div className="mb-3 min-h-[34px] text-xs text-[var(--color-text-3)]">{t('patchManager.dashboard.addTargetDescription')}</div>
            <Button type="primary" block icon={<PlusOutlined />} onClick={() => router.push('/patch-manager/target')}>{t('patchManager.dashboard.addTarget')}</Button>
          </Card>
          <Card size="small" className="min-w-[200px] flex-[1_1_200px] rounded-lg" styles={{ body: { padding: 14 } }}>
            <div className="mb-2 flex items-center gap-2.5">
              <div className="flex h-9 w-9 items-center justify-center rounded-full bg-[var(--color-fill-2)] text-[var(--color-primary)]"><PlusOutlined /></div>
              <div className="font-medium">{t('patchManager.dashboard.createBaseline')}</div>
            </div>
            <div className="mb-3 min-h-[34px] text-xs text-[var(--color-text-3)]">{t('patchManager.dashboard.createBaselineDescription')}</div>
            <Button type="primary" block icon={<PlusOutlined />} onClick={() => router.push('/patch-manager/baseline')}>{t('patchManager.dashboard.createBaseline')}</Button>
          </Card>
          <Card size="small" className="min-w-[200px] flex-[1_1_200px] rounded-lg" styles={{ body: { padding: 14 } }}>
            <div className="mb-2 flex items-center gap-2.5">
              <div className="flex h-9 w-9 items-center justify-center rounded-full bg-[var(--color-fill-2)] text-[var(--color-primary)]"><FileTextOutlined /></div>
              <div className="font-medium">{t('patchManager.dashboard.executionRecords')}</div>
            </div>
            <div className="mb-3 min-h-[34px] text-xs text-[var(--color-text-3)]">{t('patchManager.dashboard.executionRecordsDescription')}</div>
            <Button type="primary" block icon={<FileTextOutlined />} onClick={() => router.push('/patch-manager/risk-execution')}>{t('patchManager.dashboard.viewRecords')}</Button>
          </Card>
        </div>
      </Card>

      {/* 第3行：最近执行 + TOP风险 */}
      <div ref={bottomRef} className="flex flex-nowrap gap-3.5" style={{ height: tableHeight }}>
        <Card
          title={<span><FileTextOutlined className="mr-1.5" />{t('patchManager.dashboard.recentExecutions')}</span>}
          className="flex h-full min-w-0 flex-[2_1_0] flex-col rounded-[10px]"
          styles={{ body: { padding: '10px 10px', flex: 1, overflow: 'hidden' } }}
          extra={<Button type="link" size="small" onClick={() => router.push('/patch-manager/risk-execution')}>{t('patchManager.dashboard.viewMore')}</Button>}
        >
          <div className={styles.dashboardTable} style={tableBodyStyle}>
            <CustomTable<RecentTaskItem>
              size="small"
              pagination={false}
              rowKey="id"
              dataSource={stats?.recent_tasks || []}
              scroll={{ y: tableScrollY }}
              columns={[
                { title: t('patchManager.dashboard.taskName'), dataIndex: 'name', width: 250, ellipsis: true },
                { title: t('patchManager.execution.type'), dataIndex: 'task_type_display', width: 90, render: (value: string) => <Tag>{value}</Tag> },
                { title: t('patchManager.risk.executionMode'), dataIndex: 'execution_mode', width: 110, render: (_: unknown, r: RecentTaskItem) => recentExecutionText(r) },
                { title: t('patchManager.execution.status'), dataIndex: 'status', width: 110, render: (_: unknown, r: RecentTaskItem) => <Tag color={r.status_color}>{t(`patchManager.execution.statuses.${r.status_code}`, r.status)}</Tag> },
                { title: t('patchManager.createTime'), dataIndex: 'created_at', width: 170, render: (_: string, r: RecentTaskItem) => <span className="text-[var(--color-text-3)]">{convertToLocalizedTime(r.created_at) || '--'}</span> },
              ]}
            />
          </div>
        </Card>

        <Card
          title={<span><ArrowRightOutlined className="mr-1.5" />{t('patchManager.dashboard.topRiskPatches')}</span>}
          className="flex h-full min-w-0 flex-[1_1_0] flex-col rounded-[10px]"
          styles={{ body: { padding: '10px 10px', flex: 1, overflow: 'hidden' } }}
          extra={<Button type="link" size="small" onClick={() => router.push('/patch-manager/risk-pending')}>{t('patchManager.dashboard.viewAll')}</Button>}
        >
          <div className={styles.dashboardTable} style={tableBodyStyle}>
            <CustomTable<TopRiskItem>
              size="small"
              pagination={false}
              rowKey="id"
              dataSource={stats?.top_risks || []}
              scroll={{ y: tableScrollY }}
              columns={[
                { title: t('patchManager.dashboard.patchRequirement'), dataIndex: 'patch', ellipsis: true },
                { title: t('patchManager.dashboard.affectedTargets'), dataIndex: 'hosts', width: 90, render: (v: number) => t('patchManager.dashboard.targetCount', undefined, { count: v }) },
                { title: t('patchManager.severity'), dataIndex: 'severity', width: 90, render: (v: string) => <SeverityTag severity={v} /> },
              ]}
            />
          </div>
        </Card>
      </div>
    </div>
  );
}
