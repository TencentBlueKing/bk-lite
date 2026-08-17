'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { ArrowLeftOutlined, PlusOutlined } from '@ant-design/icons';
import { Button, Space, Tag, Typography, type TableColumnsType } from 'antd';
import useApmApi from '@/app/apm/api';
import ApmDataTable, { APM_TABLE_COLUMN_WIDTHS } from '@/app/apm/components/apm-data-table';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import ServiceLanguage from '@/app/apm/components/service-language';
import ApmStatusTag from '@/app/apm/components/status-tag';
import { TopologyCanvas } from '@/app/apm/services/topology/page';
import { formatErrorRate, formatLatency, formatThroughput } from '@/app/apm/components/metric-format';
import type { ApmApplication, ApmService, ApmServiceRed, ApmTopologyGraph } from '@/app/apm/types';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { useTranslation } from '@/utils/i18n';

type PageState = CatalogStateKind | 'ready';

export default function ApmApplicationDetailPage() {
  const { t } = useTranslation();
  const params = useParams<{ applicationId: string }>();
  const { getApplication, getServices, getServiceRed, getTopology, isLoading } = useApmApi();
  const [application, setApplication] = useState<ApmApplication>();
  const [services, setServices] = useState<ApmService[]>([]);
  const [state, setState] = useState<PageState>('loading');
  const [graph, setGraph] = useState<ApmTopologyGraph>({ nodes: [], edges: [], sampled_traces: 0, truncated: false, data_state: 'no_data' });
  const [reds, setReds] = useState<ApmServiceRed[]>([]);

  useEffect(() => {
    if (isLoading || !params.applicationId) return;
    setState('loading');
    const endedAt = new Date();
    const startedAt = new Date(endedAt.getTime() - 3600000);
    Promise.all([getApplication(params.applicationId), getServices(), getTopology({ started_at: startedAt.toISOString(), ended_at: endedAt.toISOString() })])
      .then(async ([item, allServices, topology]) => {
        const applicationServices = allServices.filter((service) => service.application_id === item.application_id);
        setApplication(item);
        setServices(applicationServices);
        const nodeIds = new Set(topology.nodes.filter((node) => node.service_namespace === item.application_id).map((node) => node.id));
        setGraph({ ...topology, nodes: topology.nodes.filter((node) => nodeIds.has(node.id)), edges: topology.edges.filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target)) });
        const metrics = await Promise.allSettled(applicationServices.flatMap((service) => {
          const environment = service.environment_views[0]?.environment;
          return environment === undefined ? [] : [getServiceRed(service.id, environment, startedAt.toISOString(), endedAt.toISOString())];
        }));
        setReds(metrics.flatMap((result) => result.status === 'fulfilled' ? [result.value] : []));
        setState('ready');
      })
      .catch((error) => setState(catalogErrorKind(error)));
  }, [getApplication, getServiceRed, getServices, getTopology, isLoading, params.applicationId]);

  const kpis = useMemo(() => {
    const requestRate = reds.reduce((sum, red) => sum + (red.request_rate ?? 0), 0);
    const weightedErrors = reds.reduce((sum, red) => sum + (red.request_rate ?? 0) * (red.error_rate ?? 0), 0);
    return [
      { label: t('apm.applications.serviceCount', '服务数'), value: String(services.length) },
      { label: t('apm.common.throughput', '吞吐量'), value: `${formatThroughput(requestRate)}/s` },
      { label: t('apm.common.errorRate', '错误率'), value: formatErrorRate(requestRate ? weightedErrors / requestRate : null) },
      { label: t('apm.common.p95', 'P95'), value: formatLatency(reds.reduce<number | null>((max, red) => red.p95_ms == null ? max : Math.max(max ?? 0, red.p95_ms), null)) },
    ];
  }, [reds, services.length, t]);

  const columns = useMemo<TableColumnsType<ApmService>>(() => [
    {
      title: t('apm.common.service', '服务'),
      render: (_, service) => (
        <Space size={8}>
          <ServiceLanguage language={service.language} />
          <Link
            href={`/apm/services/${service.id}${service.environment_views[0]?.environment ? `?environment=${encodeURIComponent(service.environment_views[0].environment)}` : ''}`}
            className="font-medium text-[var(--color-primary)] hover:underline"
          >
            {service.name}
          </Link>
        </Space>
      ),
    },
    {
      title: t('apm.common.environment', '环境'),
      responsive: ['sm'],
      render: (_, service) => (
        <div className="flex flex-wrap gap-1">
          {service.environment_views.length
            ? service.environment_views.map((view) => <Tag bordered={false} key={view.environment}>{view.environment || t('apm.common.unset', '未设置')}</Tag>)
            : <Typography.Text type="secondary">—</Typography.Text>}
        </div>
      ),
    },
    { title: t('apm.common.status', '状态'), dataIndex: 'status', width: APM_TABLE_COLUMN_WIDTHS.status, align: 'center', render: (value) => <ApmStatusTag status={value} /> },
    {
      title: t('apm.instances.lastReport', '最近上报'),
      dataIndex: 'last_seen_at',
      width: APM_TABLE_COLUMN_WIDTHS.timestamp,
      responsive: ['lg'],
      render: (value) => <EllipsisWithTooltip text={new Date(value).toLocaleString()} />,
    },
  ], [t]);

  return (
    <ApmRouteShell
      title={application?.name ?? t('apm.applications.detailTitle', '应用详情')}
      description={t('apm.applications.detailDescription', '查看应用边界、下属服务并发起新的遥测接入。')}
    >
      {state === 'ready' && application ? (
        <div className="flex flex-col gap-3">
          <div className="flex justify-end gap-2">
            <Link href="/apm/integration/applications"><Button icon={<ArrowLeftOutlined aria-hidden="true" />}>{t('apm.applications.backToList', '返回列表')}</Button></Link>
            <Link href={`/apm/integration/add?application_id=${encodeURIComponent(application.application_id)}`}>
              <Button type="primary" icon={<PlusOutlined aria-hidden="true" />}>{t('apm.applications.addIngest', '添加接入')}</Button>
            </Link>
          </div>
          <div className="grid gap-3 xl:grid-cols-3">
            <ApmSurface className="min-w-0 xl:col-span-2">
              <div className="mb-2"><Typography.Text strong>{t('apm.applications.topology', '应用服务拓扑')}</Typography.Text><Typography.Text type="secondary" className="ml-2 !text-xs">{application.application_id}</Typography.Text></div>
              {graph.nodes.length ? <TopologyCanvas nodes={graph.nodes} edges={graph.edges} keyword="" zoom={1} /> : <CatalogState kind="empty" description={t('apm.applications.noTopology', '当前时间窗暂无应用内调用关系。')} />}
            </ApmSurface>
            <ApmSurface>
              <Typography.Text strong>{t('apm.applications.kpi', '应用 KPI')}</Typography.Text>
              <div className="mt-3 grid grid-cols-2 gap-3 xl:grid-cols-1">
                {kpis.map((kpi) => <div key={kpi.label} className="rounded-lg bg-[var(--color-fill-1)] p-3"><Typography.Text type="secondary" className="block !text-xs">{kpi.label}</Typography.Text><div className="mt-1 text-xl font-semibold tabular-nums">{kpi.value}</div></div>)}
              </div>
              <div className="mt-4 border-t border-[var(--color-border-1)] pt-3"><Typography.Text type="secondary" className="block !text-xs">{t('apm.applications.note', '说明')}</Typography.Text><Typography.Paragraph className="!mb-0 !mt-1 !text-sm">{application.description || '—'}</Typography.Paragraph></div>
            </ApmSurface>
          </div>
          <ApmSurface>
            <div className="mb-4">
              <Typography.Text strong>{t('apm.applications.childServices', '下属服务')}</Typography.Text>
              <Typography.Text type="secondary" className="ml-2 !text-xs">{t('apm.common.serviceCount', '共 {count} 个', { count: services.length })}</Typography.Text>
            </div>
            {services.length ? (
              <ApmDataTable
                columns={columns}
                dataSource={services}
                rowKey="id"
                pagination={{ defaultPageSize: 20, pageSizeOptions: [10, 20, 50, 100], showSizeChanger: true }}
              />
            ) : (
              <CatalogState
                kind="empty"
                description={t('apm.applications.noServices', '该应用还没有观测到服务。')}
                action={<Link href={`/apm/integration/add?application_id=${encodeURIComponent(application.application_id)}`}><Button type="primary">{t('apm.applications.addIngest', '添加接入')}</Button></Link>}
              />
            )}
          </ApmSurface>
        </div>
      ) : (
        <ApmSurface padding="none">
          <CatalogState kind={state === 'ready' ? 'error' : state} />
        </ApmSurface>
      )}
    </ApmRouteShell>
  );
}
