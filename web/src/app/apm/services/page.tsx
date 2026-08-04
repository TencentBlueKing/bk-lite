'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import {
  AppstoreOutlined,
  BarsOutlined,
  EditOutlined,
  EyeOutlined,
  InboxOutlined,
  SearchOutlined,
  UndoOutlined,
} from '@ant-design/icons';
import {
  Alert,
  Button,
  Card,
  Empty,
  Input,
  message,
  Popconfirm,
  Segmented,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  type TableColumnsType,
} from 'antd';
import dayjs from 'dayjs';
import useApmApi from '@/app/apm/api';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, {
  catalogErrorKind,
  type CatalogStateKind,
} from '@/app/apm/components/catalog-state';
import OrganizationAssignmentModal from '@/app/apm/components/organization-assignment-modal';
import ServiceIdentity from '@/app/apm/components/service-identity';
import ApmStatusTag from '@/app/apm/components/status-tag';
import type { ApmEnvironmentView, ApmService, ApmServiceRed, CatalogStatus } from '@/app/apm/types';
import Permission from '@/components/permission';
import { useUserInfoContext } from '@/context/userInfo';

interface ServiceEnvironmentRow extends ApmEnvironmentView {
  key: string;
  serviceId: string;
  namespace: string;
  serviceName: string;
  serviceOrganizationIds: number[];
  serviceArchivedAt: string | null;
}

type PageState = CatalogStateKind | 'ready';
type ServicePerspective = 'application' | 'service';
type TimeWindow = '15m' | '1h' | '4h' | '1d' | '7d';

interface ApplicationSummary {
  key: string;
  label: string;
  status: CatalogStatus;
  services: string[];
  environmentCount: number;
  requestRate: number | null;
  errorRate: number | null;
  lastSeenAt: string;
}

const timeWindowUnits: Record<TimeWindow, [number, dayjs.ManipulateType]> = {
  '15m': [15, 'minute'],
  '1h': [1, 'hour'],
  '4h': [4, 'hour'],
  '1d': [1, 'day'],
  '7d': [7, 'day'],
};

const metricKey = (serviceId: string, environment: string) => `${serviceId}:${environment}`;

const formatRate = (value: number | null) => {
  if (value === null) return '暂无数据';
  return value >= 1000 ? `${(value / 1000).toFixed(1)}k/s` : `${value.toFixed(value >= 100 ? 0 : 1)}/s`;
};

export default function ApmServicesPage() {
  const {
    getHealth,
    getServiceRed,
    getServices,
    setServiceArchived,
    setServiceOrganizations,
    isLoading: authLoading,
  } = useApmApi();
  const { flatGroups } = useUserInfoContext();
  const [services, setServices] = useState<ApmService[]>([]);
  const [catalogDegraded, setCatalogDegraded] = useState(false);
  const [perspective, setPerspective] = useState<ServicePerspective>('application');
  const [keyword, setKeyword] = useState('');
  const [environment, setEnvironment] = useState<string>();
  const [namespace, setNamespace] = useState<string>();
  const [status, setStatus] = useState<CatalogStatus>();
  const [timeWindow, setTimeWindow] = useState<TimeWindow>('1h');
  const [redMetrics, setRedMetrics] = useState<Record<string, ApmServiceRed>>({});
  const [metricsLoading, setMetricsLoading] = useState(false);
  const [state, setState] = useState<PageState>('loading');
  const [refreshKey, setRefreshKey] = useState(0);
  const [organizationService, setOrganizationService] = useState<ApmService | null>(null);
  const [organizationSubmitting, setOrganizationSubmitting] = useState(false);

  const groupNames = useMemo(
    () => new Map(flatGroups.map((group) => [Number(group.id), group.name])),
    [flatGroups]
  );

  useEffect(() => {
    if (authLoading) return;
    let active = true;
    setState('loading');
    Promise.all([
      getServices({ include_archived: status === 'archived' }),
      getHealth().catch(() => ({ catalog_reconcile: { status: 'degraded' as const } })),
    ])
      .then(([items, health]) => {
        if (!active) return;
        setServices(items);
        setCatalogDegraded(health.catalog_reconcile.status === 'degraded');
        setState(items.length ? 'ready' : 'empty');
      })
      .catch((error) => {
        if (active) setState(catalogErrorKind(error));
      });
    return () => {
      active = false;
    };
  }, [authLoading, getHealth, getServices, refreshKey, status]);

  const submitOrganizations = async (organizationIds: number[]) => {
    if (!organizationService) return;
    setOrganizationSubmitting(true);
    try {
      await setServiceOrganizations(organizationService.id, organizationIds);
      message.success('服务组织已更新');
      setOrganizationService(null);
      setRefreshKey((value) => value + 1);
    } finally {
      setOrganizationSubmitting(false);
    }
  };

  const setArchived = async (serviceId: string, archived: boolean) => {
    await setServiceArchived(serviceId, archived);
    message.success(archived ? '服务已归档' : '服务已解档');
    setRefreshKey((value) => value + 1);
  };

  const rows = useMemo(
    () =>
      services.flatMap((service) => {
        const environmentViews = service.environment_views.length
          ? service.environment_views
          : [{ environment: '', last_seen_at: service.last_seen_at, status: service.status }];
        return environmentViews.map((environment) => ({
          ...environment,
          status: service.archived_at ? 'archived' as const : environment.status,
          key: `${service.id}:${environment.environment}`,
          serviceId: service.id,
          namespace: service.namespace,
          serviceName: service.name,
          serviceOrganizationIds: service.organization_ids,
          serviceArchivedAt: service.archived_at,
        }));
      }),
    [services]
  );

  useEffect(() => {
    if (state !== 'ready') {
      setRedMetrics({});
      return;
    }
    const targets = rows.filter((row) => row.environment && !row.serviceArchivedAt);
    if (!targets.length) {
      setRedMetrics({});
      return;
    }
    let active = true;
    const [amount, unit] = timeWindowUnits[timeWindow];
    const endedAt = dayjs();
    const startedAt = endedAt.subtract(amount, unit);
    setMetricsLoading(true);
    Promise.allSettled(targets.map(async (row) => ({
      key: metricKey(row.serviceId, row.environment),
      metric: await getServiceRed(row.serviceId, row.environment, startedAt.toISOString(), endedAt.toISOString()),
    })))
      .then((results) => {
        if (!active) return;
        setRedMetrics(Object.fromEntries(results.flatMap((result) => (
          result.status === 'fulfilled' ? [[result.value.key, result.value.metric]] : []
        ))));
      })
      .finally(() => {
        if (active) setMetricsLoading(false);
      });
    return () => {
      active = false;
    };
  }, [getServiceRed, rows, state, timeWindow]);

  const environmentOptions = useMemo(
    () => Array.from(new Set(rows.map((item) => item.environment)))
      .sort()
      .map((value) => ({ value, label: value || '未设置' })),
    [rows]
  );

  const namespaceOptions = useMemo(
    () => Array.from(new Set(rows.map((item) => item.namespace)))
      .sort()
      .map((value) => ({ value, label: value || '未归类应用' })),
    [rows]
  );

  const filteredRows = useMemo(() => {
    const normalizedKeyword = keyword.trim().toLowerCase();
    return rows.filter((item) => {
      const matchesKeyword = !normalizedKeyword
        || `${item.namespace} ${item.serviceName}`.toLowerCase().includes(normalizedKeyword);
      return matchesKeyword
        && (environment === undefined || item.environment === environment)
        && (namespace === undefined || item.namespace === namespace)
        && (status === undefined || item.status === status);
    });
  }, [environment, keyword, namespace, rows, status]);

  const filteredServiceCount = useMemo(
    () => new Set(filteredRows.map((item) => item.serviceId)).size,
    [filteredRows]
  );

  const applicationSummaries = useMemo<ApplicationSummary[]>(() => {
    const summaries = new Map<string, {
      serviceNames: Set<string>;
      environments: Set<string>;
      statuses: CatalogStatus[];
      metrics: ApmServiceRed[];
      lastSeenAt: string;
    }>();
    filteredRows.forEach((row) => {
      const current = summaries.get(row.namespace) ?? {
        serviceNames: new Set<string>(),
        environments: new Set<string>(),
        statuses: [],
        metrics: [],
        lastSeenAt: row.last_seen_at,
      };
      current.serviceNames.add(row.serviceName);
      current.environments.add(row.environment || '未设置');
      current.statuses.push(row.status);
      current.lastSeenAt = dayjs(row.last_seen_at).isAfter(current.lastSeenAt) ? row.last_seen_at : current.lastSeenAt;
      const metric = redMetrics[metricKey(row.serviceId, row.environment)];
      if (metric) current.metrics.push(metric);
      summaries.set(row.namespace, current);
    });

    return Array.from(summaries.entries()).map(([key, summary]) => {
      const metricsWithRate = summary.metrics.filter((metric) => metric.request_rate !== null);
      const requestRate = metricsWithRate.length
        ? metricsWithRate.reduce((total, metric) => total + (metric.request_rate ?? 0), 0)
        : null;
      const weightedErrors = metricsWithRate.filter((metric) => metric.error_rate !== null);
      const errorRate = requestRate && weightedErrors.length
        ? weightedErrors.reduce((total, metric) => total + (metric.request_rate ?? 0) * (metric.error_rate ?? 0), 0) / requestRate
        : null;
      const statusValue: CatalogStatus = summary.statuses.every((value) => value === 'archived')
        ? 'archived'
        : summary.statuses.some((value) => value === 'active') ? 'active' : 'silent';
      return {
        key,
        label: key || '未归类应用',
        status: statusValue,
        services: Array.from(summary.serviceNames).sort(),
        environmentCount: summary.environments.size,
        requestRate,
        errorRate,
        lastSeenAt: summary.lastSeenAt,
      };
    }).sort((left, right) => left.label.localeCompare(right.label));
  }, [filteredRows, redMetrics]);

  const columns: TableColumnsType<ServiceEnvironmentRow> = [
    {
      title: '服务',
      key: 'service',
      render: (_, item) => (
        <ServiceIdentity namespace={item.namespace} name={item.serviceName} />
      ),
    },
    {
      title: '环境',
      dataIndex: 'environment',
      width: 150,
      responsive: ['sm'],
      render: (value) => <Tag bordered={false}>{value || '未设置'}</Tag>,
    },
    {
      title: '最近发现',
      dataIndex: 'last_seen_at',
      width: 200,
      responsive: ['md'],
      render: (value) => (
        <Typography.Text className="tabular-nums text-sm">
          {dayjs(value).format('YYYY-MM-DD HH:mm:ss')}
        </Typography.Text>
      ),
    },
    { title: '状态', dataIndex: 'status', width: 110, render: (value) => <ApmStatusTag status={value} /> },
    {
      title: '组织',
      dataIndex: 'serviceOrganizationIds',
      width: 140,
      responsive: ['xl'],
      render: (value: number[]) => value.map((id) => (
        <Tag bordered={false} key={id}>{groupNames.get(id) ?? `#${id}`}</Tag>
      )),
    },
    {
      title: '操作',
      key: 'action',
      width: 300,
      align: 'right',
      render: (_, item) => (
        <Space size={0}>
          {item.environment ? (
            <Link href={`/apm/services/${item.serviceId}?environment=${encodeURIComponent(item.environment)}`}>
              <Button type="link" size="small" icon={<EyeOutlined aria-hidden="true" />}>
                查看 RED
              </Button>
            </Link>
          ) : (
            <Button type="link" size="small" disabled title="收到带环境与实例身份的 Span 后可查询 RED">
              待实例身份
            </Button>
          )}
          <Permission requiredPermissions={['Operate']} permissionPath="/apm/services">
            <Space size={0}>
              {!item.serviceArchivedAt ? (
                <Button
                  type="link"
                  size="small"
                  icon={<EditOutlined aria-hidden="true" />}
                  onClick={() => setOrganizationService(services.find((service) => service.id === item.serviceId) ?? null)}
                >
                  组织
                </Button>
              ) : null}
              <Popconfirm
                title={item.serviceArchivedAt ? '确认解档服务？' : '确认归档服务？'}
                description={item.serviceArchivedAt ? '解档后服务将重新出现在默认目录。' : '归档不会删除 Trace 或指标数据。'}
                okText={item.serviceArchivedAt ? '解档' : '归档'}
                cancelText="取消"
                onConfirm={() => setArchived(item.serviceId, !item.serviceArchivedAt)}
              >
                <Button
                  type="link"
                  size="small"
                  danger={!item.serviceArchivedAt}
                  icon={item.serviceArchivedAt ? <UndoOutlined aria-hidden="true" /> : <InboxOutlined aria-hidden="true" />}
                >
                  {item.serviceArchivedAt ? '解档' : '归档'}
                </Button>
              </Popconfirm>
            </Space>
          </Permission>
        </Space>
      ),
    },
  ];

  return (
    <ApmRouteShell
      title="服务目录"
      description="按 namespace 与 service.name 汇总逻辑服务，并按环境分别展示健康状态。"
      dependency="telemetry"
    >
      {catalogDegraded ? (
        <Alert
          className="mb-4"
          type="warning"
          showIcon
          message="目录对账暂时降级，当前列表可能不是最新状态。"
        />
      ) : null}
      <div className="flex flex-col gap-3">
        <ApmSurface padding="compact">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2 border-r border-[var(--color-border)] pr-3">
              <Typography.Text type="secondary" className="!text-xs">视角</Typography.Text>
              <Segmented<ServicePerspective>
                aria-label="服务目录视角"
                options={[
                  { value: 'application', label: <span><AppstoreOutlined aria-hidden="true" className="mr-1" />应用</span> },
                  { value: 'service', label: <span><BarsOutlined aria-hidden="true" className="mr-1" />服务</span> },
                ]}
                value={perspective}
                onChange={setPerspective}
              />
            </div>
            <Input
              allowClear
              aria-label="按应用或服务名称搜索"
              className="min-w-52 flex-1 md:max-w-xs"
              prefix={<SearchOutlined className="text-[var(--color-text-4)]" aria-hidden="true" />}
              placeholder="按应用或服务名称搜索"
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
            />
            <Select
              allowClear
              aria-label="按环境筛选"
              className="w-40"
              placeholder="全部环境"
              value={environment}
              options={environmentOptions}
              onChange={setEnvironment}
            />
            <Select
              allowClear
              aria-label="按应用筛选"
              className="w-40"
              placeholder="全部应用"
              value={namespace}
              options={namespaceOptions}
              onChange={setNamespace}
            />
            <Select<CatalogStatus>
              allowClear
              aria-label="按服务状态筛选"
              className="w-36"
              placeholder="全部健康度"
              value={status}
              options={[
                { value: 'active', label: '活跃' },
                { value: 'silent', label: '静默' },
                { value: 'archived', label: '已归档' },
              ]}
              onChange={setStatus}
            />
            <div className="ml-auto flex flex-wrap items-center gap-2">
              <Typography.Text type="secondary" className="!text-xs">时间窗</Typography.Text>
              <Segmented<TimeWindow>
                aria-label="服务指标时间窗口"
                options={['15m', '1h', '4h', '1d', '7d']}
                size="small"
                value={timeWindow}
                onChange={setTimeWindow}
              />
              <Button
                icon={<InboxOutlined aria-hidden="true" />}
                type={status === 'archived' ? 'primary' : 'default'}
                onClick={() => {
                  setStatus((value) => value === 'archived' ? undefined : 'archived');
                  setPerspective('service');
                }}
              >
                已归档
              </Button>
            </div>
          </div>
        </ApmSurface>
        {perspective === 'application' ? (
          state === 'ready' ? (
            applicationSummaries.length ? (
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
                {applicationSummaries.map((application) => (
                  <button
                    aria-label={`查看应用 ${application.label} 下的服务`}
                    className="group min-w-0 cursor-pointer rounded-lg text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"
                    key={application.key || 'uncategorized'}
                    type="button"
                    onClick={() => {
                      setNamespace(application.key);
                      setPerspective('service');
                    }}
                  >
                    <Card
                      className="h-full border-[var(--color-border)] transition-colors duration-200 group-hover:border-[var(--color-primary)]"
                      styles={{ body: { padding: 16, height: '100%' } }}
                    >
                      <div className="flex h-full flex-col gap-4">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <Typography.Text strong ellipsis={{ tooltip: application.label }} className="block !text-sm">
                              {application.label}
                            </Typography.Text>
                            <Typography.Text type="secondary" className="!text-xs tabular-nums">
                              {application.services.length} 个服务 · {application.environmentCount} 个环境
                            </Typography.Text>
                          </div>
                          <ApmStatusTag status={application.status} />
                        </div>
                        <div className="grid grid-cols-2 gap-3 rounded-md bg-[var(--color-fill-1)] p-3">
                          <div>
                            <Typography.Text type="secondary" className="block !text-xs">吞吐量</Typography.Text>
                            <Typography.Text strong className="tabular-nums">{formatRate(application.requestRate)}</Typography.Text>
                          </div>
                          <div>
                            <Typography.Text type="secondary" className="block !text-xs">错误率</Typography.Text>
                            <Typography.Text strong className="tabular-nums">
                              {application.errorRate === null ? '暂无数据' : `${(application.errorRate * 100).toFixed(2)}%`}
                            </Typography.Text>
                          </div>
                        </div>
                        <div className="flex min-h-6 flex-wrap gap-1.5">
                          {application.services.slice(0, 3).map((serviceName) => (
                            <Tag bordered={false} key={serviceName}>{serviceName}</Tag>
                          ))}
                          {application.services.length > 3 ? <Tag bordered={false}>+{application.services.length - 3}</Tag> : null}
                        </div>
                        <Typography.Text type="secondary" className="mt-auto !text-xs tabular-nums">
                          最近上报 {dayjs(application.lastSeenAt).format('YYYY-MM-DD HH:mm:ss')}
                        </Typography.Text>
                      </div>
                    </Card>
                  </button>
                ))}
              </div>
            ) : (
              <ApmSurface><Empty description="没有匹配的应用，请调整筛选条件。" /></ApmSurface>
            )
          ) : (
            <ApmSurface padding="none"><CatalogState kind={state} /></ApmSurface>
          )
        ) : (
          <ApmSurface padding="none" className="overflow-hidden">
            <div className="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-3">
              <div className="flex min-w-0 items-center gap-2">
                <Typography.Text strong>{namespace === undefined ? '全部服务' : namespace || '未归类应用'}</Typography.Text>
                {namespace !== undefined ? (
                  <Button size="small" type="link" onClick={() => setNamespace(undefined)}>清除应用筛选</Button>
                ) : null}
              </div>
              <Typography.Text type="secondary" className="!text-xs tabular-nums">
                {filteredRows.length} 个环境视图 · {filteredServiceCount} 个逻辑服务
              </Typography.Text>
            </div>
            {state === 'ready' ? (
              <Table
                columns={columns}
                dataSource={filteredRows}
                pagination={{
                  defaultPageSize: 20,
                  pageSizeOptions: [10, 20, 50, 100],
                  showSizeChanger: true,
                  showTotal: (total) => `共 ${total} 条`,
                }}
              />
            ) : (
              <CatalogState kind={state} />
            )}
          </ApmSurface>
        )}
        {metricsLoading && perspective === 'application' ? (
          <Typography.Text type="secondary" className="self-end !text-xs">正在更新 {timeWindow} RED 指标…</Typography.Text>
        ) : null}
      </div>
      <OrganizationAssignmentModal
        open={Boolean(organizationService)}
        title={`调整服务组织${organizationService ? `：${organizationService.namespace}/${organizationService.name}` : ''}`}
        organizationIds={organizationService?.organization_ids ?? []}
        submitting={organizationSubmitting}
        description="服务组织独立于接入源与实例，仅影响此逻辑服务的可见和可操作范围。"
        onCancel={() => setOrganizationService(null)}
        onSubmit={submitOrganizations}
      />
    </ApmRouteShell>
  );
}
