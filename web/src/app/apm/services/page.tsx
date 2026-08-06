'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import {
  AppstoreOutlined,
  BarsOutlined,
  BellOutlined,
  EditOutlined,
  EllipsisOutlined,
  InboxOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import {
  Alert,
  Button,
  Drawer,
  Dropdown,
  Empty,
  Input,
  List,
  Modal,
  message,
  Segmented,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
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
import MetricValue from '@/app/apm/components/metric-value';
import MiniTrend from '@/app/apm/components/mini-trend';
import OrganizationAssignmentModal from '@/app/apm/components/organization-assignment-modal';
import type {
  ApmApplication,
  ApmEnvironmentView,
  ApmEvent,
  ApmService,
  ApmServiceRed,
  ApmSlo,
  CatalogStatus,
} from '@/app/apm/types';
import Permission from '@/components/permission';
import { useUserInfoContext } from '@/context/userInfo';

interface ServiceEnvironmentRow extends ApmEnvironmentView {
  key: string;
  serviceId: string;
  applicationName: string;
  namespace: string;
  serviceName: string;
  serviceOrganizationIds: number[];
  serviceArchivedAt: string | null;
  archiveReason: string;
}

type PageState = CatalogStateKind | 'ready';
type ServicePerspective = 'application' | 'service';
type TimeWindow = '15m' | '1h' | '4h' | '1d' | '7d';
type HealthFilter = CatalogStatus | 'critical' | 'warning';

interface ApplicationSummary {
  key: string;
  label: string;
  isBuiltin: boolean;
  status: CatalogStatus;
  services: { name: string; silent: boolean }[];
  environmentCount: number;
  requestRate: number | null;
  errorRate: number | null;
  metricUnavailable: boolean;
  alertCount: number;
  lastSeenAt: string | null;
}

const timeWindowUnits: Record<TimeWindow, [number, dayjs.ManipulateType]> = {
  '15m': [15, 'minute'],
  '1h': [1, 'hour'],
  '4h': [4, 'hour'],
  '1d': [1, 'day'],
  '7d': [7, 'day'],
};

const metricKey = (serviceId: string, environment: string) => `${serviceId}:${environment}`;
const alertKey = (serviceName: string, environment: string) => `${serviceName}::${environment}`;
const TIME_WINDOWS: TimeWindow[] = ['15m', '1h', '4h', '1d', '7d'];
const isTimeWindow = (value: string | null): value is TimeWindow => (
  value !== null && (TIME_WINDOWS as string[]).includes(value)
);
const isHealthFilter = (value: string | null): value is HealthFilter => (
  value === 'critical' || value === 'warning' || value === 'active' || value === 'silent'
);

const severityRank: Record<string, number> = {
  critical: 1,
  error: 2,
  warning: 3,
  info: 4,
};

export default function ApmServicesPage() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const {
    getApplications,
    getEvents,
    getHealth,
    getServiceRed,
    getServices,
    getSlos,
    setServiceArchived,
    setServiceOrganizations,
    isLoading: authLoading,
  } = useApmApi();
  const { flatGroups } = useUserInfoContext();
  const [services, setServices] = useState<ApmService[]>([]);
  const [applications, setApplications] = useState<ApmApplication[]>([]);
  const [slos, setSlos] = useState<ApmSlo[]>([]);
  const [firingEvents, setFiringEvents] = useState<ApmEvent[]>([]);
  const [catalogDegraded, setCatalogDegraded] = useState(false);
  const [perspective, setPerspective] = useState<ServicePerspective>(() => {
    const fromQuery = searchParams.get('perspective');
    if (fromQuery === 'service' || fromQuery === 'application') return fromQuery;
    return searchParams.get('namespace') !== null ? 'service' : 'application';
  });
  const [keyword, setKeyword] = useState(searchParams.get('q') ?? '');
  const [environment, setEnvironment] = useState<string | undefined>(
    searchParams.get('environment') ?? undefined
  );
  const [namespace, setNamespace] = useState<string | undefined>(
    searchParams.get('namespace') ?? undefined
  );
  const [healthFilter, setHealthFilter] = useState<HealthFilter | undefined>(() => {
    const value = searchParams.get('health');
    return isHealthFilter(value) ? value : undefined;
  });
  const [timeWindow, setTimeWindow] = useState<TimeWindow>(() => {
    const value = searchParams.get('window');
    return isTimeWindow(value) ? value : '1h';
  });
  const [redMetrics, setRedMetrics] = useState<Record<string, ApmServiceRed>>({});
  const [metricFailureKeys, setMetricFailureKeys] = useState<string[]>([]);
  const [metricsLoading, setMetricsLoading] = useState(false);
  const [metricRefreshKey, setMetricRefreshKey] = useState(0);
  const [state, setState] = useState<PageState>('loading');
  const [refreshKey, setRefreshKey] = useState(0);
  const [organizationService, setOrganizationService] = useState<ApmService | null>(null);
  const [organizationSubmitting, setOrganizationSubmitting] = useState(false);
  const [archivedOpen, setArchivedOpen] = useState(false);
  const [archivedServices, setArchivedServices] = useState<ApmService[]>([]);
  const [archivedKeyword, setArchivedKeyword] = useState('');

  const groupNames = useMemo(
    () => new Map(flatGroups.map((group) => [Number(group.id), group.name])),
    [flatGroups]
  );

  const retryMetrics = () => setMetricRefreshKey((value) => value + 1);

  useEffect(() => {
    const params = new URLSearchParams();
    if (perspective !== 'application') params.set('perspective', perspective);
    if (namespace !== undefined) params.set('namespace', namespace);
    if (environment) params.set('environment', environment);
    if (healthFilter) params.set('health', healthFilter);
    if (timeWindow !== '1h') params.set('window', timeWindow);
    const trimmed = keyword.trim();
    if (trimmed) params.set('q', trimmed);
    const next = params.toString();
    const current = searchParams.toString();
    if (next === current) return;
    router.replace(next ? `${pathname}?${next}` : pathname, { scroll: false });
  }, [
    environment,
    healthFilter,
    keyword,
    namespace,
    pathname,
    perspective,
    router,
    searchParams,
    timeWindow,
  ]);

  useEffect(() => {
    if (authLoading) return;
    let active = true;
    setState('loading');
    Promise.all([
      getApplications(),
      getServices({ include_archived: true }),
      getHealth().catch(() => ({ catalog_reconcile: { status: 'degraded' as const } })),
      getSlos().catch(() => [] as ApmSlo[]),
      getEvents({ limit: 100 }).catch(() => [] as ApmEvent[]),
    ])
      .then(([applicationItems, items, health, sloItems, events]) => {
        if (!active) return;
        const activeServices = items.filter((service) => !service.archived_at);
        setApplications(applicationItems);
        setServices(activeServices);
        setArchivedServices(items.filter((service) => Boolean(service.archived_at)));
        setSlos(sloItems);
        setFiringEvents(events.filter((event) => event.status === 'firing'));
        setCatalogDegraded(health.catalog_reconcile.status === 'degraded');
        setState(applicationItems.length || activeServices.length ? 'ready' : 'empty');
      })
      .catch((error) => {
        if (active) setState(catalogErrorKind(error));
      });
    return () => {
      active = false;
    };
  }, [authLoading, getApplications, getEvents, getHealth, getServices, getSlos, refreshKey]);

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

  const confirmArchive = (serviceId: string, archived: boolean) => {
    Modal.confirm({
      title: archived ? '确认归档服务？' : '确认解档服务？',
      content: archived
        ? '归档不会删除 Trace 或指标数据。'
        : '解档后服务将重新出现在默认目录。',
      okText: archived ? '归档' : '解档',
      okButtonProps: archived ? { danger: true } : undefined,
      cancelText: '取消',
      onOk: () => setArchived(serviceId, archived),
    });
  };

  const rows = useMemo(
    () =>
      services.flatMap((service) => {
        const environmentViews = service.environment_views.length
          ? service.environment_views
          : [{ environment: '', last_seen_at: service.last_seen_at, status: service.status }];
        return environmentViews.map((environmentView) => ({
          ...environmentView,
          status: service.archived_at ? 'archived' as const : environmentView.status,
          key: `${service.id}:${environmentView.environment}`,
          serviceId: service.id,
          applicationName: service.application_name,
          namespace: service.namespace,
          serviceName: service.name,
          serviceOrganizationIds: service.organization_ids,
          serviceArchivedAt: service.archived_at,
          archiveReason: service.archive_reason,
        }));
      }),
    [services]
  );

  useEffect(() => {
    if (state !== 'ready') {
      setRedMetrics({});
      setMetricFailureKeys([]);
      return;
    }
    const targets = rows.filter((row) => row.environment && !row.serviceArchivedAt);
    if (!targets.length) {
      setRedMetrics({});
      setMetricFailureKeys([]);
      return;
    }
    let active = true;
    const [amount, unit] = timeWindowUnits[timeWindow];
    const endedAt = dayjs();
    const startedAt = endedAt.subtract(amount, unit);
    setMetricsLoading(true);
    setMetricFailureKeys([]);
    Promise.allSettled(targets.map(async (row) => ({
      key: metricKey(row.serviceId, row.environment),
      metric: await getServiceRed(row.serviceId, row.environment, startedAt.toISOString(), endedAt.toISOString()),
    })))
      .then((results) => {
        if (!active) return;
        setRedMetrics(Object.fromEntries(results.flatMap((result) => (
          result.status === 'fulfilled' ? [[result.value.key, result.value.metric]] : []
        ))));
        setMetricFailureKeys(results.flatMap((result, index) => (
          result.status === 'rejected'
            ? [metricKey(targets[index].serviceId, targets[index].environment)]
            : []
        )));
      })
      .finally(() => {
        if (active) setMetricsLoading(false);
      });
    return () => {
      active = false;
    };
  }, [getServiceRed, metricRefreshKey, rows, state, timeWindow]);

  const alertCounts = useMemo(() => {
    const counts = new Map<string, { count: number; level: number }>();
    firingEvents.forEach((event) => {
      const key = alertKey(event.service, event.environment || '');
      const current = counts.get(key) ?? { count: 0, level: 5 };
      const level = severityRank[event.severity] ?? 4;
      counts.set(key, {
        count: current.count + 1,
        level: Math.min(current.level, level),
      });
    });
    return counts;
  }, [firingEvents]);

  const sloByServiceEnv = useMemo(() => {
    const map = new Map<string, ApmSlo>();
    slos.forEach((slo) => {
      if (!slo.is_enabled) return;
      const key = metricKey(slo.service_id, slo.environment);
      const existing = map.get(key);
      if (!existing || (slo.budget_remaining ?? 1) < (existing.budget_remaining ?? 1)) {
        map.set(key, slo);
      }
    });
    return map;
  }, [slos]);

  const environmentOptions = useMemo(
    () => Array.from(new Set(rows.map((item) => item.environment)))
      .sort()
      .map((value) => ({ value, label: value || '未设置' })),
    [rows]
  );

  const namespaceOptions = useMemo(
    () => [...applications]
      .sort((left, right) => Number(left.is_builtin) - Number(right.is_builtin) || left.name.localeCompare(right.name))
      .map((application) => ({ value: application.application_id, label: application.name })),
    [applications]
  );

  const filteredRows = useMemo(() => {
    const normalizedKeyword = keyword.trim().toLowerCase();
    return rows.filter((item) => {
      const metric = redMetrics[metricKey(item.serviceId, item.environment)];
      const errorRate = metric?.error_rate ?? null;
      const health = deriveHealth(item.status, errorRate);
      const matchesKeyword = !normalizedKeyword
        || `${item.namespace} ${item.serviceName} ${item.applicationName}`.toLowerCase().includes(normalizedKeyword);
      const matchesHealth = healthFilter === undefined
        || (healthFilter === 'critical' && health === 1)
        || (healthFilter === 'warning' && health === 2)
        || (healthFilter === 'active' && item.status === 'active')
        || (healthFilter === 'silent' && item.status === 'silent')
        || (healthFilter === 'archived' && item.status === 'archived');
      return matchesKeyword
        && (environment === undefined || item.environment === environment)
        && (namespace === undefined || item.namespace === namespace)
        && matchesHealth;
    });
  }, [environment, healthFilter, keyword, namespace, redMetrics, rows]);

  const filteredServiceCount = useMemo(
    () => new Set(filteredRows.map((item) => item.serviceId)).size,
    [filteredRows]
  );

  const applicationSummaries = useMemo<ApplicationSummary[]>(() => {
    const summaries = new Map<string, {
      serviceNames: Map<string, boolean>;
      environments: Set<string>;
      statuses: CatalogStatus[];
      metrics: ApmServiceRed[];
      metricUnavailable: boolean;
      alertCount: number;
      lastSeenAt: string | null;
    }>();
    const normalizedKeyword = keyword.trim().toLowerCase();
    const canShowWithoutServices = environment === undefined && healthFilter === undefined;
    const canShowSilentWithoutServices = environment === undefined && healthFilter === 'silent';
    applications.forEach((application) => {
      const matchesApplication = !normalizedKeyword
        || `${application.application_id} ${application.name}`.toLowerCase().includes(normalizedKeyword);
      const matchesNamespace = namespace === undefined || namespace === application.application_id;
      const visibleWithoutServices = canShowWithoutServices
        || (canShowSilentWithoutServices && application.service_count === 0);
      if (!matchesApplication || !matchesNamespace || !visibleWithoutServices) return;
      summaries.set(application.application_id, {
        serviceNames: new Map(),
        environments: new Set(),
        statuses: [],
        metrics: [],
        metricUnavailable: false,
        alertCount: 0,
        lastSeenAt: null,
      });
    });
    filteredRows.forEach((row) => {
      const current = summaries.get(row.namespace) ?? {
        serviceNames: new Map<string, boolean>(),
        environments: new Set<string>(),
        statuses: [],
        metrics: [],
        metricUnavailable: false,
        alertCount: 0,
        lastSeenAt: null,
      };
      current.serviceNames.set(row.serviceName, row.status === 'silent' || Boolean(current.serviceNames.get(row.serviceName)));
      current.environments.add(row.environment || '未设置');
      current.statuses.push(row.status);
      current.lastSeenAt = current.lastSeenAt && dayjs(current.lastSeenAt).isAfter(row.last_seen_at)
        ? current.lastSeenAt
        : row.last_seen_at;
      const metric = redMetrics[metricKey(row.serviceId, row.environment)];
      if (metric) current.metrics.push(metric);
      if (metricFailureKeys.includes(metricKey(row.serviceId, row.environment))) current.metricUnavailable = true;
      current.alertCount += alertCounts.get(alertKey(row.serviceName, row.environment))?.count ?? 0;
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
      const statusValue: CatalogStatus = summary.statuses.length === 0
        ? 'silent'
        : summary.statuses.every((value) => value === 'archived')
          ? 'archived'
          : summary.statuses.some((value) => value === 'active') ? 'active' : 'silent';
      const application = applications.find((item) => item.application_id === key);
      return {
        key,
        label: application?.name ?? (key || '未归类应用'),
        isBuiltin: application?.is_builtin ?? false,
        status: statusValue,
        services: Array.from(summary.serviceNames.entries())
          .map(([name, silent]) => ({ name, silent }))
          .sort((left, right) => left.name.localeCompare(right.name)),
        environmentCount: summary.environments.size,
        requestRate,
        errorRate,
        metricUnavailable: summary.metricUnavailable,
        alertCount: summary.alertCount,
        lastSeenAt: summary.lastSeenAt,
      };
    }).sort((left, right) => Number(left.isBuiltin) - Number(right.isBuiltin) || left.label.localeCompare(right.label));
  }, [alertCounts, applications, environment, filteredRows, healthFilter, keyword, metricFailureKeys, namespace, redMetrics]);

  const archivedRows = useMemo(() => {
    const normalized = archivedKeyword.trim().toLowerCase();
    return archivedServices.filter((service) => (
      !normalized
      || `${service.namespace} ${service.name} ${service.application_name}`.toLowerCase().includes(normalized)
    ));
  }, [archivedKeyword, archivedServices]);

  const selectedApplication = applications.find((item) => item.application_id === namespace);

  const actionMenu = (item: ServiceEnvironmentRow): MenuProps => ({
    items: [
      {
        key: 'org',
        icon: <EditOutlined aria-hidden="true" />,
        label: '调整组织',
        onClick: () => setOrganizationService(services.find((service) => service.id === item.serviceId) ?? null),
      },
      {
        key: 'archive',
        icon: <InboxOutlined aria-hidden="true" />,
        danger: true,
        label: '归档',
        onClick: () => confirmArchive(item.serviceId, true),
      },
    ],
  });

  const columns: TableColumnsType<ServiceEnvironmentRow> = [
    {
      title: (
        <Space size={6}>
          <span>服务</span>
          {selectedApplication ? (
            <Tag bordered={false} color="blue" className="!m-0 !text-[11px]">
              {selectedApplication.is_builtin ? '未归类应用' : selectedApplication.name}
            </Tag>
          ) : null}
        </Space>
      ),
      key: 'service',
      fixed: 'left',
      render: (_, item) => {
        const metric = redMetrics[metricKey(item.serviceId, item.environment)];
        const silent = item.status === 'silent';
        const href = item.environment
          ? `/apm/services/${item.serviceId}?environment=${encodeURIComponent(item.environment)}&window=${timeWindow}`
          : undefined;
        const health = deriveHealth(item.status, metric?.error_rate ?? null);
        return (
          <Space size={8} align="center" className={silent ? 'opacity-60' : undefined}>
            <HealthDot status={item.status} errorRate={metric?.error_rate ?? null} showLabel />
            {href ? (
              <Link
                href={href}
                className={`font-medium text-[var(--color-primary)] hover:underline ${
                  health <= 2 ? 'font-semibold' : ''
                }`}
              >
                {item.serviceName}
              </Link>
            ) : (
              <Typography.Text strong className="!text-sm">{item.serviceName}</Typography.Text>
            )}
            {silent ? <Tag bordered={false} className="!m-0 !text-[11px] text-[var(--color-text-3)]">静默</Tag> : null}
          </Space>
        );
      },
    },
    {
      title: '活跃告警',
      key: 'alerts',
      width: 100,
      render: (_, item) => {
        const alert = alertCounts.get(alertKey(item.serviceName, item.environment));
        const count = alert?.count ?? 0;
        const dangerous = count > 0 && (alert?.level ?? 5) <= 2;
        const eventsHref = `/apm/events?service=${encodeURIComponent(item.serviceName)}${
          item.environment ? `&environment=${encodeURIComponent(item.environment)}` : ''
        }`;
        return (
          <Link
            href={eventsHref}
            aria-label={`${item.serviceName} 有 ${count} 个活跃告警，查看告警`}
            className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] no-underline transition-colors duration-150 ${
              dangerous
                ? 'border-[var(--color-fail)] bg-[color-mix(in_srgb,var(--color-fail)_10%,var(--color-bg))] font-semibold text-[var(--color-fail)]'
                : 'border-[var(--color-border)] bg-[var(--color-fill-1)] text-[var(--color-text-3)] hover:border-[var(--color-primary)]'
            }`}
            onClick={(event) => event.stopPropagation()}
          >
            <BellOutlined className="text-[10px]" aria-hidden="true" />
            <span className="tabular-nums">{count}</span>
            <span className="sr-only">个活跃告警</span>
          </Link>
        );
      },
    },
    {
      title: '吞吐量(/s)',
      key: 'throughput',
      width: 120,
      align: 'right',
      className: 'tabular-nums',
      render: (_, item) => {
        const metric = redMetrics[metricKey(item.serviceId, item.environment)];
        const unavailable = metricFailureKeys.includes(metricKey(item.serviceId, item.environment));
        return (
          <MetricValue
            text={formatThroughput(metric?.request_rate ?? null, unavailable)}
            unavailable={unavailable}
            muted={item.status === 'silent'}
            onRetry={unavailable ? retryMetrics : undefined}
          />
        );
      },
    },
    {
      title: '错误率',
      key: 'errorRate',
      width: 110,
      align: 'right',
      className: 'tabular-nums',
      render: (_, item) => {
        const metric = redMetrics[metricKey(item.serviceId, item.environment)];
        const unavailable = metricFailureKeys.includes(metricKey(item.serviceId, item.environment));
        return (
          <MetricValue
            text={formatErrorRate(metric?.error_rate ?? null, unavailable)}
            unavailable={unavailable}
            danger={isErrorRateDanger(metric?.error_rate ?? null)}
            onRetry={unavailable ? retryMetrics : undefined}
          />
        );
      },
    },
    {
      title: 'P99',
      key: 'p99',
      width: 100,
      align: 'right',
      className: 'tabular-nums',
      responsive: ['md'],
      render: (_, item) => {
        const metric = redMetrics[metricKey(item.serviceId, item.environment)];
        const unavailable = metricFailureKeys.includes(metricKey(item.serviceId, item.environment));
        return (
          <MetricValue
            text={formatLatency(metric?.p99_ms ?? null, unavailable)}
            unavailable={unavailable}
            onRetry={unavailable ? retryMetrics : undefined}
          />
        );
      },
    },
    {
      title: '趋势',
      key: 'trend',
      width: 90,
      responsive: ['lg'],
      render: (_, item) => {
        const metric = redMetrics[metricKey(item.serviceId, item.environment)];
        return (
          <MiniTrend
            points={metric?.timeseries}
            status={item.status}
            errorRate={metric?.error_rate ?? null}
          />
        );
      },
    },
    {
      title: '环境',
      dataIndex: 'environment',
      width: 110,
      responsive: ['sm'],
      render: (value) => <Tag bordered={false}>{value || '未设置'}</Tag>,
    },
    {
      title: 'SLO',
      key: 'slo',
      width: 110,
      responsive: ['xl'],
      render: (_, item) => {
        const slo = sloByServiceEnv.get(metricKey(item.serviceId, item.environment));
        if (!slo) return <Typography.Text type="secondary">—</Typography.Text>;
        const met = slo.budget_remaining !== null && slo.budget_remaining > 0
          && slo.current_rate !== null
          && Number(slo.current_rate) >= Number(slo.objective);
        return (
          <Tag
            bordered={false}
            className={`!m-0 !text-[11px] ${
              met
                ? '!bg-[color-mix(in_srgb,var(--color-success)_12%,var(--color-bg))] !text-[var(--color-success)]'
                : '!bg-[color-mix(in_srgb,var(--color-fail)_12%,var(--color-bg))] !text-[var(--color-fail)]'
            }`}
          >
            {met ? '达标' : '未达标'}
            {slo.current_rate !== null ? ` ${(Number(slo.current_rate) * 100).toFixed(1)}%` : ''}
          </Tag>
        );
      },
    },
    {
      title: '最近活跃',
      dataIndex: 'last_seen_at',
      width: 110,
      responsive: ['md'],
      render: (value) => (
        <Tooltip title={dayjs(value).format('YYYY-MM-DD HH:mm:ss')}>
          <span className="text-xs text-[var(--color-text-3)]">{formatRelativeTime(value)}</span>
        </Tooltip>
      ),
    },
    {
      title: '组织',
      dataIndex: 'serviceOrganizationIds',
      width: 120,
      responsive: ['xl'],
      render: (value: number[]) => value.length
        ? value.map((id) => (
          <Tag bordered={false} key={id}>{groupNames.get(id) ?? `#${id}`}</Tag>
        ))
        : <Typography.Text type="secondary">—</Typography.Text>,
    },
    {
      title: '',
      key: 'action',
      width: 56,
      align: 'right',
      fixed: 'right',
      render: (_, item) => (
        <Permission requiredPermissions={['Operate']} permissionPath="/apm/services">
          <Dropdown menu={actionMenu(item)} trigger={['click']}>
            <Button type="text" size="small" icon={<EllipsisOutlined aria-hidden="true" />} aria-label="更多操作" />
          </Dropdown>
        </Permission>
      ),
    },
  ];

  return (
    <ApmRouteShell
      title="服务"
      description="按应用与服务浏览健康状态和 RED 指标，点击服务进入详情。"
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
      {metricFailureKeys.length ? (
        <Alert
          action={(
            <Button
              icon={<ReloadOutlined aria-hidden="true" />}
              loading={metricsLoading}
              size="small"
              onClick={() => retryMetrics()}
            >
              重试 RED 指标
            </Button>
          )}
          className="mb-4"
          description="服务目录元数据仍然可用；失败项显示为「查询失败」，不会再伪装成无遥测数据。"
          message={metricFailureKeys.length === rows.filter((row) => row.environment && !row.serviceArchivedAt).length
            ? 'RED 指标查询失败'
            : `部分 RED 指标查询失败（${metricFailureKeys.length} 项）`}
          showIcon
          role="alert"
          type="warning"
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
              className="w-36"
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
            <Select<HealthFilter>
              allowClear
              aria-label="按健康度筛选"
              className="w-36"
              placeholder="全部健康度"
              value={healthFilter}
              options={[
                { value: 'critical', label: '严重' },
                { value: 'warning', label: '警告' },
                { value: 'active', label: '活跃' },
                { value: 'silent', label: '静默' },
              ]}
              onChange={setHealthFilter}
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
                onClick={() => setArchivedOpen(true)}
              >
                已归档
                {archivedServices.length ? (
                  <span className="ml-1 tabular-nums text-[var(--color-text-3)]">{archivedServices.length}</span>
                ) : null}
              </Button>
            </div>
          </div>
        </ApmSurface>
        {perspective === 'application' ? (
          state === 'ready' ? (
            applicationSummaries.length ? (
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
                {applicationSummaries.map((application) => {
                  const health = deriveHealth(application.status, application.errorRate);
                  const errDanger = isErrorRateDanger(application.errorRate);
                  const alertServiceHint = application.services[0]?.name;
                  const eventsHref = alertServiceHint
                    ? `/apm/events?service=${encodeURIComponent(alertServiceHint)}`
                    : '/apm/events';
                  return (
                    <button
                      aria-label={`查看应用 ${application.label} 下的服务`}
                      className="group min-w-0 cursor-pointer rounded-md text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"
                      key={application.key || 'uncategorized'}
                      type="button"
                      onClick={() => {
                        setNamespace(application.key);
                        setPerspective('service');
                      }}
                    >
                      <div
                        className={`flex h-full flex-col border border-[var(--color-border)] bg-[var(--color-bg)] p-4 transition-colors duration-150 group-hover:border-[var(--color-primary)] ${
                          application.isBuiltin ? 'border-t-[3px] border-t-dashed border-t-[var(--theme-color-status-warning)]' : ''
                        }`}
                      >
                        <div className="mb-3.5 flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <HealthDot level={health} showLabel />
                              <Typography.Text strong ellipsis={{ tooltip: application.label }} className="!text-[15px]">
                                {application.label}
                              </Typography.Text>
                              {application.isBuiltin ? (
                                <Tooltip title="这些服务未设置 service.namespace，平台归入内置未归类应用。">
                                  <Tag color="warning" className="!m-0 !text-[11px]">未归类</Tag>
                                </Tooltip>
                              ) : null}
                            </div>
                            <Typography.Text type="secondary" className="mt-1 ml-4 block !text-xs tabular-nums">
                              {application.services.length} 个服务
                            </Typography.Text>
                          </div>
                          <Link
                            href={eventsHref}
                            aria-label={`应用内 ${application.alertCount} 个活跃告警，查看告警`}
                            title={`应用内 ${application.alertCount} 个活跃告警`}
                            className={`inline-flex shrink-0 items-center gap-1 rounded px-2 py-0.5 text-xs no-underline transition-colors duration-150 ${
                              application.alertCount > 0
                                ? 'border border-[var(--color-fail)] bg-[color-mix(in_srgb,var(--color-fail)_8%,var(--color-bg))] font-semibold text-[var(--color-fail)]'
                                : 'border border-[var(--color-border)] bg-[var(--color-fill-1)] text-[var(--color-text-3)] hover:border-[var(--color-primary)]'
                            }`}
                            onClick={(event) => event.stopPropagation()}
                          >
                            <BellOutlined className="text-[11px]" aria-hidden="true" />
                            <span className="tabular-nums">{application.alertCount}</span>
                          </Link>
                        </div>
                        <div className="mb-3.5 grid grid-cols-2 gap-4">
                          <div>
                            <Typography.Text type="secondary" className="block !text-[11px]">吞吐量</Typography.Text>
                            <div className="mt-0.5 flex items-baseline gap-0.5">
                              <MetricValue
                                size="lg"
                                text={formatThroughput(application.requestRate, application.metricUnavailable)}
                                unavailable={application.metricUnavailable}
                                onRetry={application.metricUnavailable ? retryMetrics : undefined}
                              />
                              {application.requestRate !== null ? (
                                <span className="text-xs text-[var(--color-text-3)]">/s</span>
                              ) : null}
                            </div>
                          </div>
                          <div>
                            <Typography.Text type="secondary" className="block !text-[11px]">错误率</Typography.Text>
                            <div className="mt-0.5">
                              <MetricValue
                                size="lg"
                                text={formatErrorRate(application.errorRate, application.metricUnavailable)}
                                unavailable={application.metricUnavailable}
                                danger={errDanger}
                                onRetry={application.metricUnavailable ? retryMetrics : undefined}
                              />
                            </div>
                          </div>
                        </div>
                        <div className="mt-auto border-t border-dashed border-[var(--color-border)] pt-3">
                          <Tooltip
                            title={application.services.map((service) => (
                              service.silent ? `${service.name}(静默)` : service.name
                            )).join('、') || '尚无服务'}
                          >
                            <div className="flex flex-nowrap gap-1.5 overflow-hidden">
                              {application.services.slice(0, 4).map((service) => (
                                <span
                                  key={service.name}
                                  className={`inline-flex shrink-0 items-center rounded border px-2 py-0.5 text-xs whitespace-nowrap ${
                                    service.silent
                                      ? 'border-[var(--color-border)] bg-[var(--color-fill-1)] text-[var(--color-text-3)]'
                                      : 'border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text-1)]'
                                  }`}
                                >
                                  {service.name}
                                </span>
                              ))}
                              {application.services.length > 4 ? (
                                <span className="inline-flex shrink-0 items-center rounded bg-[var(--color-primary-bg-active)] px-2 py-0.5 text-xs font-medium text-[var(--color-primary)]">
                                  +{application.services.length - 4}
                                </span>
                              ) : null}
                              {!application.services.length ? (
                                <Typography.Text type="secondary" className="!text-xs">尚无服务上报</Typography.Text>
                              ) : null}
                            </div>
                          </Tooltip>
                        </div>
                      </div>
                    </button>
                  );
                })}
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
                <Typography.Text strong>
                  {namespace === undefined
                    ? '全部服务'
                    : selectedApplication?.name ?? (namespace || '未归类应用')}
                </Typography.Text>
                {namespace !== undefined ? (
                  <Button size="small" type="link" onClick={() => setNamespace(undefined)}>清除应用筛选</Button>
                ) : null}
              </div>
              <Typography.Text type="secondary" className="!text-xs tabular-nums">
                {filteredRows.length} 个环境视图 · {filteredServiceCount} 个逻辑服务
                {metricsLoading ? ' · 更新指标中…' : ''}
              </Typography.Text>
            </div>
            {state === 'ready' ? (
              <Table
                size="middle"
                columns={columns}
                dataSource={filteredRows}
                scroll={{ x: 1100 }}
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
      <Drawer
        title={(
          <div>
            <div className="text-[15px] font-semibold">已归档服务</div>
            <Typography.Text type="secondary" className="!text-xs">
              {archivedRows.length} 个归档服务 · 归档不会删除 Trace 或指标数据
            </Typography.Text>
          </div>
        )}
        open={archivedOpen}
        onClose={() => {
          setArchivedOpen(false);
          setArchivedKeyword('');
        }}
        width={560}
        extra={(
          <Input
            allowClear
            size="small"
            className="w-44"
            placeholder="搜索归档服务"
            prefix={<SearchOutlined className="text-[var(--color-text-4)]" aria-hidden="true" />}
            value={archivedKeyword}
            onChange={(event) => setArchivedKeyword(event.target.value)}
          />
        )}
      >
        <Alert
          showIcon
          type="info"
          className="mb-3"
          message="归档不等于删除。归档后告警自动暂停，可随时解档恢复。"
        />
        <List
          size="small"
          dataSource={archivedRows}
          locale={{ emptyText: '暂无已归档服务' }}
          renderItem={(service) => (
            <List.Item
              actions={[
                <Button
                  key="restore"
                  type="link"
                  size="small"
                  onClick={() => confirmArchive(service.id, false)}
                >
                  解档
                </Button>,
                service.environment_views[0]?.environment ? (
                  <Link
                    key="view"
                    href={`/apm/services/${service.id}?environment=${encodeURIComponent(service.environment_views[0].environment)}`}
                  >
                    <Button type="link" size="small">查看历史</Button>
                  </Link>
                ) : null,
              ].filter(Boolean)}
            >
              <List.Item.Meta
                title={(
                  <Space size={8}>
                    <span>{service.name}</span>
                    <Tag bordered={false} className="!m-0 !text-[11px]">
                      {service.archive_reason === 'manual' ? '手动归档' : '自动归档'}
                    </Tag>
                  </Space>
                )}
                description={(
                  <Space size={8} wrap className="!text-xs text-[var(--color-text-3)]">
                    <span>应用 = {service.application_name || '未归类应用'}</span>
                    <span>·</span>
                    <span>最后活跃 {formatRelativeTime(service.last_seen_at)}</span>
                  </Space>
                )}
              />
            </List.Item>
          )}
        />
      </Drawer>
      <OrganizationAssignmentModal
        open={Boolean(organizationService)}
        title={`调整服务组织${organizationService ? `：${organizationService.namespace}/${organizationService.name}` : ''}`}
        organizationIds={organizationService?.organization_ids ?? []}
        submitting={organizationSubmitting}
        description="服务组织独立于应用与实例，仅影响此逻辑服务的可见和可操作范围。"
        onCancel={() => setOrganizationService(null)}
        onSubmit={submitOrganizations}
      />
    </ApmRouteShell>
  );
}
