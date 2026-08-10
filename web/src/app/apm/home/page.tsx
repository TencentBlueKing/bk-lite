'use client';

import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import Link from 'next/link';
import {
  ApartmentOutlined,
  ApiOutlined,
  AppstoreOutlined,
  BellOutlined,
  DashboardOutlined,
  FieldTimeOutlined,
  FireOutlined,
  RocketOutlined,
  TagsOutlined,
  ThunderboltOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { Button, Col, Row, Segmented, Space, Spin, Typography } from 'antd';
import useApmApi from '@/app/apm/api';
import DonutChart, { HEALTH_DONUT_COLORS } from '@/app/apm/components/home/donut-chart';
import SectionCard, {
  SectionEmpty,
  StatusPill,
} from '@/app/apm/components/home/section-card';
import Sparkline, { toSparklineData } from '@/app/apm/components/home/sparkline';
import Top5BarChart, {
  errorRateBarColor,
  formatTopErrorSubValue,
  formatTopP95SubValue,
  p95BarColor,
} from '@/app/apm/components/home/top5-bar-chart';
import {
  formatLatency,
  formatMetricEmpty,
  formatRelativeTime,
  formatThroughput,
} from '@/app/apm/components/metric-format';
import type {
  ApmDashboard,
  ApmDashboardAlertRow,
  ApmDashboardHealthBucket,
  ApmDashboardKpiData,
  ApmDashboardSection,
  ApmDashboardSloRow,
  ApmDashboardTopRow,
  ApmTimeWindow,
  ApmTopologyHealth,
} from '@/app/apm/types';

const { Text, Title, Paragraph } = Typography;

const TIME_WINDOWS: ApmTimeWindow[] = ['15m', '1h', '4h', '1d', '7d'];

const WINDOW_LABEL: Record<ApmTimeWindow, string> = {
  '15m': '近窗 15 分钟',
  '1h': '近窗 1 小时',
  '4h': '近窗 4 小时',
  '1d': '近窗 1 天',
  '7d': '近窗 7 天',
};

const ALERT_SEVERITY: Record<
  ApmDashboardAlertRow['severity'],
  { label: string; tone: 'danger' | 'warning' }
> = {
  critical: { label: '严重', tone: 'danger' },
  warning: { label: '警告', tone: 'warning' },
};

const HEALTH_LINK: Record<ApmTopologyHealth, string> = {
  healthy: '/apm/services',
  warning: '/apm/services?health=warning',
  critical: '/apm/services?health=critical',
  unknown: '/apm/services',
};

interface KpiCardConfig {
  key: string;
  label: string;
  icon: ReactNode;
  iconBg: string;
  iconColor: string;
  value: ReactNode;
  unit?: string;
  trend: number[];
  sparkColor: string;
}

function softBg(token: string, pct = 12): string {
  return `color-mix(in srgb, ${token} ${pct}%, var(--color-bg))`;
}

function buildKpiCards(data: ApmDashboardKpiData): KpiCardConfig[] {
  const spark = data.sparklines;
  return [
    {
      key: 'apps',
      label: '应用数量',
      icon: <ApartmentOutlined />,
      iconBg: 'var(--color-primary-bg-active)',
      iconColor: 'var(--color-primary)',
      value: data.application_count,
      trend: toSparklineData(spark.application_count),
      sparkColor: 'var(--color-primary)',
    },
    {
      key: 'services',
      label: '服务数量',
      icon: <AppstoreOutlined />,
      iconBg: 'var(--color-primary-bg-active)',
      iconColor: 'var(--color-primary)',
      value: data.service_count,
      trend: toSparklineData(spark.service_count),
      sparkColor: 'var(--color-primary)',
    },
    {
      key: 'alerts',
      label: '活跃告警数',
      icon: <BellOutlined />,
      iconBg: softBg('var(--color-fail)', 10),
      iconColor: 'var(--color-fail)',
      value: data.active_alert_count,
      trend: toSparklineData(spark.active_alert_count),
      sparkColor: 'var(--color-fail)',
    },
    {
      key: 'requests',
      label: '请求量',
      icon: <ApiOutlined />,
      iconBg: 'var(--color-primary-bg-active)',
      iconColor: 'var(--color-primary)',
      value: data.request_rate === null ? formatMetricEmpty() : formatThroughput(data.request_rate),
      unit: data.request_rate === null ? undefined : 'req/s',
      trend: toSparklineData(spark.request_rate),
      sparkColor: 'var(--color-primary)',
    },
    {
      key: 'errors',
      label: '错误请求数',
      icon: <WarningOutlined />,
      iconBg: softBg('var(--color-fail)', 10),
      iconColor: 'var(--color-fail)',
      value: data.error_request_rate === null ? formatMetricEmpty() : data.error_request_rate.toFixed(1),
      unit: data.error_request_rate === null ? undefined : '/s',
      trend: toSparklineData(spark.error_request_rate),
      sparkColor: 'var(--color-fail)',
    },
    {
      key: 'p95',
      label: 'P95 延迟',
      icon: <FieldTimeOutlined />,
      iconBg: softBg('var(--theme-color-status-warning)', 12),
      iconColor: 'var(--theme-color-status-warning)',
      value: data.p95_ms === null ? formatMetricEmpty() : formatLatency(data.p95_ms),
      trend: toSparklineData(spark.p95_ms),
      sparkColor: 'var(--theme-color-status-warning)',
    },
  ];
}

function KpiCard({ kpi }: { kpi: KpiCardConfig }) {
  return (
    <div className="flex h-full min-h-[132px] flex-col gap-1 rounded-[6px] border border-[var(--color-border)] bg-[var(--color-bg)] px-5 pb-3.5 pt-[18px]">
      <div className="flex items-center gap-2">
        <span
          className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded text-sm"
          style={{ background: kpi.iconBg, color: kpi.iconColor }}
        >
          {kpi.icon}
        </span>
        <span className="text-xs font-medium text-[var(--color-text-3)]">{kpi.label}</span>
      </div>
      <div className="mt-1 flex items-baseline gap-2">
        <span className="text-[28px] font-semibold leading-[1.1] tracking-tight tabular-nums text-[var(--color-text-1)]">
          {kpi.value}
        </span>
        {kpi.unit ? <span className="text-xs text-[var(--color-text-3)]">{kpi.unit}</span> : null}
      </div>
      <div className="mt-auto min-w-0 pt-1">
        <Sparkline data={kpi.trend} height={28} color={kpi.sparkColor} kind="area" />
      </div>
    </div>
  );
}

function HomeEmptyState() {
  return (
    <div className="mt-1 rounded-[6px] border border-[var(--color-border)] bg-[var(--color-bg)] px-8 py-20 text-center">
      <div className="mx-auto mb-5 inline-flex h-14 w-14 items-center justify-center rounded-xl bg-[var(--color-primary-bg-active)]">
        <RocketOutlined className="text-2xl text-[var(--color-primary)]" />
      </div>
      <Title level={4} className="!mb-2 !font-semibold">
        还没有接入任何应用
      </Title>
      <Paragraph type="secondary" className="!mb-6 text-[13px]">
        前往集成菜单完成首次接入，数分钟内即可在首页看到 6 个 KPI 与 7 段汇总。
      </Paragraph>
      <Button type="primary" href="/apm/integration/add">
        前往集成菜单
      </Button>
    </div>
  );
}

function FailedSection({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="rounded-[6px] border border-[var(--color-border)] bg-[var(--color-bg)] px-6 py-10 text-center">
      <Button type="link" onClick={onRetry}>
        加载失败，点击重试
      </Button>
    </div>
  );
}

function HealthLegendRow({ bucket, total }: { bucket: ApmDashboardHealthBucket; total: number }) {
  const pct = total > 0 ? ((bucket.count / total) * 100).toFixed(0) : '0';
  return (
    <Link
      href={HEALTH_LINK[bucket.key]}
      className="flex items-center gap-2 text-[13px] hover:opacity-80"
    >
      <span
        className="h-2 w-2 shrink-0 rounded-sm"
        style={{ background: HEALTH_DONUT_COLORS[bucket.key] }}
      />
      <span className="flex-1 font-medium text-[var(--color-text-1)]">{bucket.label}</span>
      <span className="font-semibold tabular-nums text-[var(--color-text-1)]">{bucket.count}</span>
      <span className="min-w-9 text-right tabular-nums text-[var(--color-text-4)]">({pct}%)</span>
    </Link>
  );
}

function SloOverviewList({ items }: { items: ApmDashboardSloRow[] }) {
  return (
    <div className="flex flex-col">
      <div className="mb-1 grid grid-cols-[minmax(0,1fr)_88px_72px_64px] gap-2 border-b border-[var(--color-border)] pb-2 text-[12px] text-[var(--color-text-4)]">
        <span>服务</span>
        <span className="text-right">可用性目标</span>
        <span className="text-right">达成率</span>
        <span className="text-center">状态</span>
      </div>
      {items.map((row, index) => (
        <div
          key={row.id}
          className={`grid grid-cols-[minmax(0,1fr)_88px_72px_64px] items-center gap-2 py-2.5 ${
            index < items.length - 1 ? 'border-b border-[var(--color-border)]' : ''
          }`}
        >
          <Link
            href={`/apm/services/${row.service_id}`}
            className="truncate text-[13px] font-medium text-[var(--color-text-1)] hover:text-[var(--color-primary)]"
            title={row.service_name}
          >
            {row.service_name}
          </Link>
          <span className="text-right text-[13px] tabular-nums text-[var(--color-text-3)]">
            {row.objective.toFixed(row.objective % 1 === 0 ? 1 : 2)}%
          </span>
          <span
            className="text-right text-[13px] font-semibold tabular-nums"
            style={{ color: row.met ? 'var(--color-success)' : 'var(--color-fail)' }}
          >
            {row.current_rate.toFixed(2)}%
          </span>
          <span className="flex justify-center">
            <StatusPill label={row.met ? '达成' : '未达成'} tone={row.met ? 'success' : 'danger'} />
          </span>
        </div>
      ))}
    </div>
  );
}

export default function ApmHomePage() {
  const { getDashboard, isLoading: authLoading } = useApmApi();
  const [timeWindow, setTimeWindow] = useState<ApmTimeWindow>('1h');
  const [dashboard, setDashboard] = useState<ApmDashboard | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    if (authLoading) return;
    setLoading(true);
    setLoadFailed(false);
    getDashboard(timeWindow)
      .then((payload) => {
        setDashboard(payload);
        setLoadFailed(false);
      })
      .catch(() => {
        setDashboard(null);
        setLoadFailed(true);
      })
      .finally(() => setLoading(false));
  }, [authLoading, getDashboard, timeWindow]);

  useEffect(() => {
    load();
  }, [load]);

  const kpiCards = useMemo(
    () => (dashboard?.kpis.status === 'ok' && dashboard.kpis.data ? buildKpiCards(dashboard.kpis.data) : []),
    [dashboard],
  );

  const healthData = dashboard?.health.status === 'ok' ? dashboard.health.data : undefined;
  const sloItems: ApmDashboardSloRow[] =
    dashboard?.slos.status === 'ok' && dashboard.slos.data?.items
      ? dashboard.slos.data.items
      : dashboard?.slos.status === 'empty'
        ? []
        : [];
  const alertItems: ApmDashboardAlertRow[] =
    dashboard?.alerts.status === 'ok' && dashboard.alerts.data?.items
      ? dashboard.alerts.data.items
      : dashboard?.alerts.status === 'empty'
        ? []
        : [];
  const topErrorItems: ApmDashboardTopRow[] =
    dashboard?.top_error_rate.status === 'ok' && dashboard.top_error_rate.data?.items
      ? dashboard.top_error_rate.data.items
      : [];
  const topP95Items: ApmDashboardTopRow[] =
    dashboard?.top_p95.status === 'ok' && dashboard.top_p95.data?.items ? dashboard.top_p95.data.items : [];

  const sectionFailed = (section: ApmDashboardSection<unknown> | undefined) => section?.status === 'failed';

  return (
    <div className="h-full min-h-full overflow-auto px-6 pb-10 pt-4 lg:px-8">
      <div className="mb-3 flex items-center justify-end px-1">
        <Space size={6} align="center">
          <Text type="secondary" className="text-xs">
            时间窗
          </Text>
          <Segmented
            size="small"
            value={timeWindow}
            onChange={(value) => setTimeWindow(value as ApmTimeWindow)}
            options={TIME_WINDOWS.map((item) => ({ value: item, label: item }))}
          />
        </Space>
      </div>

      {loading && !dashboard ? (
        <div className="flex justify-center py-24">
          <Spin />
        </div>
      ) : loadFailed ? (
        <FailedSection onRetry={load} />
      ) : dashboard?.empty ? (
        <HomeEmptyState />
      ) : (
        <>
          {sectionFailed(dashboard?.kpis) ? (
            <FailedSection onRetry={load} />
          ) : (
            <Row gutter={[12, 12]} className="!mb-4">
              {kpiCards.map((kpi) => (
                <Col key={kpi.key} xs={12} sm={8} md={8} lg={4} xl={4}>
                  <KpiCard kpi={kpi} />
                </Col>
              ))}
            </Row>
          )}

          <Row gutter={[16, 16]}>
            <Col xs={24} lg={8}>
              <SectionCard
                icon={<DashboardOutlined className="text-[var(--color-primary)]" />}
                title="服务健康度分布"
                subtitle={WINDOW_LABEL[timeWindow]}
                viewAllHref="/apm/services"
                failed={sectionFailed(dashboard?.health)}
                onRetry={load}
                bodyMinHeight={188}
              >
                {healthData && healthData.total > 0 ? (
                  <div className="grid grid-cols-1 items-center gap-4 sm:grid-cols-[180px_1fr]">
                    <div className="relative mx-auto h-[180px] w-[180px]">
                      <DonutChart
                        data={healthData.buckets
                          .filter((bucket) => bucket.count > 0)
                          .map((bucket) => ({
                            label: bucket.label,
                            count: bucket.count,
                            color: HEALTH_DONUT_COLORS[bucket.key],
                          }))}
                      />
                      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                        <span className="text-[32px] font-semibold leading-tight tracking-tight tabular-nums text-[var(--color-text-1)]">
                          {healthData.total}
                        </span>
                        <span className="mt-0.5 text-[11px] text-[var(--color-text-4)]">总服务数</span>
                      </div>
                    </div>
                    <div className="flex flex-col gap-2.5">
                      {healthData.buckets.map((bucket) => (
                        <HealthLegendRow key={bucket.key} bucket={bucket} total={healthData.total} />
                      ))}
                    </div>
                  </div>
                ) : (
                  <SectionEmpty>暂无服务数据</SectionEmpty>
                )}
              </SectionCard>
            </Col>

            <Col xs={24} lg={8}>
              <SectionCard
                icon={<DashboardOutlined className="text-[var(--color-primary)]" />}
                title="SLO 概览"
                subtitle="已配置 SLO"
                viewAllHref="/apm/services/slo"
                failed={sectionFailed(dashboard?.slos)}
                onRetry={load}
              >
                {sloItems.length === 0 ? (
                  <SectionEmpty>
                    <div>
                      暂无 SLO 配置
                      <div className="mt-2">
                        <Link href="/apm/services/slo" className="text-[var(--color-primary)] hover:underline">
                          前往配置 →
                        </Link>
                      </div>
                    </div>
                  </SectionEmpty>
                ) : (
                  <SloOverviewList items={sloItems} />
                )}
              </SectionCard>
            </Col>

            <Col xs={24} lg={8}>
              <SectionCard
                icon={<BellOutlined className="text-[var(--color-fail)]" />}
                title="实时告警"
                subtitle="未恢复"
                viewAllHref="/apm/events/alerts"
                failed={sectionFailed(dashboard?.alerts)}
                onRetry={load}
              >
                {alertItems.length === 0 ? (
                  <SectionEmpty tone="success">✓ 一切正常，无未恢复告警</SectionEmpty>
                ) : (
                  <div className="flex flex-col">
                    {alertItems.map((alert, index) => {
                      const severity = ALERT_SEVERITY[alert.severity];
                      return (
                        <div
                          key={alert.id}
                          className={`flex items-center gap-2.5 py-2.5 ${
                            index < alertItems.length - 1 ? 'border-b border-[var(--color-border)]' : ''
                          }`}
                        >
                          <span
                            className="h-1.5 w-1.5 shrink-0 rounded-full"
                            style={{
                              background:
                                severity.tone === 'danger'
                                  ? 'var(--color-fail)'
                                  : 'var(--theme-color-status-warning)',
                            }}
                          />
                          <div className="min-w-0 flex-1">
                            <Link
                              href={`/apm/events/alerts?service=${encodeURIComponent(alert.service)}`}
                              className="block truncate text-[13px] font-medium text-[var(--color-text-1)] hover:text-[var(--color-primary)]"
                              title={`${alert.service} · ${alert.name}`}
                            >
                              {alert.service}
                            </Link>
                            <div className="mt-0.5 text-[11px] text-[var(--color-text-4)]">{alert.name}</div>
                          </div>
                          <StatusPill label={severity.label} tone={severity.tone} />
                          <span className="min-w-[60px] text-right text-[11px] tabular-nums text-[var(--color-text-4)]">
                            {formatRelativeTime(alert.started_at)}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </SectionCard>
            </Col>
          </Row>

          <Row gutter={[16, 16]} className="!mt-4">
            <Col xs={24} lg={8}>
              <SectionCard
                icon={<FireOutlined className="text-[var(--color-fail)]" />}
                title="服务 TOP5 (按错误率)"
                viewAllHref="/apm/services"
                failed={sectionFailed(dashboard?.top_error_rate)}
                onRetry={load}
              >
                {topErrorItems.length === 0 ? (
                  <SectionEmpty>暂无错误率数据</SectionEmpty>
                ) : (
                  <Top5BarChart
                    window={timeWindow}
                    rows={topErrorItems.map((row) => ({
                      service_id: row.service_id,
                      name: row.service_name,
                      environment: row.environment,
                      value: row.value,
                      sub: formatTopErrorSubValue(row.sub_value),
                    }))}
                    valueFormatter={(value) => `${value.toFixed(2)}%`}
                    colorOf={errorRateBarColor}
                    subField="P95"
                  />
                )}
              </SectionCard>
            </Col>

            <Col xs={24} lg={8}>
              <SectionCard
                icon={<ThunderboltOutlined className="text-[var(--theme-color-status-warning)]" />}
                title="P95 响应时间 TOP5"
                viewAllHref="/apm/services"
                failed={sectionFailed(dashboard?.top_p95)}
                onRetry={load}
              >
                {topP95Items.length === 0 ? (
                  <SectionEmpty>暂无 P95 数据</SectionEmpty>
                ) : (
                  <Top5BarChart
                    window={timeWindow}
                    rows={topP95Items.map((row) => ({
                      service_id: row.service_id,
                      name: row.service_name,
                      environment: row.environment,
                      value: row.value,
                      sub: formatTopP95SubValue(row.sub_value),
                    }))}
                    valueFormatter={(value) => `${Math.round(value)}ms`}
                    colorOf={p95BarColor}
                    subField="吞吐"
                  />
                )}
              </SectionCard>
            </Col>

            <Col xs={24} lg={8}>
              <SectionCard
                icon={<TagsOutlined className="text-[var(--color-primary)]" />}
                title="版本发布变更"
                subtitle="近 7 天"
                viewAllHref="/apm/services"
                failed={sectionFailed(dashboard?.releases)}
                onRetry={load}
              >
                <SectionEmpty>近 7 天无发布</SectionEmpty>
              </SectionCard>
            </Col>
          </Row>
        </>
      )}
    </div>
  );
}
