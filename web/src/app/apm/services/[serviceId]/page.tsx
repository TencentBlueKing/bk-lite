'use client';

import { useEffect, useMemo, useState } from 'react';
import { useParams, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import {
  ArrowLeftOutlined,
  InboxOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import {
  Button,
  Col,
  Empty,
  List,
  Modal,
  Progress,
  Row,
  Segmented,
  Select,
  Space,
  Tabs,
  Tag,
  Typography,
  message,
  theme,
  type TableColumnsType,
} from 'antd';
import MoreActionsDropdown from '@/components/more-actions-dropdown';
import type { MoreActionsDropdownItem } from '@/components/more-actions-dropdown';
import CompactEmptyState from '@/components/compact-empty-state';
import useApmApi from '@/app/apm/api';
import ApmDataTable, { APM_TABLE_COLUMN_WIDTHS } from '@/app/apm/components/apm-data-table';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, {
  catalogErrorKind,
  type CatalogStateKind,
} from '@/app/apm/components/catalog-state';
import { DEPLOYMENT_LOOKBACK_MS, DEPLOYMENT_STATUS_META } from '@/app/apm/components/deployment-status';
import HealthDot from '@/app/apm/components/health-dot';
import { StatusPill } from '@/app/apm/components/home/section-card';
import {
  deriveHealth,
  formatClockTime,
  formatDateTime,
  formatErrorRate,
  formatLatency,
  formatNumber,
  formatPercentage,
  formatRelativeTime,
  formatRequestRate,
  formatThroughput,
  isErrorRateDanger,
} from '@/app/apm/components/metric-format';
import type {
  ApmDeploymentEvent,
  ApmService,
  ApmServiceEndpointRed,
  ApmServiceRed,
  ApmSlo,
  ApmTopologyEdge,
  ApmTopologyNode,
  ApmTraceSummary,
} from '@/app/apm/types';
import { isInferredTopologyNode } from '@/app/apm/services/topology/topology-layout';
import SummaryMetricCard from '@/components/summary-metric-card';
import Permission from '@/components/permission';
import TimeSeriesComposedChart from '@/components/time-series-composed-chart';
import { useTranslation } from '@/utils/i18n';

type PageState = CatalogStateKind | 'ready';
type TimeRange = '15m' | '1h' | '4h' | '1d' | '7d';
type DetailTab = 'overview' | 'traces' | 'errors' | 'runtime' | 'deployments' | 'slo';
type RedChartPoint = Record<string, unknown> & {
  timestamp: string;
  request_rate: number | null;
  error_rate_percent: number | null;
  p95_ms: number | null;
  p99_ms: number | null;
};

const RANGE_MS: Record<TimeRange, number> = {
  '15m': 15 * 60 * 1000,
  '1h': 60 * 60 * 1000,
  '4h': 4 * 60 * 60 * 1000,
  '1d': 24 * 60 * 60 * 1000,
  '7d': 7 * 24 * 60 * 60 * 1000,
};

function ServiceMetricCard({
  label,
  value,
  suffix,
  danger,
}: {
  label: string;
  value: string;
  suffix?: string;
  danger?: boolean;
}) {
  return (
    <SummaryMetricCard
      className="rounded-lg px-4 py-3.5"
      label={label}
      labelClassName="!text-xs"
      layout="vertical"
      maxFontSize={16}
      minFontSize={16}
      unit={suffix}
      value={value}
      valueColor={danger ? 'var(--color-fail)' : undefined}
    />
  );
}

export default function ApmServiceDetailPage() {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const params = useParams<{ serviceId: string }>();
  const searchParams = useSearchParams();
  const {
    getService,
    getServiceRed,
    getTraces,
    getTopology,
    getSlos,
    getDeployments,
    setServiceArchived,
    isLoading: authLoading,
  } = useApmApi();
  const [service, setService] = useState<ApmService>();
  const [environment, setEnvironment] = useState<string | undefined>(
    searchParams.get('environment') ?? undefined
  );
  const [red, setRed] = useState<ApmServiceRed>();
  const [timeRange, setTimeRange] = useState<TimeRange>('1h');
  const [activeTab, setActiveTab] = useState<DetailTab>('overview');
  const [catalogState, setCatalogState] = useState<PageState>('loading');
  const [metricState, setMetricState] = useState<PageState>('loading');
  const [traces, setTraces] = useState<ApmTraceSummary[]>([]);
  const [tracesState, setTracesState] = useState<PageState>('loading');
  const [upstream, setUpstream] = useState<{ node: ApmTopologyNode; edge: ApmTopologyEdge }[]>([]);
  const [downstream, setDownstream] = useState<{ node: ApmTopologyNode; edge: ApmTopologyEdge }[]>([]);
  const [serviceSlos, setServiceSlos] = useState<ApmSlo[]>([]);
  const [deployments, setDeployments] = useState<ApmDeploymentEvent[]>([]);
  const [deploymentsState, setDeploymentsState] = useState<PageState>('loading');
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    if (authLoading || !params.serviceId) return;
    let active = true;
    setCatalogState('loading');
    getService(params.serviceId)
      .then((item) => {
        if (!active) return;
        setService(item);
        const available = item.environment_views.map((view) => view.environment);
        setEnvironment((current) =>
          current !== undefined && available.includes(current) ? current : available[0]
        );
        setCatalogState('ready');
      })
      .catch((error) => {
        if (active) setCatalogState(catalogErrorKind(error));
      });
    return () => {
      active = false;
    };
  }, [authLoading, getService, params.serviceId, refreshKey]);

  useEffect(() => {
    if (!service || environment === undefined) {
      setMetricState('empty');
      return;
    }
    let active = true;
    setMetricState('loading');
    const endedAt = new Date().toISOString();
    const startedAt = new Date(new Date(endedAt).getTime() - RANGE_MS[timeRange]).toISOString();
    getServiceRed(service.id, environment, startedAt, endedAt)
      .then((value) => {
        if (!active) return;
        setRed(value);
        setMetricState('ready');
      })
      .catch((error) => {
        if (active) setMetricState(catalogErrorKind(error));
      });
    return () => {
      active = false;
    };
  }, [environment, getServiceRed, refreshKey, service, timeRange]);

  useEffect(() => {
    if (!service || environment === undefined || authLoading) return;
    let active = true;
    setTracesState('loading');
    const endedAt = new Date().toISOString();
    const startedAt = new Date(new Date(endedAt).getTime() - RANGE_MS[timeRange]).toISOString();
    Promise.all([
      getTraces({
        service_namespace: service.namespace,
        service_name: service.name,
        environment,
        started_at: startedAt,
        ended_at: endedAt,
        limit: 20,
      }),
      getTopology({ started_at: startedAt, ended_at: endedAt, environment }).catch(() => null),
      getSlos().catch(() => [] as ApmSlo[]),
    ])
      .then(([page, topology, slos]) => {
        if (!active) return;
        setTraces(page.items);
        setTracesState(page.items.length ? 'ready' : 'empty');
        setServiceSlos(slos.filter((slo) => slo.service_id === service.id && slo.environment === environment));
        if (topology) {
          const self = topology.nodes.find(
            (node) => node.service_namespace === service.namespace && node.service_name === service.name
          );
          if (self) {
            const nodeMap = new Map<string, ApmTopologyNode>(topology.nodes.map((node) => [node.id, node]));
            setUpstream(
              topology.edges
                .filter((edge) => edge.target === self.id)
                .flatMap((edge) => {
                  const node = nodeMap.get(edge.source);
                  return node && !isInferredTopologyNode(node) ? [{ node, edge }] : [];
                })
            );
            setDownstream(
              topology.edges
                .filter((edge) => edge.source === self.id)
                .flatMap((edge) => {
                  const node = nodeMap.get(edge.target);
                  return node && !isInferredTopologyNode(node) ? [{ node, edge }] : [];
                })
            );
          } else {
            setUpstream([]);
            setDownstream([]);
          }
        }
      })
      .catch((error) => {
        if (active) setTracesState(catalogErrorKind(error));
      });
    return () => {
      active = false;
    };
  }, [authLoading, environment, getSlos, getTopology, getTraces, refreshKey, service, timeRange]);

  useEffect(() => {
    if (authLoading || !params.serviceId || activeTab !== 'deployments') return;
    let active = true;
    setDeploymentsState('loading');
    const endedAt = new Date();
    const startedAt = new Date(endedAt.getTime() - DEPLOYMENT_LOOKBACK_MS);
    getDeployments({
      service_id: params.serviceId,
      page: 1,
      page_size: 100,
      started_at: startedAt.toISOString(),
      ended_at: endedAt.toISOString(),
    })
      .then((result) => {
        if (!active) return;
        setDeployments(result.items);
        setDeploymentsState(result.items.length ? 'ready' : 'empty');
      })
      .catch((error) => {
        if (active) setDeploymentsState(catalogErrorKind(error));
      });
    return () => {
      active = false;
    };
  }, [activeTab, authLoading, getDeployments, params.serviceId, refreshKey]);

  const exploreHref = service && red
    ? `/apm/explore/traces?${new URLSearchParams({
      service_namespace: service.namespace,
      service_name: service.name,
      environment: red.environment,
      started_at: red.started_at,
      ended_at: red.ended_at,
    }).toString()}`
    : '/apm/explore/traces';

  const chartData = useMemo<RedChartPoint[]>(
    () => (red?.timeseries ?? []).map((point) => ({
      timestamp: point.timestamp,
      request_rate: point.request_rate,
      error_rate_percent: point.error_rate == null ? null : point.error_rate * 100,
      p95_ms: point.p95_ms,
      p99_ms: point.p99_ms,
    })),
    [red]
  );

  const topEndpoints = useMemo(() => {
    const items = [...(red?.top_endpoints ?? [])];
    const maxRate = Math.max(...items.map((item) => item.request_rate), 1);
    return items.map((item) => ({ ...item, ratio: Math.round((item.request_rate / maxRate) * 100) }));
  }, [red]);

  const errorTraces = useMemo(
    () => traces.filter((item) => item.status === 'error'),
    [traces]
  );

  const health = deriveHealth(service?.status ?? 'silent', red?.error_rate ?? null);

  const archiveService = () => {
    if (!service) return;
    Modal.confirm({
      title: service.archived_at
        ? t('apm.serviceDetail.unarchiveConfirm', '确认解档该服务？')
        : t('apm.serviceDetail.archiveConfirm', '确认归档该服务？'),
      content: service.archived_at
        ? t('apm.services.unarchiveHint', '解档后服务将重新出现在默认目录。')
        : t('apm.serviceDetail.archiveHint', '归档后告警自动暂停，数据保留期内可恢复。'),
      okText: service.archived_at ? t('apm.services.unarchive', '解档') : t('apm.services.archive', '归档'),
      okButtonProps: service.archived_at ? undefined : { danger: true },
      cancelText: t('common.cancel', '取消'),
      onOk: async () => {
        await setServiceArchived(service.id, !service.archived_at);
        message.success(service.archived_at ? t('apm.services.unarchived', '服务已解档') : t('apm.services.archived', '服务已归档'));
        const refreshed = await getService(service.id, true);
        setService(refreshed);
      },
    });
  };

  const moreMenuItems: MoreActionsDropdownItem[] = [
    {
      key: 'archive',
      icon: <InboxOutlined aria-hidden="true" />,
      danger: !service?.archived_at,
      label: service?.archived_at ? t('apm.services.unarchive', '解档') : t('apm.services.archive', '归档'),
      onClick: archiveService,
    },
  ];

  const traceColumns: TableColumnsType<ApmTraceSummary> = [
    {
      title: t('apm.explore.traceId', 'Trace ID'),
      dataIndex: 'trace_id',
      width: APM_TABLE_COLUMN_WIDTHS.traceId,
      render: (value: string) => (
        <Link
          href={`/apm/explore/traces/${value}`}
          className="block truncate font-mono text-xs text-[var(--color-text-3)] hover:text-[var(--color-primary)]"
        >
          {value}
        </Link>
      ),
    },
    {
      title: t('apm.explore.entryService', '入口服务'),
      key: 'service',
      width: APM_TABLE_COLUMN_WIDTHS.entryService,
      ellipsis: true,
      render: (_, item) => (
        <span className="flex min-w-0 items-center gap-1.5">
          <HealthDot level={item.status === 'error' ? 1 : 5} />
          <span className="truncate text-sm font-medium">{item.service_name}</span>
        </span>
      ),
    },
    {
      title: t('apm.explore.resource', '资源'),
      dataIndex: 'root_span_name',
      width: APM_TABLE_COLUMN_WIDTHS.resource,
      ellipsis: true,
      responsive: ['md'],
      render: (value) => <span className="truncate font-mono text-xs">{value}</span>,
    },
    {
      title: t('apm.explore.totalDuration', '总耗时'),
      dataIndex: 'duration_ms',
      width: APM_TABLE_COLUMN_WIDTHS.metric,
      align: 'right',
      className: 'tabular-nums',
      responsive: ['sm'],
      render: (value: number) => formatLatency(value, false, t),
    },
    {
      title: t('apm.explore.spanCount', '跨度数'),
      dataIndex: 'span_count',
      width: APM_TABLE_COLUMN_WIDTHS.status,
      align: 'right',
      className: 'tabular-nums',
      responsive: ['lg'],
    },
    {
      title: t('apm.common.status', '状态'),
      dataIndex: 'status',
      width: APM_TABLE_COLUMN_WIDTHS.status,
      align: 'center',
      render: (status: ApmTraceSummary['status']) => (
        status === 'error'
          ? <Tag bordered={false} color="error">{t('apm.severity.error', '错误')}</Tag>
          : <Tag bordered={false} color="success">{t('apm.status.ok', '正常')}</Tag>
      ),
    },
    {
      title: t('apm.common.time', '时间'),
      dataIndex: 'started_at',
      width: APM_TABLE_COLUMN_WIDTHS.relativeTime,
      responsive: ['xl'],
      render: (value: string) => (
        <span className="text-xs tabular-nums text-[var(--color-text-3)]" title={formatDateTime(value)}>
          {formatRelativeTime(value, t)}
        </span>
      ),
    },
  ];

  const deploymentColumns: TableColumnsType<ApmDeploymentEvent> = [
    {
      title: t('apm.deployments.version', '版本'),
      dataIndex: 'version',
      width: APM_TABLE_COLUMN_WIDTHS.metric,
      render: (value: string) => (
        <span className="rounded bg-[var(--color-bg)] px-1.5 py-px font-mono text-[11px] text-[var(--color-text-3)]">
          {value}
        </span>
      ),
    },
    {
      title: t('apm.common.environment', '环境'),
      dataIndex: 'environment',
      width: APM_TABLE_COLUMN_WIDTHS.metric,
      render: (value: string) => value || t('apm.common.unset', '未设置'),
    },
    {
      title: t('apm.deployments.deployedAt', '发布时间'),
      dataIndex: 'deployed_at',
      width: APM_TABLE_COLUMN_WIDTHS.relativeTime,
      render: (value: string) => (
        <span className="tabular-nums" title={formatDateTime(value)}>
          {formatRelativeTime(value, t)}
        </span>
      ),
    },
    {
      title: t('apm.common.status', '状态'),
      dataIndex: 'status',
      width: APM_TABLE_COLUMN_WIDTHS.status,
      render: (value: ApmDeploymentEvent['status']) => {
        const meta = DEPLOYMENT_STATUS_META[value] ?? DEPLOYMENT_STATUS_META.success;
        return <StatusPill label={t(meta.labelKey, meta.fallback)} tone={meta.tone} />;
      },
    },
    {
      title: t('apm.deployments.source', '来源'),
      dataIndex: 'source',
      width: APM_TABLE_COLUMN_WIDTHS.status,
      render: (value: ApmDeploymentEvent['source']) => (
        <Tag bordered={false}>
          {value === 'reported'
            ? t('apm.deployments.sourceReported', '上报')
            : t('apm.deployments.sourceInferred', '推断')}
        </Tag>
      ),
    },
  ];

  const dependencyTag = (item: { node: ApmTopologyNode; edge: ApmTopologyEdge }) => (
    <Tag bordered={false} key={item.node.id} className="!mb-1 !max-w-full !whitespace-normal">
      {item.node.service_name}
      {' · '}
      {t('apm.serviceDetail.dependencyMeta', '{calls}/窗 · Pavg {duration} · 错误 {errors}', {
        calls: formatNumber(item.edge.sampled_calls),
        duration: formatLatency(item.edge.average_duration_ms, false, t),
        errors: formatNumber(item.edge.error_calls),
      })}
    </Tag>
  );

  return (
    <ApmRouteShell
      title={t('apm.serviceDetail.title', '服务详情')}
      description={t('apm.serviceDetail.description', '查看单服务 RED 指标、调用链与错误样本，并可下钻到探索视图。')}
      dependency="telemetry"
    >
      {catalogState !== 'ready' ? (
        <ApmSurface padding="none">
          <CatalogState
            kind={catalogState}
            onRetry={catalogState === 'forbidden' ? undefined : () => setRefreshKey((value) => value + 1)}
          />
        </ApmSurface>
      ) : service ? (
        <div className="flex flex-col gap-4">
          <ApmSurface padding="compact">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex min-w-0 items-center gap-3">
                <Link href="/apm/services">
                  <Button aria-label={t('apm.serviceDetail.backAria', '返回服务目录')} icon={<ArrowLeftOutlined aria-hidden="true" />}>
                    {t('apm.serviceDetail.back', '返回服务')}
                  </Button>
                </Link>
                <div className="min-w-0">
                  <Space size={10} align="center" wrap>
                    <HealthDot level={health} showLabel={false} />
                    <Typography.Title level={2} className="!mb-0 !text-base !font-semibold">
                      {service.name}
                    </Typography.Title>
                    <Tag
                      bordered={false}
                      color={health <= 2 ? 'error' : health === 3 ? 'warning' : 'success'}
                    >
                      {health <= 2 ? t('apm.health.abnormal', '异常') : health === 3 ? t('apm.health.silent', '静默') : t('apm.health.healthy', '健康')}
                    </Tag>
                    <Tag bordered={false}>{environment || t('apm.common.unset', '未设置')}</Tag>
                  </Space>
                  <Typography.Text type="secondary" className="mt-1 block truncate text-xs">
                    {t('apm.serviceDetail.ownerApplication', '所属应用')}{' '}
                    <Link
                      href={`/apm/services?namespace=${encodeURIComponent(service.namespace)}`}
                      className="text-[var(--color-primary)]"
                    >
                      {service.application_name || service.namespace || t('apm.common.unsetNamespace', '未设置 namespace')}
                    </Link>
                  </Typography.Text>
                </div>
              </div>
              <Space wrap>
                <Select
                  aria-label={t('apm.serviceDetail.selectEnvironment', '选择环境')}
                  className="min-w-40"
                  value={environment}
                  onChange={setEnvironment}
                  options={service.environment_views.map((item) => ({
                    value: item.environment,
                    label: item.environment || t('apm.common.unset', '未设置'),
                  }))}
                />
                <Segmented<TimeRange>
                  aria-label={t('apm.serviceDetail.selectWindow', '选择时间窗')}
                  value={timeRange}
                  onChange={setTimeRange}
                  options={(Object.keys(RANGE_MS) as TimeRange[]).map((value) => ({ value, label: value }))}
                />
                <Link href={exploreHref}>
                  <Button icon={<SearchOutlined aria-hidden="true" />}>{t('apm.explore.openInExplore', '在探索中打开')}</Button>
                </Link>
                <Permission requiredPermissions={['Operate']} permissionPath="/apm/services">
                  <MoreActionsDropdown
                    items={moreMenuItems}
                    ariaLabel={t('apm.serviceDetail.moreActions', '更多操作')}
                    buttonType="default"
                    buttonSize="middle"
                  />
                </Permission>
              </Space>
            </div>
          </ApmSurface>

          {metricState === 'ready' && red ? (
            <Row gutter={[12, 12]}>
              <Col xs={12} lg={6}>
                <ServiceMetricCard
                  label={t('apm.explore.throughputShort', '吞吐')}
                  value={formatThroughput(red.request_rate, false, t)}
                  suffix={red.request_rate === null ? undefined : t('apm.common.requestsPerSecondUnit', 'req/s')}
                />
              </Col>
              <Col xs={12} lg={6}>
                <ServiceMetricCard
                  label={t('apm.common.errorRate', '错误率')}
                  value={formatErrorRate(red.error_rate, false, t)}
                  danger={isErrorRateDanger(red.error_rate)}
                />
              </Col>
              <Col xs={12} lg={6}>
                <ServiceMetricCard
                  label={t('apm.common.p99', 'P99')}
                  value={formatLatency(red.p99_ms, false, t)}
                  danger={red.p99_ms !== null && red.p99_ms >= 500}
                />
              </Col>
              <Col xs={12} lg={6}>
                <ServiceMetricCard label={t('apm.common.p95', 'P95')} value={formatLatency(red.p95_ms, false, t)} />
              </Col>
            </Row>
          ) : null}

          <Tabs
            activeKey={activeTab}
            onChange={(key) => setActiveTab(key as DetailTab)}
            items={[
              {
                key: 'overview',
                label: t('apm.serviceDetail.overview', '概览'),
                children: metricState === 'ready' && red ? (
                  <div className="flex flex-col gap-4">
                    <Row gutter={[16, 16]}>
                      <Col xs={24} xl={8}>
                        <ApmSurface className="h-[340px]">
                          <Typography.Text strong className="mb-3 block">{t('apm.common.throughput', '吞吐量')}</Typography.Text>
                          <div className="h-[280px]">
                            <TimeSeriesComposedChart<RedChartPoint>
                              data={chartData}
                              xDataKey="timestamp"
                              getXLabel={(item) => formatClockTime(item.timestamp, false)}
                              xAxisBoundaryGap={false}
                              yAxes={[{ formatter: (value) => formatRequestRate(value, false, t) }]}
                              series={[
                                { name: t('apm.serviceDetail.requestRate', '请求速率 req/s'), type: 'line', dataKey: 'request_rate', color: token.colorPrimary, showArea: true },
                              ]}
                              surfaceProps={{ emptyStateProps: { description: t('apm.serviceDetail.noRedTrend', '当前时间窗暂无 RED 趋势点') } }}
                            />
                          </div>
                        </ApmSurface>
                      </Col>
                      <Col xs={24} xl={8}>
                        <ApmSurface className="h-[340px]">
                          <Typography.Text strong className="mb-3 block">{t('apm.common.errorRate', '错误率')}</Typography.Text>
                          <div className="h-[280px]">
                            <TimeSeriesComposedChart<RedChartPoint>
                              data={chartData}
                              xDataKey="timestamp"
                              getXLabel={(item) => formatClockTime(item.timestamp, false)}
                              xAxisBoundaryGap={false}
                              yAxes={[{ formatter: (value) => formatPercentage(value, 1) }]}
                              series={[{ name: t('apm.common.errorRatePercent', '错误率 %'), type: 'line', dataKey: 'error_rate_percent', color: token.colorError, showArea: true, showSymbol: true }]}
                              surfaceProps={{ emptyStateProps: { description: t('apm.serviceDetail.noRedTrend', '当前时间窗暂无 RED 趋势点') } }}
                            />
                          </div>
                        </ApmSurface>
                      </Col>
                      <Col xs={24} xl={8}>
                        <ApmSurface className="h-[340px]">
                          <Typography.Text strong className="mb-3 block">{t('apm.serviceDetail.latencyTrend', '延迟趋势')}</Typography.Text>
                          <div className="h-[280px]">
                            <TimeSeriesComposedChart<RedChartPoint>
                              data={chartData}
                              xDataKey="timestamp"
                              getXLabel={(item) => formatClockTime(item.timestamp, false)}
                              xAxisBoundaryGap={false}
                              yAxes={[{ formatter: (value) => formatLatency(value, false, t) }]}
                              series={[
                                { name: t('apm.common.p95', 'P95'), type: 'line', dataKey: 'p95_ms', color: token.colorPrimary, showArea: true },
                                { name: t('apm.common.p99', 'P99'), type: 'line', dataKey: 'p99_ms', color: token.colorWarning, lineType: 'dotted', showSymbol: true },
                              ]}
                              surfaceProps={{ emptyStateProps: { description: t('apm.serviceDetail.noLatencyTrend', '当前时间窗暂无延迟趋势点') } }}
                            />
                          </div>
                        </ApmSurface>
                      </Col>
                    </Row>
                    <Row gutter={[12, 12]}>
                      <Col xs={24} lg={12}>
                        <ApmSurface>
                          <Typography.Text strong>{t('apm.serviceDetail.topEndpoints', 'Top 端点')}</Typography.Text>
                          <List
                            className="mt-2"
                            size="small"
                            dataSource={topEndpoints}
                            locale={{ emptyText: t('apm.serviceDetail.noEndpoints', '当前时间窗暂无端点指标') }}
                            renderItem={(item: ApmServiceEndpointRed & { ratio: number }) => (
                              <List.Item className="!px-0">
                                <div className="w-full">
                                  <div className="mb-1.5 flex items-start justify-between gap-3">
                                    <Link
                                      href={`/apm/explore/endpoints?service=${encodeURIComponent(service.name)}&environment=${encodeURIComponent(environment ?? '')}&endpoint=${encodeURIComponent(item.endpoint)}`}
                                      className="min-w-0 break-all text-sm text-[var(--color-text-1)] hover:text-[var(--color-primary)]"
                                    >
                                      {item.endpoint}
                                    </Link>
                                    <span className="shrink-0 text-xs tabular-nums text-[var(--color-text-3)]">
                                      {t('apm.serviceDetail.endpointMeta', '{throughput} · P99 {latency}', {
                                        throughput: formatRequestRate(item.request_rate, false, t),
                                        latency: formatLatency(item.p99_ms, false, t),
                                      })}
                                    </span>
                                  </div>
                                  <Progress
                                    percent={item.ratio}
                                    showInfo={false}
                                    size="small"
                                    strokeColor="var(--color-primary)"
                                    trailColor="var(--color-border)"
                                  />
                                </div>
                              </List.Item>
                            )}
                          />
                        </ApmSurface>
                      </Col>
                      <Col xs={24} lg={12}>
                        <ApmSurface>
                          <Typography.Text strong>{t('apm.serviceDetail.dependencies', '依赖关系')}</Typography.Text>
                          <Row gutter={[12, 12]} className="mt-2">
                            <Col span={12}>
                              <Typography.Text type="secondary" className="!text-xs">
                                {t('apm.serviceDetail.upstreamCallers', '上游 · 调用方 {count}', { count: upstream.length })}
                              </Typography.Text>
                              <div className="mt-1.5">
                                {upstream.length
                                  ? upstream.map(dependencyTag)
                                  : <Typography.Text type="secondary" className="!text-xs">{t('apm.serviceDetail.noUpstream', '近窗内无上游调用')}</Typography.Text>}
                              </div>
                            </Col>
                            <Col span={12}>
                              <Typography.Text type="secondary" className="!text-xs">
                                {t('apm.serviceDetail.downstreamCallees', '下游 · 被调方 {count}', { count: downstream.length })}
                              </Typography.Text>
                              <div className="mt-1.5">
                                {downstream.length
                                  ? downstream.map(dependencyTag)
                                  : <Typography.Text type="secondary" className="!text-xs">{t('apm.serviceDetail.noDownstream', '近窗内无向下调用')}</Typography.Text>}
                              </div>
                            </Col>
                          </Row>
                        </ApmSurface>
                      </Col>
                    </Row>
                  </div>
                ) : (
                  <ApmSurface padding="none">
                    <CatalogState
                      kind={metricState === 'ready' ? 'error' : metricState}
                      description={metricState === 'empty' ? t('apm.serviceDetail.noEnvironments', '当前服务尚无可查询的环境视图。') : undefined}
                      onRetry={metricState === 'forbidden' || metricState === 'empty' ? undefined : () => setRefreshKey((value) => value + 1)}
                    />
                  </ApmSurface>
                ),
              },
              {
                key: 'traces',
                label: t('apm.serviceDetail.traces', '调用链'),
                children: (
                  <ApmSurface>
                    <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
                      <Typography.Text strong>{t('apm.serviceDetail.recentTraces', '近窗调用链样本')}</Typography.Text>
                      <Link href={exploreHref}>
                        <Button type="link" size="small">{t('apm.explore.openInExplore', '在探索中打开')}</Button>
                      </Link>
                    </div>
                    {tracesState === 'ready' ? (
                      <ApmDataTable
                        rowKey="trace_id"
                        columns={traceColumns}
                        dataSource={traces}
                        pagination={false}
                      />
                    ) : (
                      <CatalogState
                        kind={tracesState}
                        description={tracesState === 'empty' ? t('apm.serviceDetail.noTraces', '当前时间窗暂无调用链样本。') : undefined}
                        onRetry={tracesState === 'forbidden' || tracesState === 'empty' ? undefined : () => setRefreshKey((value) => value + 1)}
                      />
                    )}
                  </ApmSurface>
                ),
              },
              {
                key: 'errors',
                label: errorTraces.length
                  ? t('apm.serviceDetail.errorsWithCount', '错误 ({count})', { count: errorTraces.length })
                  : t('apm.serviceDetail.errors', '错误'),
                children: errorTraces.length ? (
                  <div className="flex flex-col gap-3">
                    {errorTraces.map((item) => (
                      <ApmSurface key={item.trace_id} padding="compact">
                        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                          <div className="min-w-0">
                            <Space size={8} wrap>
                              <Typography.Text strong className="!text-sm">{item.root_span_name}</Typography.Text>
                              <Tag bordered={false} color="error">{t('apm.severity.error', '错误')}</Tag>
                              <Typography.Text type="secondary" className="!text-xs">
                                {item.service_name} · {item.environment || t('apm.common.unset', '未设置')}
                              </Typography.Text>
                            </Space>
                            <div className="mt-2">
                              <Link
                                href={`/apm/explore/traces/${item.trace_id}`}
                                className="text-xs text-[var(--color-primary)]"
                              >
                                {t('apm.explore.viewSampleTrace', '查看样本 Trace →')}
                              </Link>
                            </div>
                          </div>
                          <Space size={24}>
                            <div className="text-center">
                              <Typography.Text type="secondary" className="!text-xs">{t('apm.explore.spanCount', '跨度数')}</Typography.Text>
                              <div className="text-sm font-semibold tabular-nums text-[var(--color-fail)]">{item.span_count}</div>
                            </div>
                            <div className="text-center">
                              <Typography.Text type="secondary" className="!text-xs">{t('apm.common.latency', '耗时')}</Typography.Text>
                              <div className="text-sm font-semibold tabular-nums">{formatLatency(item.duration_ms, false, t)}</div>
                            </div>
                            <div className="text-center">
                              <Typography.Text type="secondary" className="!text-xs">{t('apm.explore.lastSeen', '最近出现')}</Typography.Text>
                              <div className="text-sm tabular-nums">{formatRelativeTime(item.started_at, t)}</div>
                            </div>
                          </Space>
                        </div>
                      </ApmSurface>
                    ))}
                  </div>
                ) : (
                  <ApmSurface className="py-16 text-center">
                    <CompactEmptyState description={t('apm.serviceDetail.noErrorTraces', '当前时间窗暂无错误 Trace')} />
                  </ApmSurface>
                ),
              },
              {
                key: 'runtime',
                label: t('apm.serviceDetail.runtime', '运行时'),
                children: (
                  <ApmSurface className="py-16 text-center">
                    <Typography.Text type="secondary">
                      {t('apm.serviceDetail.runtimeEmpty', '该服务尚未接入运行时指标采集（JVM / Go Runtime 等）')}
                    </Typography.Text>
                  </ApmSurface>
                ),
              },
              {
                key: 'deployments',
                label: t('apm.serviceDetail.deploy', '部署'),
                children: (
                  <ApmSurface>
                    <Typography.Text type="secondary" className="mb-3 block">
                      {t('apm.serviceDetail.deployHint', '由遥测推断的发布记录')}
                    </Typography.Text>
                    {deploymentsState === 'ready' ? (
                      <ApmDataTable
                        columns={deploymentColumns}
                        dataSource={deployments}
                        pagination={false}
                        rowKey="id"
                      />
                    ) : deploymentsState === 'empty' ? (
                      <CompactEmptyState description={t('apm.serviceDetail.deployEmpty', '近 90 天未观测到版本变化')} />
                    ) : (
                      <CatalogState
                        compact
                        kind={deploymentsState}
                        onRetry={deploymentsState === 'forbidden' ? undefined : () => setRefreshKey((value) => value + 1)}
                      />
                    )}
                  </ApmSurface>
                ),
              },
              {
                key: 'slo',
                label: t('apm.slo.title', 'SLO'),
                children: serviceSlos.length ? (
                  <ApmSurface>
                    <ApmDataTable
                      rowKey="id"
                      pagination={false}
                      dataSource={serviceSlos}
                      columns={[
                        { title: t('apm.slo.name', '名称'), dataIndex: 'name' },
                        {
                          title: t('apm.serviceDetail.target', '目标'),
                          dataIndex: 'objective',
                          width: APM_TABLE_COLUMN_WIDTHS.metric,
                          align: 'right',
                          responsive: ['sm'],
                          render: (value) => <span className="tabular-nums">{formatPercentage(value)}</span>,
                        },
                        {
                          title: t('apm.serviceDetail.current', '当前'),
                          dataIndex: 'current_rate',
                          width: APM_TABLE_COLUMN_WIDTHS.metric,
                          align: 'right',
                          responsive: ['md'],
                          render: (value) => value == null
                            ? '—'
                            : <span className="tabular-nums">{formatPercentage(value)}</span>,
                        },
                        {
                          title: t('apm.serviceDetail.errorBudget', '错误预算'),
                          dataIndex: 'budget_remaining',
                          width: APM_TABLE_COLUMN_WIDTHS.progress,
                          responsive: ['lg'],
                          render: (value) => value == null
                            ? '—'
                            : <Progress percent={Math.max(0, Math.min(100, Number(value)))} size="small" />,
                        },
                        {
                          title: t('apm.common.operation', '操作'),
                          width: APM_TABLE_COLUMN_WIDTHS.status,
                          align: 'right',
                          fixed: 'right',
                          render: () => <Link href="/apm/services/slo"><Button className="!px-0" type="link" size="small">{t('apm.serviceDetail.manage', '管理')}</Button></Link>,
                        },
                      ]}
                      headerAlignment="column"
                    />
                  </ApmSurface>
                ) : (
                  <ApmSurface className="py-16 text-center">
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description={t('apm.serviceDetail.noSlo', '该服务尚未配置 SLO')}
                    >
                      <Link href="/apm/services/slo"><Button type="primary">{t('apm.serviceDetail.configureSlo', '去配置 SLO')}</Button></Link>
                    </Empty>
                  </ApmSurface>
                ),
              },
            ]}
          />
        </div>
      ) : null}
    </ApmRouteShell>
  );
}
