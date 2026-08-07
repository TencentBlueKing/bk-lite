'use client';

import { useEffect, useMemo, useState } from 'react';
import { useParams, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import {
  ArrowLeftOutlined,
  EllipsisOutlined,
  InboxOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import {
  Button,
  Col,
  Dropdown,
  Empty,
  List,
  Modal,
  Progress,
  Row,
  Segmented,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
  type MenuProps,
  type TableColumnsType,
} from 'antd';
import dayjs from 'dayjs';
import useApmApi from '@/app/apm/api';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, {
  catalogErrorKind,
  type CatalogStateKind,
} from '@/app/apm/components/catalog-state';
import HealthDot from '@/app/apm/components/health-dot';
import {
  deriveHealth,
  formatErrorRate,
  formatLatency,
  formatRelativeTime,
  formatThroughput,
  isErrorRateDanger,
} from '@/app/apm/components/metric-format';
import type {
  ApmService,
  ApmServiceEndpointRed,
  ApmServiceRed,
  ApmSlo,
  ApmTopologyEdge,
  ApmTopologyNode,
  ApmTraceSummary,
} from '@/app/apm/types';
import Permission from '@/components/permission';
import TimeSeriesComposedChart from '@/components/time-series-composed-chart';

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

function KpiCard({
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
    <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-3.5">
      <Typography.Text type="secondary" className="!text-xs">{label}</Typography.Text>
      <div className="mt-1">
        <span
          className={`text-2xl font-bold tabular-nums leading-none ${
            danger ? 'text-[var(--color-fail)]' : 'text-[var(--color-text-1)]'
          }`}
        >
          {value}
        </span>
        {suffix ? <span className="ml-0.5 text-[13px] text-[var(--color-text-3)]">{suffix}</span> : null}
      </div>
    </div>
  );
}

export default function ApmServiceDetailPage() {
  const params = useParams<{ serviceId: string }>();
  const searchParams = useSearchParams();
  const {
    getService,
    getServiceRed,
    getTraces,
    getTopology,
    getSlos,
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

  useEffect(() => {
    if (authLoading || !params.serviceId) return;
    let active = true;
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
  }, [authLoading, getService, params.serviceId]);

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
  }, [environment, getServiceRed, service, timeRange]);

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
            const nodeMap = new Map(topology.nodes.map((node) => [node.id, node]));
            setUpstream(
              topology.edges
                .filter((edge) => edge.target === self.id)
                .flatMap((edge) => {
                  const node = nodeMap.get(edge.source);
                  return node ? [{ node, edge }] : [];
                })
            );
            setDownstream(
              topology.edges
                .filter((edge) => edge.source === self.id)
                .flatMap((edge) => {
                  const node = nodeMap.get(edge.target);
                  return node ? [{ node, edge }] : [];
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
  }, [authLoading, environment, getSlos, getTopology, getTraces, service, timeRange]);

  const exploreHref = service && red
    ? `/apm/traces?${new URLSearchParams({
      service_namespace: service.namespace,
      service_name: service.name,
      environment: red.environment,
      started_at: red.started_at,
      ended_at: red.ended_at,
    }).toString()}`
    : '/apm/traces';

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
      title: service.archived_at ? '确认解档该服务？' : '确认归档该服务？',
      content: service.archived_at
        ? '解档后服务将重新出现在默认目录。'
        : '归档后告警自动暂停，数据保留期内可恢复。',
      okText: service.archived_at ? '解档' : '归档',
      okButtonProps: service.archived_at ? undefined : { danger: true },
      cancelText: '取消',
      onOk: async () => {
        await setServiceArchived(service.id, !service.archived_at);
        message.success(service.archived_at ? '服务已解档' : '服务已归档');
        const refreshed = await getService(service.id, true);
        setService(refreshed);
      },
    });
  };

  const moreMenu: MenuProps = {
    items: [
      {
        key: 'archive',
        icon: <InboxOutlined aria-hidden="true" />,
        danger: !service?.archived_at,
        label: service?.archived_at ? '解档' : '归档',
        onClick: archiveService,
      },
    ],
  };

  const traceColumns: TableColumnsType<ApmTraceSummary> = [
    {
      title: '入口服务 / Trace ID',
      key: 'identity',
      render: (_, item) => (
        <Space direction="vertical" size={2}>
          <Space size={6}>
            <HealthDot level={item.status === 'error' ? 1 : 5} />
            <span className="text-[13px] font-medium">{item.service_name}</span>
          </Space>
          <Link
            href={`/apm/traces/${item.trace_id}`}
            className="font-mono text-[11px] text-[var(--color-text-3)] hover:text-[var(--color-primary)]"
          >
            {item.trace_id}
          </Link>
        </Space>
      ),
    },
    {
      title: '资源',
      dataIndex: 'root_span_name',
      render: (value) => <span className="font-mono text-xs">{value}</span>,
    },
    {
      title: '总耗时',
      dataIndex: 'duration_ms',
      width: 100,
      className: 'tabular-nums',
      render: (value: number) => formatLatency(value),
    },
    {
      title: '跨度数',
      dataIndex: 'span_count',
      width: 90,
      align: 'right',
      className: 'tabular-nums',
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (status: ApmTraceSummary['status']) => (
        status === 'error'
          ? <Tag bordered={false} color="error">错误</Tag>
          : <Tag bordered={false} color="success">正常</Tag>
      ),
    },
    {
      title: '时间',
      dataIndex: 'started_at',
      width: 100,
      render: (value: string) => (
        <span className="text-xs tabular-nums text-[var(--color-text-3)]">{formatRelativeTime(value)}</span>
      ),
    },
  ];

  const dependencyTag = (item: { node: ApmTopologyNode; edge: ApmTopologyEdge }) => (
    <Tag bordered={false} key={item.node.id} className="!mb-1 !max-w-full !whitespace-normal">
      {item.node.service_name}
      {' · '}
      {item.edge.sampled_calls}/窗
      {' · '}
                      Pavg {Math.round(item.edge.average_duration_ms)}ms
      {' · '}
      错误 {item.edge.error_calls}
    </Tag>
  );

  return (
    <ApmRouteShell
      title="服务详情"
      description="查看单服务 RED 指标、调用链与错误样本，并可下钻到探索视图。"
      dependency="telemetry"
    >
      {catalogState !== 'ready' ? (
        <ApmSurface padding="none"><CatalogState kind={catalogState} /></ApmSurface>
      ) : service ? (
        <div className="flex flex-col gap-4">
          <ApmSurface padding="compact">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex min-w-0 items-center gap-3">
                <Link href="/apm/services">
                  <Button aria-label="返回服务目录" icon={<ArrowLeftOutlined aria-hidden="true" />}>
                    返回服务
                  </Button>
                </Link>
                <div className="min-w-0">
                  <Space size={10} align="center" wrap>
                    <HealthDot level={health} />
                    <Typography.Title level={2} className="!mb-0 !text-lg !font-semibold">
                      {service.name}
                    </Typography.Title>
                    <Tag
                      bordered={false}
                      color={health <= 2 ? 'error' : health === 3 ? 'warning' : 'success'}
                    >
                      {health <= 2 ? '异常' : health === 3 ? '静默' : '健康'}
                    </Tag>
                    <Tag bordered={false}>{environment || '未设置'}</Tag>
                  </Space>
                  <Typography.Text type="secondary" className="mt-1 block truncate text-xs">
                    所属应用{' '}
                    <Link
                      href={`/apm/services?namespace=${encodeURIComponent(service.namespace)}`}
                      className="text-[var(--color-primary)]"
                    >
                      {service.application_name || service.namespace || '未归类应用'}
                    </Link>
                  </Typography.Text>
                </div>
              </div>
              <Space wrap>
                <Select
                  aria-label="选择环境"
                  className="min-w-40"
                  value={environment}
                  onChange={setEnvironment}
                  options={service.environment_views.map((item) => ({
                    value: item.environment,
                    label: item.environment || '未设置',
                  }))}
                />
                <Segmented<TimeRange>
                  aria-label="选择时间窗"
                  value={timeRange}
                  onChange={setTimeRange}
                  options={(Object.keys(RANGE_MS) as TimeRange[]).map((value) => ({ value, label: value }))}
                />
                <Link href={exploreHref}>
                  <Button icon={<SearchOutlined aria-hidden="true" />}>在探索中打开</Button>
                </Link>
                <Permission requiredPermissions={['Operate']} permissionPath="/apm/services">
                  <Dropdown menu={moreMenu} placement="bottomRight">
                    <Button icon={<EllipsisOutlined aria-hidden="true" />} aria-label="更多操作" />
                  </Dropdown>
                </Permission>
              </Space>
            </div>
          </ApmSurface>

          {metricState === 'ready' && red ? (
            <Row gutter={[12, 12]}>
              <Col xs={12} lg={6}>
                <KpiCard
                  label="吞吐"
                  value={formatThroughput(red.request_rate)}
                  suffix={red.request_rate === null ? undefined : '/s'}
                />
              </Col>
              <Col xs={12} lg={6}>
                <KpiCard
                  label="错误率"
                  value={formatErrorRate(red.error_rate)}
                  danger={isErrorRateDanger(red.error_rate)}
                />
              </Col>
              <Col xs={12} lg={6}>
                <KpiCard
                  label="P99"
                  value={formatLatency(red.p99_ms)}
                  danger={red.p99_ms !== null && red.p99_ms >= 500}
                />
              </Col>
              <Col xs={12} lg={6}>
                <KpiCard label="P95" value={formatLatency(red.p95_ms)} />
              </Col>
            </Row>
          ) : null}

          <Tabs
            activeKey={activeTab}
            onChange={(key) => setActiveTab(key as DetailTab)}
            items={[
              {
                key: 'overview',
                label: '概览',
                children: metricState === 'ready' && red ? (
                  <div className="flex flex-col gap-4">
                    <Row gutter={[16, 16]}>
                      <Col xs={24} xl={12}>
                        <ApmSurface className="h-[340px]">
                          <Typography.Text strong className="mb-3 block">吞吐与错误率</Typography.Text>
                          <div className="h-[280px]">
                            <TimeSeriesComposedChart<RedChartPoint>
                              data={chartData}
                              xDataKey="timestamp"
                              getXLabel={(item) => dayjs(item.timestamp).format('HH:mm')}
                              xAxisBoundaryGap={false}
                              yAxes={[
                                { formatter: (value) => `${value.toFixed(value >= 10 ? 0 : 1)}` },
                                { formatter: (value) => `${value.toFixed(1)}%`, splitLine: false },
                              ]}
                              series={[
                                { name: '请求速率 req/s', type: 'line', dataKey: 'request_rate', color: 'var(--color-primary)', showArea: true },
                                { name: '错误率 %', type: 'line', dataKey: 'error_rate_percent', color: 'var(--color-fail)', yAxisIndex: 1 },
                              ]}
                              surfaceProps={{ emptyStateProps: { description: '当前时间窗暂无 RED 趋势点' } }}
                            />
                          </div>
                        </ApmSurface>
                      </Col>
                      <Col xs={24} xl={12}>
                        <ApmSurface className="h-[340px]">
                          <Typography.Text strong className="mb-3 block">延迟趋势</Typography.Text>
                          <div className="h-[280px]">
                            <TimeSeriesComposedChart<RedChartPoint>
                              data={chartData}
                              xDataKey="timestamp"
                              getXLabel={(item) => dayjs(item.timestamp).format('HH:mm')}
                              xAxisBoundaryGap={false}
                              yAxes={[{ formatter: (value) => `${value.toFixed(0)} ms` }]}
                              series={[
                                { name: 'P95', type: 'line', dataKey: 'p95_ms', color: '#722ed1', showArea: true },
                                { name: 'P99', type: 'line', dataKey: 'p99_ms', color: '#fa8c16' },
                              ]}
                              surfaceProps={{ emptyStateProps: { description: '当前时间窗暂无延迟趋势点' } }}
                            />
                          </div>
                        </ApmSurface>
                      </Col>
                    </Row>
                    <Row gutter={[12, 12]}>
                      <Col xs={24} lg={12}>
                        <ApmSurface>
                          <Typography.Text strong>Top 端点</Typography.Text>
                          <List
                            className="mt-2"
                            size="small"
                            dataSource={topEndpoints}
                            locale={{ emptyText: '当前时间窗暂无端点指标' }}
                            renderItem={(item: ApmServiceEndpointRed & { ratio: number }) => (
                              <List.Item className="!px-0">
                                <div className="w-full">
                                  <div className="mb-1.5 flex items-start justify-between gap-3">
                                    <Link
                                      href={`/apm/endpoints?service=${encodeURIComponent(service.name)}&environment=${encodeURIComponent(environment ?? '')}&endpoint=${encodeURIComponent(item.endpoint)}`}
                                      className="min-w-0 break-all text-[13px] text-[var(--color-text-1)] hover:text-[var(--color-primary)]"
                                    >
                                      {item.endpoint}
                                    </Link>
                                    <span className="shrink-0 text-xs tabular-nums text-[var(--color-text-3)]">
                                      {formatThroughput(item.request_rate)}/s · P99 {formatLatency(item.p99_ms)}
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
                          <Typography.Text strong>依赖关系</Typography.Text>
                          <Row gutter={[12, 12]} className="mt-2">
                            <Col span={12}>
                              <Typography.Text type="secondary" className="!text-xs">
                                上游 · 调用方 {upstream.length}
                              </Typography.Text>
                              <div className="mt-1.5">
                                {upstream.length
                                  ? upstream.map(dependencyTag)
                                  : <Typography.Text type="secondary" className="!text-xs">近窗内无上游调用</Typography.Text>}
                              </div>
                            </Col>
                            <Col span={12}>
                              <Typography.Text type="secondary" className="!text-xs">
                                下游 · 被调方 {downstream.length}
                              </Typography.Text>
                              <div className="mt-1.5">
                                {downstream.length
                                  ? downstream.map(dependencyTag)
                                  : <Typography.Text type="secondary" className="!text-xs">近窗内无向下调用</Typography.Text>}
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
                      description={metricState === 'empty' ? '当前服务尚无可查询的环境视图。' : undefined}
                    />
                  </ApmSurface>
                ),
              },
              {
                key: 'traces',
                label: '调用链',
                children: (
                  <ApmSurface padding="none" className="overflow-hidden">
                    <div className="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-3">
                      <Typography.Text strong>近窗调用链样本</Typography.Text>
                      <Link href={exploreHref}>
                        <Button type="link" size="small">在探索中打开</Button>
                      </Link>
                    </div>
                    {tracesState === 'ready' ? (
                      <Table
                        size="middle"
                        rowKey="trace_id"
                        columns={traceColumns}
                        dataSource={traces}
                        pagination={false}
                      />
                    ) : (
                      <CatalogState
                        kind={tracesState}
                        description={tracesState === 'empty' ? '当前时间窗暂无调用链样本。' : undefined}
                      />
                    )}
                  </ApmSurface>
                ),
              },
              {
                key: 'errors',
                label: `错误${errorTraces.length ? ` (${errorTraces.length})` : ''}`,
                children: errorTraces.length ? (
                  <div className="flex flex-col gap-3">
                    {errorTraces.map((item) => (
                      <ApmSurface key={item.trace_id} padding="compact">
                        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                          <div className="min-w-0">
                            <Space size={8} wrap>
                              <Typography.Text strong className="!text-sm">{item.root_span_name}</Typography.Text>
                              <Tag bordered={false} color="error">错误</Tag>
                              <Typography.Text type="secondary" className="!text-xs">
                                {item.service_name} · {item.environment || '未设置'}
                              </Typography.Text>
                            </Space>
                            <div className="mt-2">
                              <Link
                                href={`/apm/traces/${item.trace_id}`}
                                className="text-xs text-[var(--color-primary)]"
                              >
                                查看样本 Trace →
                              </Link>
                            </div>
                          </div>
                          <Space size={24}>
                            <div className="text-center">
                              <Typography.Text type="secondary" className="!text-[11px]">跨度数</Typography.Text>
                              <div className="text-lg font-semibold tabular-nums text-[var(--color-fail)]">{item.span_count}</div>
                            </div>
                            <div className="text-center">
                              <Typography.Text type="secondary" className="!text-[11px]">耗时</Typography.Text>
                              <div className="text-lg font-semibold tabular-nums">{formatLatency(item.duration_ms)}</div>
                            </div>
                            <div className="text-center">
                              <Typography.Text type="secondary" className="!text-[11px]">最近出现</Typography.Text>
                              <div className="text-[13px] tabular-nums">{formatRelativeTime(item.started_at)}</div>
                            </div>
                          </Space>
                        </div>
                      </ApmSurface>
                    ))}
                  </div>
                ) : (
                  <ApmSurface className="py-16 text-center">
                    <Empty description="当前时间窗暂无错误 Trace" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                  </ApmSurface>
                ),
              },
              {
                key: 'runtime',
                label: '运行时',
                children: (
                  <ApmSurface className="py-16 text-center">
                    <Typography.Text type="secondary">
                      该服务尚未接入运行时指标采集（JVM / Go Runtime 等）
                    </Typography.Text>
                  </ApmSurface>
                ),
              },
              {
                key: 'deployments',
                label: '部署',
                children: (
                  <ApmSurface className="py-16 text-center">
                    <Typography.Text type="secondary">
                      部署事件将在发布埋点接入后展示；当前可先通过版本与 Trace 属性排查变更。
                    </Typography.Text>
                  </ApmSurface>
                ),
              },
              {
                key: 'slo',
                label: 'SLO',
                children: serviceSlos.length ? (
                  <ApmSurface padding="none" className="overflow-hidden">
                    <Table
                      size="middle"
                      rowKey="id"
                      pagination={false}
                      dataSource={serviceSlos}
                      columns={[
                        { title: '名称', dataIndex: 'name' },
                        {
                          title: '目标',
                          dataIndex: 'objective',
                          width: 100,
                          render: (value) => <span className="tabular-nums">{(Number(value) * 100).toFixed(2)}%</span>,
                        },
                        {
                          title: '当前',
                          dataIndex: 'current_rate',
                          width: 100,
                          render: (value) => value == null
                            ? '—'
                            : <span className="tabular-nums">{(Number(value) * 100).toFixed(2)}%</span>,
                        },
                        {
                          title: '错误预算',
                          dataIndex: 'budget_remaining',
                          width: 140,
                          render: (value) => value == null
                            ? '—'
                            : <Progress percent={Math.max(0, Math.min(100, Number(value) * 100))} size="small" />,
                        },
                        {
                          title: '操作',
                          width: 100,
                          render: () => <Link href="/apm/slo"><Button type="link" size="small">管理</Button></Link>,
                        },
                      ]}
                    />
                  </ApmSurface>
                ) : (
                  <ApmSurface className="py-16 text-center">
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description="该服务尚未配置 SLO"
                    >
                      <Link href="/apm/slo"><Button type="primary">去配置 SLO</Button></Link>
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
