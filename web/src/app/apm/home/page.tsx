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
import { Button, Col, Row, Segmented, Skeleton, Space, Typography } from 'antd';
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
  formatPercentage,
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
import ApmRouteShell from '@/app/apm/components/apm-route-shell';
import SummaryMetricCard from '@/components/summary-metric-card';
import { useTranslation } from '@/utils/i18n';

const { Text, Paragraph } = Typography;

const TIME_WINDOWS: ApmTimeWindow[] = ['15m', '1h', '4h', '1d', '7d'];

const WINDOW_LABEL_KEYS: Record<ApmTimeWindow, string> = {
  '15m': 'apm.home.window15m',
  '1h': 'apm.home.window1h',
  '4h': 'apm.home.window4h',
  '1d': 'apm.home.window1d',
  '7d': 'apm.home.window7d',
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

function buildKpiCards(
  data: ApmDashboardKpiData,
  t: (id: string, defaultMessage?: string, values?: Record<string, string | number>) => string,
): KpiCardConfig[] {
  const spark = data.sparklines;
  return [
    {
      key: 'apps',
      label: t('apm.home.kpiApps', '应用数量'),
      icon: <ApartmentOutlined aria-hidden="true" />,
      iconBg: 'var(--color-primary-bg-active)',
      iconColor: 'var(--color-primary)',
      value: data.application_count,
      trend: toSparklineData(spark.application_count),
      sparkColor: 'var(--color-primary)',
    },
    {
      key: 'services',
      label: t('apm.home.kpiServices', '服务数量'),
      icon: <AppstoreOutlined aria-hidden="true" />,
      iconBg: 'var(--color-primary-bg-active)',
      iconColor: 'var(--color-primary)',
      value: data.service_count,
      trend: toSparklineData(spark.service_count),
      sparkColor: 'var(--color-primary)',
    },
    {
      key: 'alerts',
      label: t('apm.home.kpiAlerts', '活跃告警数'),
      icon: <BellOutlined aria-hidden="true" />,
      iconBg: softBg('var(--color-fail)', 10),
      iconColor: 'var(--color-fail)',
      value: data.active_alert_count,
      trend: toSparklineData(spark.active_alert_count),
      sparkColor: 'var(--color-fail)',
    },
    {
      key: 'requests',
      label: t('apm.home.kpiRequests', '请求量'),
      icon: <ApiOutlined aria-hidden="true" />,
      iconBg: 'var(--color-primary-bg-active)',
      iconColor: 'var(--color-primary)',
      value: data.request_rate === null ? formatMetricEmpty(false, t) : formatThroughput(data.request_rate, false, t),
      unit: data.request_rate === null ? undefined : t('apm.common.requestsPerSecondUnit', 'req/s'),
      trend: toSparklineData(spark.request_rate),
      sparkColor: 'var(--color-primary)',
    },
    {
      key: 'errors',
      label: t('apm.home.kpiErrors', '错误请求数'),
      icon: <WarningOutlined aria-hidden="true" />,
      iconBg: softBg('var(--color-fail)', 10),
      iconColor: 'var(--color-fail)',
      value: data.error_request_rate === null ? formatMetricEmpty(false, t) : formatThroughput(data.error_request_rate, false, t),
      unit: data.error_request_rate === null ? undefined : t('apm.common.requestsPerSecondUnit', 'req/s'),
      trend: toSparklineData(spark.error_request_rate),
      sparkColor: 'var(--color-fail)',
    },
    {
      key: 'p95',
      label: t('apm.home.kpiP95', 'P95 延迟'),
      icon: <FieldTimeOutlined aria-hidden="true" />,
      iconBg: softBg('var(--theme-color-status-warning)', 12),
      iconColor: 'var(--theme-color-status-warning)',
      value: data.p95_ms === null ? formatMetricEmpty(false, t) : formatLatency(data.p95_ms, false, t),
      trend: toSparklineData(spark.p95_ms),
      sparkColor: 'var(--theme-color-status-warning)',
    },
  ];
}

function HomeSkeleton() {
  const { t } = useTranslation();
  return (
    <div aria-label={t('apm.home.loading', '加载 APM 首页数据')} aria-busy="true">
      <Row gutter={[12, 12]} className="!mb-4">
        {Array.from({ length: 6 }, (_, index) => (
          <Col key={index} xs={24} sm={12} md={8} lg={4}>
            <div className="min-h-[132px] rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
              <Skeleton active paragraph={{ rows: 2 }} title={{ width: '45%' }} />
            </div>
          </Col>
        ))}
      </Row>
      <Row gutter={[16, 16]}>
        {Array.from({ length: 3 }, (_, index) => (
          <Col key={index} xs={24} lg={8}>
            <div className="min-h-72 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
              <Skeleton active paragraph={{ rows: 6 }} title={{ width: '35%' }} />
            </div>
          </Col>
        ))}
      </Row>
    </div>
  );
}

function HomeEmptyState() {
  const { t } = useTranslation();
  return (
    <div className="mt-1 rounded-[6px] border border-[var(--color-border)] bg-[var(--color-bg)] px-8 py-20 text-center">
      <div className="mx-auto mb-5 inline-flex h-10 w-10 items-center justify-center rounded-lg bg-[var(--color-primary-bg-active)]">
        <RocketOutlined aria-hidden="true" className="text-base text-[var(--color-primary)]" />
      </div>
      <p className="mb-2 text-base font-semibold leading-6 text-[var(--color-text-1)]">
        {t('apm.home.emptyTitle', '还没有接入任何应用')}
      </p>
      <Paragraph type="secondary" className="!mb-6 text-sm">
        {t('apm.home.emptyDescription', '前往集成菜单完成首次接入，数分钟内即可在首页看到 6 个 KPI 与 7 段汇总。')}
      </Paragraph>
      <Button type="primary" href="/apm/integration/add">
        {t('apm.home.emptyAction', '前往集成菜单')}
      </Button>
    </div>
  );
}

function FailedSection({ onRetry }: { onRetry: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="rounded-[6px] border border-[var(--color-border)] bg-[var(--color-bg)] px-6 py-10 text-center">
      <Button type="link" onClick={onRetry}>
        {t('apm.common.loadFailedRetry', '加载失败，点击重试')}
      </Button>
    </div>
  );
}

function HealthLegendRow({ bucket, total }: { bucket: ApmDashboardHealthBucket; total: number }) {
  const pct = formatPercentage(total > 0 ? (bucket.count / total) * 100 : 0, 0);
  return (
    <Link
      href={HEALTH_LINK[bucket.key]}
      className="flex items-center gap-2 text-sm hover:opacity-80"
    >
      <span
        className="h-2 w-2 shrink-0 rounded-sm"
        style={{ background: HEALTH_DONUT_COLORS[bucket.key] }}
      />
      <span className="flex-1 font-medium text-[var(--color-text-1)]">{bucket.label}</span>
      <span className="font-semibold tabular-nums text-[var(--color-text-1)]">{bucket.count}</span>
      <span className="min-w-9 text-right tabular-nums text-[var(--color-text-4)]">({pct})</span>
    </Link>
  );
}

function SloOverviewList({ items }: { items: ApmDashboardSloRow[] }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col">
      <div className="mb-1 grid grid-cols-[minmax(0,1fr)_88px_72px_64px] gap-2 border-b border-[var(--color-border)] pb-2 text-[12px] text-[var(--color-text-4)]">
        <span>{t('apm.home.sloService', '服务')}</span>
        <span className="text-right">{t('apm.home.sloObjective', '可用性目标')}</span>
        <span className="text-right">{t('apm.home.sloRate', '达成率')}</span>
        <span className="text-center">{t('apm.home.sloStatus', '状态')}</span>
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
            className="truncate text-sm font-medium text-[var(--color-text-1)] hover:text-[var(--color-primary)]"
            title={row.service_name}
          >
            {row.service_name}
          </Link>
          <span className="text-right text-sm tabular-nums text-[var(--color-text-3)]">
            {formatPercentage(row.objective, row.objective % 1 === 0 ? 1 : 2)}
          </span>
          <span
            className="text-right text-sm font-semibold tabular-nums"
            style={{ color: row.met ? 'var(--color-success)' : 'var(--color-fail)' }}
          >
            {formatPercentage(row.current_rate, 2)}
          </span>
          <span className="flex justify-center">
            <StatusPill label={row.met ? t('apm.home.sloMet', '达成') : t('apm.home.sloUnmet', '未达成')} tone={row.met ? 'success' : 'danger'} />
          </span>
        </div>
      ))}
    </div>
  );
}

export default function ApmHomePage() {
  const { t } = useTranslation();
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
    () => (dashboard?.kpis.status === 'ok' && dashboard.kpis.data ? buildKpiCards(dashboard.kpis.data, t) : []),
    [dashboard, t],
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
    <ApmRouteShell title={t('apm.home.title', '首页')} description={t('apm.home.description', '查看应用性能总览、健康分布与待处理告警。')}>
      <div className="mb-3 flex items-center justify-end px-1">
        <Space size={6} align="center">
          <Text type="secondary" className="text-xs">
            {t('apm.common.timeWindow', '时间窗')}
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
        <HomeSkeleton />
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
                <Col key={kpi.key} xs={24} sm={12} md={8} lg={4} xl={4}>
                  <SummaryMetricCard
                    className="h-full min-h-[132px] rounded-lg px-4 pb-3 pt-4"
                    contentClassName="flex flex-1 flex-col"
                    footer={(
                      <div className="mt-auto min-w-0 pt-2">
                        <Sparkline data={kpi.trend} height={28} color={kpi.sparkColor} kind="area" />
                      </div>
                    )}
                    footerClassName="mt-auto"
                    framed
                    headerSpacing="compact"
                    icon={kpi.icon}
                    iconBackground={kpi.iconBg}
                    iconClassName="h-7 w-7 !rounded text-sm"
                    iconColor={kpi.iconColor}
                    label={kpi.label}
                    labelClassName="!text-xs !font-medium"
                    layout="vertical"
                    maxFontSize={16}
                    minFontSize={16}
                    unit={kpi.unit}
                    value={kpi.value}
                    valueClassName="!font-semibold !tracking-tight"
                  />
                </Col>
              ))}
            </Row>
          )}

          <Row gutter={[16, 16]}>
            <Col xs={24} lg={8}>
              <SectionCard
                icon={<DashboardOutlined aria-hidden="true" className="text-[var(--color-primary)]" />}
                title={t('apm.home.healthTitle', '服务健康度分布')}
                subtitle={t(WINDOW_LABEL_KEYS[timeWindow])}
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
                        <span className="text-base font-semibold leading-6 tabular-nums text-[var(--color-text-1)]">
                          {healthData.total}
                        </span>
                        <span className="mt-0.5 text-xs text-[var(--color-text-4)]">{t('apm.home.healthTotal', '总服务数')}</span>
                      </div>
                    </div>
                    <div className="flex flex-col gap-2.5">
                      {healthData.buckets.map((bucket) => (
                        <HealthLegendRow key={bucket.key} bucket={bucket} total={healthData.total} />
                      ))}
                    </div>
                  </div>
                ) : (
                  <SectionEmpty>{t('apm.home.healthEmpty', '暂无服务数据')}</SectionEmpty>
                )}
              </SectionCard>
            </Col>

            <Col xs={24} lg={8}>
              <SectionCard
                icon={<DashboardOutlined aria-hidden="true" className="text-[var(--color-primary)]" />}
                title={t('apm.home.sloTitle', 'SLO 概览')}
                subtitle={t('apm.home.sloSubtitle', '已配置 SLO')}
                viewAllHref="/apm/services/slo"
                failed={sectionFailed(dashboard?.slos)}
                onRetry={load}
              >
                {sloItems.length === 0 ? (
                  <SectionEmpty>
                    <div>
                      {t('apm.home.sloEmpty', '暂无 SLO 配置')}
                      <div className="mt-2">
                        <Link href="/apm/services/slo" className="text-[var(--color-primary)] hover:underline">
                          {t('apm.home.sloConfigure', '前往配置 →')}
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
                icon={<BellOutlined aria-hidden="true" className="text-[var(--color-fail)]" />}
                title={t('apm.home.alertsTitle', '实时告警')}
                subtitle={t('apm.home.alertsSubtitle', '未恢复')}
                viewAllHref="/apm/events/alerts"
                failed={sectionFailed(dashboard?.alerts)}
                onRetry={load}
              >
                {alertItems.length === 0 ? (
                  <SectionEmpty tone="success">{t('apm.home.alertsEmpty', '一切正常，无未恢复告警')}</SectionEmpty>
                ) : (
                  <div className="flex flex-col">
                    {alertItems.map((alert, index) => {
                      const severity = {
                        label: t(
                          alert.severity === 'critical' ? 'apm.severity.critical' : 'apm.severity.warning',
                          alert.severity === 'critical' ? '严重' : '警告',
                        ),
                        tone: (alert.severity === 'critical' ? 'danger' : 'warning') as 'danger' | 'warning',
                      };
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
                              className="block truncate text-sm font-medium text-[var(--color-text-1)] hover:text-[var(--color-primary)]"
                              title={`${alert.service} · ${alert.name}`}
                            >
                              {alert.service}
                            </Link>
                            <div className="mt-0.5 text-xs text-[var(--color-text-4)]">{alert.name}</div>
                          </div>
                          <StatusPill label={severity.label} tone={severity.tone} />
                          <span className="min-w-[60px] text-right text-xs tabular-nums text-[var(--color-text-4)]">
                            {formatRelativeTime(alert.started_at, t)}
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
                icon={<FireOutlined aria-hidden="true" className="text-[var(--color-fail)]" />}
                title={t('apm.home.topErrorTitle', '服务 TOP5 (按错误率)')}
                viewAllHref="/apm/services"
                failed={sectionFailed(dashboard?.top_error_rate)}
                onRetry={load}
              >
                {topErrorItems.length === 0 ? (
                  <SectionEmpty>{t('apm.home.topErrorEmpty', '暂无错误率数据')}</SectionEmpty>
                ) : (
                  <Top5BarChart
                    window={timeWindow}
                    rows={topErrorItems.map((row) => ({
                      service_id: row.service_id,
                      name: row.service_name,
                      environment: row.environment,
                      value: row.value,
                      sub: formatTopErrorSubValue(row.sub_value, t),
                    }))}
                    valueFormatter={(value) => formatPercentage(value, 2)}
                    colorOf={errorRateBarColor}
                    subField="P95"
                  />
                )}
              </SectionCard>
            </Col>

            <Col xs={24} lg={8}>
              <SectionCard
                icon={<ThunderboltOutlined aria-hidden="true" className="text-[var(--theme-color-status-warning)]" />}
                title={t('apm.home.topP95Title', 'P95 响应时间 TOP5')}
                viewAllHref="/apm/services"
                failed={sectionFailed(dashboard?.top_p95)}
                onRetry={load}
              >
                {topP95Items.length === 0 ? (
                  <SectionEmpty>{t('apm.home.topP95Empty', '暂无 P95 数据')}</SectionEmpty>
                ) : (
                  <Top5BarChart
                    window={timeWindow}
                    rows={topP95Items.map((row) => ({
                      service_id: row.service_id,
                      name: row.service_name,
                      environment: row.environment,
                      value: row.value,
                      sub: formatTopP95SubValue(row.sub_value, t),
                    }))}
                    valueFormatter={(value) => formatLatency(value, false, t)}
                    colorOf={p95BarColor}
                    subField={t('apm.home.topP95Sub', '吞吐')}
                  />
                )}
              </SectionCard>
            </Col>

            <Col xs={24} lg={8}>
              <SectionCard
                icon={<TagsOutlined aria-hidden="true" className="text-[var(--color-primary)]" />}
                title={t('apm.home.releasesTitle', '版本发布变更')}
                subtitle={t('apm.home.releasesSubtitle', '近 7 天')}
                viewAllHref="/apm/services"
                failed={sectionFailed(dashboard?.releases)}
                onRetry={load}
              >
                <SectionEmpty>{t('apm.home.releasesEmpty', '近 7 天无发布')}</SectionEmpty>
              </SectionCard>
            </Col>
          </Row>
        </>
      )}
    </ApmRouteShell>
  );
}
