'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState, type Key } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import {
  AppstoreOutlined,
  BarsOutlined,
  DownOutlined,
  InboxOutlined,
  LoadingOutlined,
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
  Tag,
  Typography,
} from 'antd';
import FilterToolbar from '@/components/filter-toolbar';
import Permission from '@/components/permission';
import dayjs from 'dayjs';
import useApmApi from '@/app/apm/api';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, {
  catalogErrorKind,
  type CatalogStateKind,
} from '@/app/apm/components/catalog-state';
import {
  aggregateApplicationRedTrends,
  formatRelativeTime,
} from '@/app/apm/components/metric-format';
import OrganizationAssignmentModal from '@/app/apm/components/organization-assignment-modal';
import ApplicationCard from '@/app/apm/components/application-card';
import type { ActiveAlertStatus } from '@/app/apm/components/application-card';
import ServiceCatalogTable from '@/app/apm/components/service-catalog-table';
import {
  alertStatusFromLevel,
  alertKey,
  countActiveAlerts,
  expandServiceRows,
  indexEnabledSlos,
  isAlertStatusFilter,
  isTimeWindow,
  metricKey,
  timeWindowUnits,
  type AlertStatusFilter,
  type TimeWindow,
} from '@/app/apm/components/service-catalog-model';
import type {
  ApmApplication,
  ApmEvent,
  ApmService,
  ApmServiceRed,
  ApmSlo,
  CatalogStatus,
} from '@/app/apm/types';
import { useUserInfoContext } from '@/context/userInfo';
import { useTranslation } from '@/utils/i18n';

type PageState = CatalogStateKind | 'ready';
type ServicePerspective = 'application' | 'service';

interface ApplicationSummary {
  key: string;
  id: string;
  label: string;
  status: ActiveAlertStatus;
  services: { name: string; silent: boolean; language?: string }[];
  environmentCount: number;
  requestRate: number | null;
  errorRate: number | null;
  requestRateTrend: number[];
  errorRateTrend: number[];
  metricUnavailable: boolean;
  alertCount: number;
  lastSeenAt: string | null;
}

export default function ApmServicesPage() {
  const { t } = useTranslation();
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
  const [organizationTargets, setOrganizationTargets] = useState<ApmService[]>([]);
  const [organizationSubmitting, setOrganizationSubmitting] = useState(false);
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([]);
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
        setFiringEvents(events.filter((event) => event.status === 'active'));
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
    if (!organizationTargets.length) return;
    setOrganizationSubmitting(true);
    try {
      const results = await Promise.allSettled(
        organizationTargets.map((service) => setServiceOrganizations(service.id, organizationIds)),
      );
      const failed = results.filter((result) => result.status === 'rejected').length;
      const succeeded = results.length - failed;
      if (failed) {
        message.warning(t('apm.services.orgBatchPartial', '已更新 {ok} 个服务组织，{failed} 个失败', { ok: succeeded, failed }));
      } else {
        message.success(
          organizationTargets.length > 1
            ? t('apm.services.orgBatchUpdated', '已更新 {count} 个服务组织', { count: succeeded })
            : t('apm.services.orgUpdated', '服务组织已更新'),
        );
      }
      setOrganizationTargets([]);
      setSelectedRowKeys([]);
      setRefreshKey((value) => value + 1);
    } finally {
      setOrganizationSubmitting(false);
    }
  };

  const setArchived = async (serviceIds: string[], archived: boolean) => {
    const uniqueIds = [...new Set(serviceIds)];
    const results = await Promise.allSettled(uniqueIds.map((serviceId) => setServiceArchived(serviceId, archived)));
    const failed = results.filter((result) => result.status === 'rejected').length;
    const succeeded = results.length - failed;
    if (failed) {
      message.warning(archived
        ? t('apm.services.archiveBatchPartial', '已归档 {ok} 个服务，{failed} 个失败', { ok: succeeded, failed })
        : t('apm.services.unarchiveBatchPartial', '已解档 {ok} 个服务，{failed} 个失败', { ok: succeeded, failed }));
    } else {
      message.success(archived
        ? uniqueIds.length > 1
          ? t('apm.services.archivedBatch', '已归档 {count} 个服务', { count: succeeded })
          : t('apm.services.archived', '服务已归档')
        : uniqueIds.length > 1
          ? t('apm.services.unarchivedBatch', '已解档 {count} 个服务', { count: succeeded })
          : t('apm.services.unarchived', '服务已解档'));
    }
    setSelectedRowKeys([]);
    setRefreshKey((value) => value + 1);
  };

  const confirmArchive = (serviceIds: string[], archived: boolean) => {
    const uniqueIds = [...new Set(serviceIds)];
    Modal.confirm({
      title: archived
        ? uniqueIds.length > 1
          ? t('apm.services.archiveBatchConfirm', '确认归档 {count} 个服务？', { count: uniqueIds.length })
          : t('apm.services.archiveConfirm', '确认归档服务？')
        : uniqueIds.length > 1
          ? t('apm.services.unarchiveBatchConfirm', '确认解档 {count} 个服务？', { count: uniqueIds.length })
          : t('apm.services.unarchiveConfirm', '确认解档服务？'),
      content: archived
        ? t('apm.services.archiveHint', '归档不会删除 Trace 或指标数据。')
        : t('apm.services.unarchiveHint', '解档后服务将重新出现在默认目录。'),
      okText: archived ? t('apm.services.archive', '归档') : t('apm.services.unarchive', '解档'),
      okButtonProps: archived ? { danger: true } : undefined,
      cancelText: t('common.cancel', '取消'),
      onOk: () => setArchived(uniqueIds, archived),
    });
  };

  const rows = useMemo(() => expandServiceRows(services), [services]);

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

  const alertCounts = useMemo(() => countActiveAlerts(firingEvents), [firingEvents]);
  const sloByServiceEnv = useMemo(() => indexEnabledSlos(slos), [slos]);

  const environmentOptions = useMemo(
    () => Array.from(new Set(rows.map((item) => item.environment)))
      .sort()
      .map((value) => ({ value, label: value || t('apm.common.unset', '未设置') })),
    [rows, t]
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

  const selectedServices = useMemo(() => {
    const selectedIds = new Set(
      filteredRows.filter((row) => selectedRowKeys.includes(row.key)).map((row) => row.serviceId),
    );
    return services.filter((service) => selectedIds.has(service.id));
  }, [filteredRows, selectedRowKeys, services]);

  const organizationIdsForModal = useMemo(() => {
    if (!organizationTargets.length) return [];
    const signature = [...organizationTargets[0].organization_ids].sort().join(',');
    const same = organizationTargets.every((service) => [...service.organization_ids].sort().join(',') === signature);
    return same ? organizationTargets[0].organization_ids : [];
  }, [organizationTargets]);

  const mixedOrganizationTargets = useMemo(() => {
    if (organizationTargets.length <= 1) return false;
    const signature = [...organizationTargets[0].organization_ids].sort().join(',');
    return organizationTargets.some((service) => [...service.organization_ids].sort().join(',') !== signature);
  }, [organizationTargets]);

  const applicationSummaries = useMemo<ApplicationSummary[]>(() => {
    const summaries = new Map<string, {
      serviceInfos: Map<string, { silent: boolean; language: string }>;
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
        serviceInfos: new Map(),
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
        serviceInfos: new Map<string, { silent: boolean; language: string }>(),
        environments: new Set<string>(),
        statuses: [],
        metrics: [],
        metricUnavailable: false,
        alertCount: 0,
        alertLevel: 5,
        lastSeenAt: null,
      };
      const previous = current.serviceInfos.get(row.serviceName);
      current.serviceInfos.set(row.serviceName, {
        silent: row.status === 'silent' || Boolean(previous?.silent),
        language: row.language || previous?.language || '',
      });
      current.environments.add(row.environment || t('apm.common.unset', '未设置'));
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
        services: Array.from(summary.serviceInfos.entries())
          .map(([name, info]) => ({ name, silent: info.silent, language: info.language }))
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
  }, [alertCounts, applications, environment, filteredRows, keyword, metricFailureKeys, namespace, redMetrics, statusFilter, t]);

  const archivedRows = useMemo(() => {
    const normalized = archivedKeyword.trim().toLowerCase();
    return archivedServices.filter((service) => (
      !normalized
      || `${service.namespace} ${service.name} ${service.application_name}`.toLowerCase().includes(normalized)
    ));
  }, [archivedKeyword, archivedServices]);

  const selectedApplication = applications.find((item) => item.application_id === namespace);

  const catalogFilters = (
    <FilterToolbar align="start" spacing="flush" className="w-full" contentClassName="w-full">
      <div className="flex items-center gap-2 border-r border-[var(--color-border)] pr-3">
        <Segmented<ServicePerspective>
          aria-label={t('apm.services.viewMode', '服务目录视角')}
          options={[
            { value: 'application', label: <span><AppstoreOutlined aria-hidden="true" className="mr-1" />{t('apm.common.application', '应用')}</span> },
            { value: 'service', label: <span><BarsOutlined aria-hidden="true" className="mr-1" />{t('apm.common.service', '服务')}</span> },
          ]}
          value={perspective}
          onChange={setPerspective}
        />
      </div>
      <Input
        allowClear
        aria-label={t('apm.services.search', '按应用或服务名称搜索')}
        className="min-w-52 flex-1 md:max-w-xs"
        prefix={<SearchOutlined className="text-[var(--color-text-4)]" aria-hidden="true" />}
        placeholder={t('apm.services.search', '按应用或服务名称搜索')}
        value={keyword}
        onChange={(event) => setKeyword(event.target.value)}
      />
      <Select
        allowClear
        aria-label={t('apm.services.filterEnvironment', '按环境筛选')}
        className="w-36"
        placeholder={t('apm.common.allEnvironments', '全部环境')}
        value={environment}
        options={environmentOptions}
        onChange={setEnvironment}
      />
      <Select
        allowClear
        aria-label={t('apm.services.filterApplication', '按应用筛选')}
        className="w-40"
        placeholder={t('apm.common.allApplications', '全部应用')}
        value={namespace}
        options={namespaceOptions}
        onChange={setNamespace}
      />
      <Select<AlertStatusFilter>
        allowClear
        aria-label={t('apm.services.filterAlert', '按最高活跃告警筛选')}
        className="w-36"
        placeholder={t('apm.common.allStatuses', '全部状态')}
        value={statusFilter}
        options={[
          { value: 'critical', label: t('apm.severity.critical', '严重') },
          { value: 'error', label: t('apm.severity.error', '错误') },
          { value: 'warning', label: t('apm.severity.warning', '警告') },
          { value: 'info', label: t('apm.severity.info', '提示') },
          { value: 'normal', label: t('apm.severity.normal', '正常') },
        ]}
        onChange={setStatusFilter}
      />
      <div className="ml-auto flex flex-wrap items-center gap-2">
        <Typography.Text type="secondary" className="!text-xs">{t('apm.common.timeWindow', '时间窗')}</Typography.Text>
        <Segmented<TimeWindow>
          aria-label={t('apm.services.metricWindow', '服务指标时间窗口')}
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
            {t('apm.services.updatingMetrics', '更新 {window} 指标', { window: timeWindow })}
          </span>
        ) : null}
        {perspective === 'service' ? (
          <Permission requiredPermissions={['Operate']} permissionPath="/apm/services">
            <Dropdown
              disabled={!selectedServices.length}
              menu={{
                items: [
                  {
                    key: 'organization',
                    label: t('apm.services.adjustOrgAction', '调整组织'),
                    onClick: () => setOrganizationTargets(selectedServices),
                  },
                  {
                    key: 'archive',
                    danger: true,
                    label: t('apm.services.archive', '归档'),
                    onClick: () => confirmArchive(selectedServices.map((service) => service.id), true),
                  },
                ],
              }}
            >
              <Button aria-label={t('apm.services.batchActions', '批量操作')} disabled={!selectedServices.length}>
                {t('apm.services.batchActions', '批量操作')}
                <DownOutlined aria-hidden="true" />
              </Button>
            </Dropdown>
          </Permission>
        ) : null}
        {perspective === 'service' ? (
          <Button
            icon={<InboxOutlined aria-hidden="true" />}
            onClick={() => setArchivedOpen(true)}
          >
            {t('apm.status.archived', '已归档')}
            {archivedServices.length ? (
              <span className="ml-1 tabular-nums text-[var(--color-text-3)]">{archivedServices.length}</span>
            ) : null}
          </Button>
        ) : null}
      </div>
    </FilterToolbar>
  );

  return (
    <ApmRouteShell
      title={t('apm.services.title', '服务')}
      description={t('apm.services.description', '按应用与服务浏览最高活跃告警状态和 RED 指标，点击名称进入对应详情。')}
      dependency="telemetry"
    >
      {catalogDegraded ? (
        <Alert
          className="mb-4"
          type="warning"
          showIcon
          message={t('apm.services.reconcileDegraded', '目录对账暂时降级，当前列表可能不是最新状态。')}
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
              {t('apm.common.retryRed', '重试 RED 指标')}
            </Button>
          )}
          className="mb-4"
          description={t('apm.services.metricsDegraded', '服务目录仍可浏览，请稍后重试指标查询。')}
          message={metricFailureKeys.length === rows.filter((row) => row.environment && !row.serviceArchivedAt).length
            ? t('apm.services.redFailed', 'RED 指标查询失败')
            : t('apm.services.redPartialFailed', '部分 RED 指标查询失败（{count} 项）', { count: metricFailureKeys.length })}
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
                      href={`/apm/services/applications/${application.id}${timeWindow !== '1h' ? `?window=${timeWindow}` : ''}`}
                      onRetryMetrics={retryMetrics}
                    />
                  );
                })}
              </div>
            ) : (
              <ApmSurface>
                <Empty description={t('apm.services.noMatchingApps', '没有匹配的应用，请调整筛选条件。')}>
                  <Button onClick={() => {
                    setKeyword('');
                    setEnvironment(undefined);
                    setNamespace(undefined);
                    setStatusFilter(undefined);
                  }}>
                    {t('apm.services.clearFilters', '清除筛选')}
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
                <ServiceCatalogTable
                  alertCounts={alertCounts}
                  groupNames={groupNames}
                  metricFailureKeys={metricFailureKeys}
                  onAdjustOrganization={(serviceId) => setOrganizationTargets(services.filter((service) => service.id === serviceId))}
                  onArchive={(serviceId) => confirmArchive([serviceId], true)}
                  rowSelection={{
                    selectedRowKeys,
                    onChange: setSelectedRowKeys,
                    preserveSelectedRowKeys: true,
                  }}
                  onRetryMetrics={retryMetrics}
                  redMetrics={redMetrics}
                  rows={filteredRows}
                  selectedApplicationName={selectedApplication?.name}
                  sloByServiceEnv={sloByServiceEnv}
                  timeWindow={timeWindow}
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
            <div className="text-base font-semibold">{t('apm.services.archivedTitle', '已归档服务')}</div>
            <Typography.Text type="secondary" className="!text-xs">
              {t('apm.services.archivedSubtitle', '{count} 个归档服务 · 归档不会删除 Trace 或指标数据', { count: archivedRows.length })}
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
            placeholder={t('apm.services.searchArchived', '搜索归档服务')}
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
          message={t('apm.services.archiveNote', '归档不等于删除。归档后告警自动暂停，可随时解档恢复。')}
        />
        <List
          size="small"
          dataSource={archivedRows}
          locale={{ emptyText: t('apm.services.noArchived', '暂无已归档服务') }}
          renderItem={(service) => (
            <List.Item
              actions={[
                <Button
                  key="restore"
                  type="link"
                  size="small"
                  onClick={() => confirmArchive([service.id], false)}
                >
                  {t('apm.services.unarchive', '解档')}
                </Button>,
                service.environment_views[0]?.environment ? (
                  <Link
                    key="view"
                    href={`/apm/services/${service.id}?environment=${encodeURIComponent(service.environment_views[0].environment)}`}
                  >
                    <Button type="link" size="small">{t('apm.services.viewHistory', '查看历史')}</Button>
                  </Link>
                ) : null,
              ].filter(Boolean)}
            >
              <List.Item.Meta
                title={(
                  <Space size={8}>
                    <span>{service.name}</span>
                    <Tag bordered={false} className="!m-0 !text-xs">
                      {service.archive_reason === 'manual' ? t('apm.services.manualArchive', '手动归档') : service.archive_reason || t('apm.services.historyArchive', '历史归档')}
                    </Tag>
                  </Space>
                )}
                description={(
                  <Space size={8} wrap className="!text-xs text-[var(--color-text-3)]">
                    <span>{t('apm.services.appEquals', '应用 = {name}', { name: service.application_name || t('apm.services.unbound', '未绑定') })}</span>
                    <span>·</span>
                    <span>{t('apm.services.lastActive', '最后活跃 {time}', { time: formatRelativeTime(service.last_seen_at, t) })}</span>
                  </Space>
                )}
              />
            </List.Item>
          )}
        />
      </Drawer>
      <OrganizationAssignmentModal
        open={organizationTargets.length > 0}
        title={organizationTargets.length > 1
          ? t('apm.services.adjustOrgBatch', '调整服务组织（{count} 个服务）', { count: organizationTargets.length })
          : organizationTargets[0]
            ? t('apm.services.adjustOrgNamed', '调整服务组织：{identity}', { identity: `${organizationTargets[0].namespace}/${organizationTargets[0].name}` })
            : t('apm.services.adjustOrg', '调整服务组织')}
        organizationIds={organizationIdsForModal}
        submitting={organizationSubmitting}
        description={mixedOrganizationTargets
          ? t('apm.services.orgBatchHint', '所选服务当前组织不一致，保存后将覆盖为同一组组织。')
          : t('apm.services.orgHint', '服务组织独立于应用与实例，仅影响此逻辑服务的可见和可操作范围。')}
        onCancel={() => setOrganizationTargets([])}
        onSubmit={submitOrganizations}
      />
    </ApmRouteShell>
  );
}
