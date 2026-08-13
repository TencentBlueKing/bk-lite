'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import {
  AppstoreOutlined,
  BarsOutlined,
  BellOutlined,
  EditOutlined,
  InboxOutlined,
  LoadingOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import {
  Alert,
  Button,
  Drawer,
  Empty,
  Input,
  List,
  Modal,
  message,
  Segmented,
  Select,
  Space,
  Tag,
  Typography,
  type TableColumnsType,
} from 'antd';
import FilterToolbar from '@/components/filter-toolbar';
import MoreActionsDropdown from '@/components/more-actions-dropdown';
import type { MoreActionsDropdownItem } from '@/components/more-actions-dropdown';
import dayjs from 'dayjs';
import useApmApi from '@/app/apm/api';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, {
  catalogErrorKind,
  type CatalogStateKind,
} from '@/app/apm/components/catalog-state';
import {
  formatErrorRate,
  formatLatency,
  formatRelativeTime,
  formatThroughput,
  isErrorRateDanger,
  aggregateApplicationRedTrends,
} from '@/app/apm/components/metric-format';
import MetricValue from '@/app/apm/components/metric-value';
import MiniTrend from '@/app/apm/components/mini-trend';
import OrganizationAssignmentModal from '@/app/apm/components/organization-assignment-modal';
import ApplicationCard from '@/app/apm/components/application-card';
import type { ActiveAlertStatus } from '@/app/apm/components/application-card';
import ApmDataTable from '@/app/apm/components/apm-data-table';
import ServiceLanguage from '@/app/apm/components/service-language';
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
  language: string;
  serviceOrganizationIds: number[];
  serviceArchivedAt: string | null;
  archiveReason: string;
}

type PageState = CatalogStateKind | 'ready';
type ServicePerspective = 'application' | 'service';
type TimeWindow = '15m' | '1h' | '4h' | '1d' | '7d';
type AlertStatusFilter = ActiveAlertStatus;

interface ApplicationSummary {
  key: string;
  id: string;
  label: string;
  status: ActiveAlertStatus;
  services: { name: string; silent: boolean }[];
  environmentCount: number;
  requestRate: number | null;
  errorRate: number | null;
  requestRateTrend: number[];
  errorRateTrend: number[];
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
const isAlertStatusFilter = (value: string | null): value is AlertStatusFilter => (
  value === 'critical' || value === 'error' || value === 'warning' || value === 'info' || value === 'normal'
);

const severityRank: Record<string, number> = {
  critical: 1,
  error: 2,
  warning: 3,
  info: 4,
};

const alertStatusFromLevel = (level?: number): ActiveAlertStatus => {
  if (level === 1) return 'critical';
  if (level === 2) return 'error';
  if (level === 3) return 'warning';
  if (level === 4) return 'info';
  return 'normal';
};
const alertStatusPresentation: Record<ActiveAlertStatus, { label: string; color?: string }> = {
  critical: { label: '严重', color: 'red' },
  error: { label: '错误', color: 'volcano' },
  warning: { label: '警告', color: 'orange' },
  info: { label: '提示', color: 'blue' },
  normal: { label: '正常', color: 'green' },
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
  const [statusFilter, setStatusFilter] = useState<AlertStatusFilter | undefined>(() => {
    const value = searchParams.get('status');
    return isAlertStatusFilter(value) ? value : undefined;
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
    if (statusFilter) params.set('status', statusFilter);
    if (timeWindow !== '1h') params.set('window', timeWindow);
    const trimmed = keyword.trim();
    if (trimmed) params.set('q', trimmed);
    const next = params.toString();
    const current = searchParams.toString();
    if (next === current) return;
    router.replace(next ? `${pathname}?${next}` : pathname, { scroll: false });
  }, [
    environment,
    statusFilter,
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
        const visibleApplications = applicationItems.filter((application) => !application.is_builtin);
        const activeServices = items.filter((service) => !service.archived_at);
        setApplications(visibleApplications);
        setServices(activeServices);
        setArchivedServices(items.filter((service) => Boolean(service.archived_at)));
        setSlos(sloItems);
        setFiringEvents(events.filter((event) => event.status === 'firing'));
        setCatalogDegraded(health.catalog_reconcile.status === 'degraded');
        setState(visibleApplications.length || activeServices.length ? 'ready' : 'empty');
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
          language: service.language,
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
      const alertStatus = alertStatusFromLevel(alertCounts.get(alertKey(item.serviceName, item.environment))?.level);
      const matchesKeyword = !normalizedKeyword
        || `${item.namespace} ${item.serviceName} ${item.applicationName}`.toLowerCase().includes(normalizedKeyword);
      const matchesStatus = statusFilter === undefined || statusFilter === alertStatus;
      return matchesKeyword
        && (environment === undefined || item.environment === environment)
        && (namespace === undefined || item.namespace === namespace)
        && matchesStatus;
    });
  }, [alertCounts, environment, keyword, namespace, rows, statusFilter]);

  const applicationSummaries = useMemo<ApplicationSummary[]>(() => {
    const summaries = new Map<string, {
      serviceNames: Map<string, boolean>;
      environments: Set<string>;
      statuses: CatalogStatus[];
      metrics: ApmServiceRed[];
      metricUnavailable: boolean;
      alertCount: number;
      alertLevel: number;
      lastSeenAt: string | null;
    }>();
    const normalizedKeyword = keyword.trim().toLowerCase();
    const canShowWithoutServices = environment === undefined && (statusFilter === undefined || statusFilter === 'normal');
    applications.forEach((application) => {
      const matchesApplication = !normalizedKeyword
        || `${application.application_id} ${application.name}`.toLowerCase().includes(normalizedKeyword);
      const matchesNamespace = namespace === undefined || namespace === application.application_id;
      const visibleWithoutServices = canShowWithoutServices;
      if (!matchesApplication || !matchesNamespace || !visibleWithoutServices) return;
      summaries.set(application.application_id, {
        serviceNames: new Map(),
        environments: new Set(),
        statuses: [],
        metrics: [],
        metricUnavailable: false,
        alertCount: 0,
        alertLevel: 5,
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
        alertLevel: 5,
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
      const activeAlert = alertCounts.get(alertKey(row.serviceName, row.environment));
      current.alertCount += activeAlert?.count ?? 0;
      current.alertLevel = Math.min(current.alertLevel, activeAlert?.level ?? 5);
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
      const { requestRateTrend, errorRateTrend } = aggregateApplicationRedTrends(summary.metrics);
      const application = applications.find((item) => item.application_id === key);
      return {
        key,
        id: application?.id ?? key,
        label: application?.name ?? key,
        status: alertStatusFromLevel(summary.alertLevel),
        services: Array.from(summary.serviceNames.entries())
          .map(([name, silent]) => ({ name, silent }))
          .sort((left, right) => left.name.localeCompare(right.name)),
        environmentCount: summary.environments.size,
        requestRate,
        errorRate,
        requestRateTrend,
        errorRateTrend,
        metricUnavailable: summary.metricUnavailable,
        alertCount: summary.alertCount,
        lastSeenAt: summary.lastSeenAt,
      };
    }).sort((left, right) => left.label.localeCompare(right.label));
  }, [alertCounts, applications, environment, filteredRows, keyword, metricFailureKeys, namespace, redMetrics, statusFilter]);

  const archivedRows = useMemo(() => {
    const normalized = archivedKeyword.trim().toLowerCase();
    return archivedServices.filter((service) => (
      !normalized
      || `${service.namespace} ${service.name} ${service.application_name}`.toLowerCase().includes(normalized)
    ));
  }, [archivedKeyword, archivedServices]);

  const selectedApplication = applications.find((item) => item.application_id === namespace);

  const actionMenuItems = (item: ServiceEnvironmentRow): MoreActionsDropdownItem[] => [
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
  ];

  const columns: TableColumnsType<ServiceEnvironmentRow> = [
    {
      title: (
        <Space size={6}>
          <span>服务</span>
          {selectedApplication ? (
            <Tag bordered={false} color="blue" className="!m-0 !text-xs">
              {selectedApplication.name}
            </Tag>
          ) : null}
        </Space>
      ),
      key: 'service',
      render: (_, item) => {
        const silent = item.status === 'silent';
        const href = item.environment
          ? `/apm/services/${item.serviceId}?environment=${encodeURIComponent(item.environment)}&window=${timeWindow}`
          : undefined;
        return (
          <Space size={8} align="center" className={silent ? 'opacity-60' : undefined}>
            <ServiceLanguage language={item.language} />
            {href ? (
              <Link
                href={href}
                className="font-medium text-[var(--color-primary)] hover:underline"
              >
                {item.serviceName}
              </Link>
            ) : (
              <Typography.Text strong className="!text-sm">{item.serviceName}</Typography.Text>
            )}
            {silent ? <Tag bordered={false} className="!m-0 !text-xs text-[var(--color-text-3)]">静默</Tag> : null}
          </Space>
        );
      },
    },
    {
      title: '状态',
      key: 'status',
      width: 96,
      align: 'center',
      render: (_, item) => {
        const status = alertStatusFromLevel(alertCounts.get(alertKey(item.serviceName, item.environment))?.level);
        const presentation = alertStatusPresentation[status];
        return (
          <Tag
            bordered={false}
            color={presentation.color}
            aria-label={`最高活跃告警：${presentation.label}`}
            className="!m-0"
          >
            {presentation.label}
          </Tag>
        );
      },
    },
    {
      title: '活跃告警',
      key: 'alerts',
      width: 100,
      align: 'center',
      responsive: ['md'],
      render: (_, item) => {
        const alert = alertCounts.get(alertKey(item.serviceName, item.environment));
        const count = alert?.count ?? 0;
        const dangerous = count > 0 && (alert?.level ?? 5) <= 2;
        const eventsHref = `/apm/events/alerts?service=${encodeURIComponent(item.serviceName)}${
          item.environment ? `&environment=${encodeURIComponent(item.environment)}` : ''
        }`;
        return (
          <Link
            href={eventsHref}
            aria-label={`${item.serviceName} 有 ${count} 个活跃告警，查看告警`}
            className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs no-underline transition-colors duration-150 ${
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
      responsive: ['md'],
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
      responsive: ['md'],
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
      responsive: ['lg'],
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
      responsive: ['xl'],
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
      responsive: ['lg'],
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
            className={`!m-0 !text-xs ${
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
      width: 150,
      responsive: ['xl'],
      render: (value) => (
        <time
          className="whitespace-nowrap tabular-nums text-[var(--color-text-1)]"
          dateTime={value}
          title={dayjs(value).format('YYYY-MM-DD HH:mm:ss')}
        >
          {dayjs(value).format('YYYY-MM-DD HH:mm')}
        </time>
      ),
    },
    {
      title: '组织',
      dataIndex: 'serviceOrganizationIds',
      width: 120,
      responsive: ['xxl'],
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
      render: (_, item) => (
        <Permission requiredPermissions={['Operate']} permissionPath="/apm/services">
          <MoreActionsDropdown
            items={actionMenuItems(item)}
            ariaLabel="更多操作"
            stopPropagation
          />
        </Permission>
      ),
    },
  ];

  const catalogFilters = (
    <FilterToolbar align="start" spacing="flush" className="w-full" contentClassName="w-full">
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
      <Select<AlertStatusFilter>
        allowClear
        aria-label="按最高活跃告警筛选"
        className="w-36"
        placeholder="全部状态"
        value={statusFilter}
        options={[
          { value: 'critical', label: '严重' },
          { value: 'error', label: '错误' },
          { value: 'warning', label: '警告' },
          { value: 'info', label: '提示' },
          { value: 'normal', label: '正常' },
        ]}
        onChange={setStatusFilter}
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
        {metricsLoading ? (
          <span
            role="status"
            aria-live="polite"
            className="inline-flex items-center gap-1.5 text-xs text-[var(--color-text-3)]"
          >
            <LoadingOutlined spin className="text-[12px] text-[var(--color-primary)]" aria-hidden="true" />
            更新 {timeWindow} 指标
          </span>
        ) : null}
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
    </FilterToolbar>
  );

  return (
    <ApmRouteShell
      title="服务"
      description="按应用与服务浏览最高活跃告警状态和 RED 指标，点击名称进入对应详情。"
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
          description="服务目录仍可浏览，请稍后重试指标查询。"
          message={metricFailureKeys.length === rows.filter((row) => row.environment && !row.serviceArchivedAt).length
            ? 'RED 指标查询失败'
            : `部分 RED 指标查询失败（${metricFailureKeys.length} 项）`}
          showIcon
          role="alert"
          type="warning"
        />
      ) : null}
      <div className="flex flex-col gap-3">
        {perspective === 'application' ? (
          <ApmSurface padding="compact">{catalogFilters}</ApmSurface>
        ) : null}
        {perspective === 'application' ? (
          state === 'ready' ? (
            applicationSummaries.length ? (
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
                {applicationSummaries.map((application) => {
                  const alertServiceHint = application.services[0]?.name;
                  const servicesHref = `/apm/services?perspective=service&namespace=${encodeURIComponent(application.key)}`;
                  const eventsHref = alertServiceHint
                    ? `/apm/events/alerts?service=${encodeURIComponent(alertServiceHint)}`
                    : '/apm/events/alerts';
                  return (
                    <ApplicationCard
                      key={application.key || 'uncategorized'}
                      label={application.label}
                      status={application.status}
                      services={application.services}
                      requestRate={application.requestRate}
                      errorRate={application.errorRate}
                      requestRateTrend={application.requestRateTrend}
                      errorRateTrend={application.errorRateTrend}
                      metricUnavailable={application.metricUnavailable}
                      alertCount={application.alertCount}
                      timeWindow={timeWindow}
                      servicesHref={servicesHref}
                      eventsHref={eventsHref}
                      href={`/apm/integration/applications/${application.id}`}
                      onRetryMetrics={retryMetrics}
                    />
                  );
                })}
              </div>
            ) : (
              <ApmSurface>
                <Empty description="没有匹配的应用，请调整筛选条件。">
                  <Button onClick={() => {
                    setKeyword('');
                    setEnvironment(undefined);
                    setNamespace(undefined);
                    setStatusFilter(undefined);
                  }}>
                    清除筛选
                  </Button>
                </Empty>
              </ApmSurface>
            )
          ) : (
            <ApmSurface padding="none">
              <CatalogState
                kind={state}
                onRetry={state === 'forbidden' ? undefined : () => setRefreshKey((value) => value + 1)}
              />
            </ApmSurface>
          )
        ) : (
          <ApmSurface>
            <div className="flex flex-col gap-4">
              {catalogFilters}
              {state === 'ready' ? (
                <ApmDataTable
                  columns={columns}
                  dataSource={filteredRows}
                  rowKey="key"
                  pagination={{
                    defaultPageSize: 20,
                    pageSizeOptions: [10, 20, 50, 100],
                    showSizeChanger: true,
                    showTotal: (total) => `共 ${total} 条`,
                  }}
                />
              ) : (
                <CatalogState
                  kind={state}
                  onRetry={state === 'forbidden' ? undefined : () => setRefreshKey((value) => value + 1)}
                />
              )}
            </div>
          </ApmSurface>
        )}
      </div>
      <Drawer
        title={(
          <div>
            <div className="text-base font-semibold">已归档服务</div>
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
                    <Tag bordered={false} className="!m-0 !text-xs">
                      {service.archive_reason === 'manual' ? '手动归档' : service.archive_reason || '历史归档'}
                    </Tag>
                  </Space>
                )}
                description={(
                  <Space size={8} wrap className="!text-xs text-[var(--color-text-3)]">
                    <span>应用 = {service.application_name || '未绑定'}</span>
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
