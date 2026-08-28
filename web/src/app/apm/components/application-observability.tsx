'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { PlusOutlined } from '@ant-design/icons';
import { Button, Modal, Segmented, Typography, message } from 'antd';
import useApmApi from '@/app/apm/api';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import {
  formatErrorRate,
  formatLatency,
  formatPerSecond,
  formatThroughput,
} from '@/app/apm/components/metric-format';
import OrganizationAssignmentModal from '@/app/apm/components/organization-assignment-modal';
import ServiceCatalogTable from '@/app/apm/components/service-catalog-table';
import {
  countActiveAlerts,
  expandServiceRows,
  indexEnabledSlos,
  isTimeWindow,
  metricKey,
  timeWindowRange,
  type TimeWindow,
} from '@/app/apm/components/service-catalog-model';
import TopologyCanvas, { type TopologyLayoutMode } from '@/app/apm/services/topology/topology-canvas';
import { focusApplicationTopology } from '@/app/apm/services/topology/topology-layout';
import type { ApmApplication, ApmEvent, ApmService, ApmServiceRed, ApmSlo, ApmTopologyGraph } from '@/app/apm/types';
import { useUserInfoContext } from '@/context/userInfo';
import { useTranslation } from '@/utils/i18n';

type PageState = CatalogStateKind | 'ready';

interface KeyInfoItem {
  label: string;
  value: string;
}

export default function ApplicationObservability({
  applicationId,
  showAddIngest = false,
}: {
  applicationId: string;
  showAddIngest?: boolean;
}) {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const {
    getApplication,
    getServices,
    getServiceRed,
    getTopology,
    getEvents,
    getSlos,
    setServiceArchived,
    setServiceOrganizations,
    isLoading,
  } = useApmApi();
  const { flatGroups } = useUserInfoContext();
  const [application, setApplication] = useState<ApmApplication>();
  const [services, setServices] = useState<ApmService[]>([]);
  const [state, setState] = useState<PageState>('loading');
  const [graph, setGraph] = useState<ApmTopologyGraph>({ nodes: [], edges: [], sampled_traces: 0, truncated: false, data_state: 'no_data' });
  const [topologyLoading, setTopologyLoading] = useState(true);
  const [redMetrics, setRedMetrics] = useState<Record<string, ApmServiceRed>>({});
  const [metricFailureKeys, setMetricFailureKeys] = useState<string[]>([]);
  const [events, setEvents] = useState<ApmEvent[]>([]);
  const [slos, setSlos] = useState<ApmSlo[]>([]);
  const [timeWindow, setTimeWindow] = useState<TimeWindow>(() => {
    const value = searchParams.get('window');
    return isTimeWindow(value) ? value : '1h';
  });
  const [layout, setLayout] = useState<TopologyLayoutMode>('layered');
  const [organizationService, setOrganizationService] = useState<ApmService | null>(null);
  const [organizationSubmitting, setOrganizationSubmitting] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [metricRefreshKey, setMetricRefreshKey] = useState(0);

  const groupNames = useMemo(
    () => new Map(flatGroups.map((group) => [Number(group.id), group.name])),
    [flatGroups],
  );

  useEffect(() => {
    if (isLoading || !applicationId) return;
    setState('loading');
    Promise.all([
      getApplication(applicationId),
      getServices(),
      getEvents({ limit: 100 }).catch(() => [] as ApmEvent[]),
      getSlos().catch(() => [] as ApmSlo[]),
    ])
      .then(([item, allServices, eventItems, sloItems]) => {
        setApplication(item);
        setServices(allServices.filter((service) => service.application_id === item.application_id));
        setEvents(eventItems);
        setSlos(sloItems);
        setState('ready');
      })
      .catch((error) => setState(catalogErrorKind(error)));
  }, [applicationId, getApplication, getEvents, getServices, getSlos, isLoading, refreshKey]);

  useEffect(() => {
    if (!application) return;
    const { startedAt, endedAt } = timeWindowRange(timeWindow);
    setTopologyLoading(true);
    getTopology({
      started_at: startedAt.toISOString(),
      ended_at: endedAt.toISOString(),
      include_inferred: true,
      include_user_request: true,
    })
      .then((topology) => {
        setGraph(focusApplicationTopology(topology, application.application_id).graph);
      })
      .catch(() => {
        setGraph({ nodes: [], edges: [], sampled_traces: 0, truncated: false, data_state: 'no_data' });
      })
      .finally(() => setTopologyLoading(false));
  }, [application, getTopology, timeWindow]);

  const rows = useMemo(() => expandServiceRows(services), [services]);

  useEffect(() => {
    const targets = rows.filter((row) => row.environment && !row.serviceArchivedAt);
    if (!targets.length) {
      setRedMetrics({});
      setMetricFailureKeys([]);
      return;
    }
    let active = true;
    const { startedAt, endedAt } = timeWindowRange(timeWindow);
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
      });
    return () => {
      active = false;
    };
  }, [getServiceRed, metricRefreshKey, rows, timeWindow]);

  const alertCounts = useMemo(() => countActiveAlerts(events), [events]);
  const sloByServiceEnv = useMemo(() => indexEnabledSlos(slos), [slos]);
  const applicationAlertCount = useMemo(
    () => rows.reduce((sum, row) => sum + (alertCounts.get(`${row.serviceName}::${row.environment}`)?.count ?? 0), 0),
    [alertCounts, rows],
  );
  const applicationSloCount = useMemo(
    () => new Set(rows.filter((row) => sloByServiceEnv.has(metricKey(row.serviceId, row.environment))).map((row) => row.serviceId)).size,
    [rows, sloByServiceEnv],
  );

  const keyInfo = useMemo<KeyInfoItem[]>(() => {
    const metrics = Object.values(redMetrics);
    const requestRate = metrics.reduce((sum, red) => sum + (red.request_rate ?? 0), 0);
    const weightedErrors = metrics.reduce((sum, red) => sum + (red.request_rate ?? 0) * (red.error_rate ?? 0), 0);
    return [
      { label: t('apm.common.throughput', '吞吐量'), value: formatPerSecond(formatThroughput(requestRate || null, false, t), t) },
      { label: t('apm.common.errorRate', '错误率'), value: formatErrorRate(requestRate ? weightedErrors / requestRate : null, false, t) },
      { label: t('apm.common.p99', 'P99'), value: formatLatency(metrics.reduce<number | null>((max, red) => red.p99_ms == null ? max : Math.max(max ?? 0, red.p99_ms), null), false, t) },
      { label: t('apm.applications.serviceCount', '服务数'), value: String(services.length) },
      { label: t('apm.applications.alertCount', '告警数'), value: String(applicationAlertCount) },
      { label: t('apm.slo.title', 'SLO'), value: String(applicationSloCount) },
    ];
  }, [applicationAlertCount, applicationSloCount, redMetrics, services.length, t]);

  const confirmArchive = (serviceId: string) => {
    Modal.confirm({
      title: t('apm.services.archiveConfirm', '确认归档服务？'),
      content: t('apm.services.archiveHint', '归档不会删除 Trace 或指标数据。'),
      okText: t('apm.services.archive', '归档'),
      okButtonProps: { danger: true },
      cancelText: t('common.cancel', '取消'),
      onOk: async () => {
        await setServiceArchived(serviceId, true);
        message.success(t('apm.services.archived', '服务已归档'));
        setRefreshKey((value) => value + 1);
      },
    });
  };

  const submitOrganizations = async (organizationIds: number[]) => {
    if (!organizationService) return;
    setOrganizationSubmitting(true);
    try {
      await setServiceOrganizations(organizationService.id, organizationIds);
      message.success(t('apm.services.orgUpdated', '服务组织已更新'));
      setOrganizationService(null);
      setRefreshKey((value) => value + 1);
    } finally {
      setOrganizationSubmitting(false);
    }
  };

  return (
    <ApmRouteShell
      title={application?.name ?? t('apm.applications.detailTitle', '应用详情')}
      description={t('apm.applications.observabilityDescription', '查看应用拓扑、关键信息与该应用下的服务。')}
    >
      {state === 'ready' && application ? (
        <div className="flex flex-col gap-3">
          <div className="grid gap-3 xl:grid-cols-3">
            <ApmSurface className="min-w-0 xl:col-span-2" padding="none">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--color-border)] px-4 py-3">
                <div className="flex min-w-0 items-center gap-2">
                  <Typography.Text strong>{t('apm.applications.topology', '应用服务拓扑')}</Typography.Text>
                  <Typography.Text type="secondary" className="min-w-0 truncate !text-xs">
                    {application.name}
                  </Typography.Text>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Typography.Text type="secondary" className="!text-xs">{t('apm.common.timeWindow', '时间窗')}</Typography.Text>
                  <Segmented<TimeWindow>
                    aria-label={t('apm.services.metricWindow', '服务指标时间窗口')}
                    options={['15m', '1h', '4h', '1d', '7d']}
                    size="small"
                    value={timeWindow}
                    onChange={setTimeWindow}
                  />
                  <Segmented<TopologyLayoutMode>
                    aria-label={t('apm.topology.layout', '拓扑布局')}
                    options={[
                      { value: 'layered', label: t('apm.topology.layered', '层次') },
                      { value: 'force', label: t('apm.topology.force', '力导向') },
                    ]}
                    size="small"
                    value={layout}
                    onChange={setLayout}
                  />
                  {showAddIngest ? (
                    <Link href={`/apm/integration/add?application_id=${encodeURIComponent(application.application_id)}`}>
                      <Button type="primary" icon={<PlusOutlined aria-hidden="true" />} size="small">{t('apm.applications.addIngest', '添加接入')}</Button>
                    </Link>
                  ) : null}
                </div>
              </div>
              {topologyLoading && !graph.nodes.length ? (
                <div className="min-h-[640px]">
                  <CatalogState kind="loading" />
                </div>
              ) : graph.nodes.length ? (
                <TopologyCanvas
                  edges={graph.edges}
                  focusNamespace={application.application_id}
                  keyword=""
                  layout={layout}
                  nodes={graph.nodes}
                  zoom={1}
                />
              ) : (
                <CatalogState kind="empty" description={t('apm.applications.noTopology', '当前时间窗暂无应用内调用关系。')} />
              )}
            </ApmSurface>
            <ApmSurface>
              <Typography.Text strong>{t('apm.applications.keyInfo', '关键信息')}</Typography.Text>
              <div className="mt-3 grid grid-cols-2 gap-3">
                {keyInfo.map((item) => (
                  <div key={item.label} className="rounded-lg bg-[var(--color-fill-1)] p-3">
                    <Typography.Text type="secondary" className="block !text-xs">{item.label}</Typography.Text>
                    <div className="mt-1 text-xl font-semibold tabular-nums">{item.value}</div>
                  </div>
                ))}
              </div>
            </ApmSurface>
          </div>
          <ApmSurface>
            <div className="mb-4">
              <Typography.Text strong>{t('apm.applications.childServices', '下属服务')}</Typography.Text>
              <Typography.Text type="secondary" className="ml-2 !text-xs">{t('apm.common.serviceCount', '共 {count} 个', { count: services.length })}</Typography.Text>
            </div>
            {rows.length ? (
              <ServiceCatalogTable
                alertCounts={alertCounts}
                groupNames={groupNames}
                metricFailureKeys={metricFailureKeys}
                onAdjustOrganization={(serviceId) => setOrganizationService(services.find((service) => service.id === serviceId) ?? null)}
                onArchive={confirmArchive}
                onRetryMetrics={() => setMetricRefreshKey((value) => value + 1)}
                redMetrics={redMetrics}
                rows={rows}
                selectedApplicationName={application.name}
                sloByServiceEnv={sloByServiceEnv}
                timeWindow={timeWindow}
              />
            ) : (
              <CatalogState
                kind="empty"
                description={t('apm.applications.noServices', '该应用还没有观测到服务。')}
                action={showAddIngest ? (
                  <Link href={`/apm/integration/add?application_id=${encodeURIComponent(application.application_id)}`}>
                    <Button type="primary">{t('apm.applications.addIngest', '添加接入')}</Button>
                  </Link>
                ) : undefined}
              />
            )}
          </ApmSurface>
          <OrganizationAssignmentModal
            open={Boolean(organizationService)}
            title={organizationService
              ? t('apm.services.adjustOrgNamed', '调整服务组织：{identity}', { identity: `${organizationService.namespace}/${organizationService.name}` })
              : t('apm.services.adjustOrg', '调整服务组织')}
            organizationIds={organizationService?.organization_ids ?? []}
            submitting={organizationSubmitting}
            description={t('apm.services.orgHint', '服务组织独立于应用与实例，仅影响此逻辑服务的可见和可操作范围。')}
            onCancel={() => setOrganizationService(null)}
            onSubmit={submitOrganizations}
          />
        </div>
      ) : (
        <ApmSurface padding="none">
          <CatalogState kind={state === 'ready' ? 'error' : state} />
        </ApmSurface>
      )}
    </ApmRouteShell>
  );
}
