'use client';

import { useEffect, useMemo, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { ReloadOutlined } from '@ant-design/icons';
import { Button, Segmented, Select, Tag, Typography, type TableColumnsType } from 'antd';
import useApmApi from '@/app/apm/api';
import ApmDataTable, { APM_TABLE_COLUMN_WIDTHS } from '@/app/apm/components/apm-data-table';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import { DEPLOYMENT_STATUS_META } from '@/app/apm/components/deployment-status';
import { StatusPill } from '@/app/apm/components/home/section-card';
import { formatDateTime, formatRelativeTime } from '@/app/apm/components/metric-format';
import type { ApmDeploymentEvent, ApmDeploymentStatus, ApmService } from '@/app/apm/types';
import CompactEmptyState from '@/components/compact-empty-state';
import FilterToolbar from '@/components/filter-toolbar';
import { useTranslation } from '@/utils/i18n';

type PageState = CatalogStateKind | 'ready';
type StatusFilter = ApmDeploymentStatus | 'all';

const STATUS_VALUES: ApmDeploymentStatus[] = ['success', 'in_progress', 'rollback', 'failed'];

function isStatusFilter(value: string | null): value is StatusFilter {
  return value === 'all' || STATUS_VALUES.includes(value as ApmDeploymentStatus);
}

export default function ApmDeploymentsPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { getDeployments, getServices, isLoading: authLoading } = useApmApi();
  const [rows, setRows] = useState<ApmDeploymentEvent[]>([]);
  const [services, setServices] = useState<ApmService[]>([]);
  const [total, setTotal] = useState(0);
  const [state, setState] = useState<PageState>('loading');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [serviceId, setServiceId] = useState(searchParams.get('service_id') ?? '');
  const [environment, setEnvironment] = useState(searchParams.get('environment') ?? '');
  const [status, setStatus] = useState<StatusFilter>(() => {
    const value = searchParams.get('status');
    return isStatusFilter(value) ? value : 'all';
  });
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    const params = new URLSearchParams();
    if (serviceId) params.set('service_id', serviceId);
    if (environment) params.set('environment', environment);
    if (status !== 'all') params.set('status', status);
    const next = params.toString();
    const current = searchParams.toString();
    if (next === current) return;
    router.replace(next ? `${pathname}?${next}` : pathname, { scroll: false });
  }, [environment, pathname, router, searchParams, serviceId, status]);

  useEffect(() => {
    if (authLoading) return;
    let active = true;
    setState('loading');
    Promise.all([
      getDeployments({
        page,
        page_size: pageSize,
        service_id: serviceId || undefined,
        environment: environment || undefined,
        status: status === 'all' ? undefined : status,
      }),
      getServices(),
    ])
      .then(([result, serviceItems]) => {
        if (!active) return;
        setRows(result.items);
        setTotal(result.count);
        setServices(serviceItems);
        setState(result.items.length ? 'ready' : 'empty');
      })
      .catch((error) => {
        if (active) setState(catalogErrorKind(error));
      });
    return () => {
      active = false;
    };
  }, [authLoading, environment, getDeployments, getServices, page, pageSize, refreshKey, serviceId, status]);

  const serviceOptions = useMemo(
    () => services.map((service) => ({
      value: service.id,
      label: service.namespace ? `${service.namespace} / ${service.name}` : service.name,
    })),
    [services],
  );
  const environmentOptions = useMemo(
    () => Array.from(new Set(
      services.flatMap((service) => service.environment_views.map((view) => view.environment).filter(Boolean)),
    )).sort().map((value) => ({ value, label: value })),
    [services],
  );

  const columns: TableColumnsType<ApmDeploymentEvent> = [
    {
      title: t('apm.common.service', '服务'),
      dataIndex: 'service_name',
      render: (_, row) => (
        <Link
          href={`/apm/services/${row.service_id}`}
          className="truncate text-[var(--color-text-1)] hover:text-[var(--color-primary)]"
        >
          {row.service_namespace ? `${row.service_namespace} / ${row.service_name}` : row.service_name}
        </Link>
      ),
    },
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
      responsive: ['sm'],
      render: (value: string) => value || t('apm.common.unset', '未设置'),
    },
    {
      title: t('apm.deployments.deployedAt', '发布时间'),
      dataIndex: 'deployed_at',
      width: APM_TABLE_COLUMN_WIDTHS.relativeTime,
      responsive: ['md'],
      render: (value: string) => (
        <span className="tabular-nums" title={formatDateTime(value)}>
          {formatRelativeTime(value, t)}
        </span>
      ),
    },
    {
      title: t('apm.deployments.deployedBy', '部署人'),
      dataIndex: 'deployed_by',
      width: APM_TABLE_COLUMN_WIDTHS.metric,
      responsive: ['lg'],
      render: (value: string) => value || '—',
    },
    {
      title: t('apm.common.status', '状态'),
      dataIndex: 'status',
      width: APM_TABLE_COLUMN_WIDTHS.status,
      render: (value: ApmDeploymentStatus) => {
        const meta = DEPLOYMENT_STATUS_META[value] ?? DEPLOYMENT_STATUS_META.success;
        return <StatusPill label={t(meta.labelKey, meta.fallback)} tone={meta.tone} />;
      },
    },
    {
      title: t('apm.deployments.source', '来源'),
      dataIndex: 'source',
      width: APM_TABLE_COLUMN_WIDTHS.status,
      responsive: ['xl'],
      render: (value: ApmDeploymentEvent['source']) => (
        <Tag bordered={false}>
          {value === 'reported'
            ? t('apm.deployments.sourceReported', '上报')
            : t('apm.deployments.sourceInferred', '推断')}
        </Tag>
      ),
    },
  ];

  const content = state === 'ready' ? (
    <ApmDataTable
      columns={columns}
      dataSource={rows}
      pagination={{
        current: page,
        pageSize,
        total,
        pageSizeOptions: [10, 20, 50, 100],
        showSizeChanger: true,
        onChange: (nextPage, nextPageSize) => {
          setPage(nextPageSize === pageSize ? nextPage : 1);
          setPageSize(nextPageSize);
        },
      }}
      rowKey="id"
    />
  ) : state === 'empty' ? (
    <CompactEmptyState description={t('apm.deployments.empty', '暂无部署事件')} />
  ) : (
    <CatalogState kind={state} onRetry={state === 'forbidden' ? undefined : () => setRefreshKey((value) => value + 1)} />
  );

  return (
    <ApmRouteShell
      dependency="metadata"
      description={t('apm.deployments.description', '发布由遥测 service.version 推断；接入 CI/CD 上报后将补充部署人与失败状态。')}
      title={t('apm.deployments.title', '部署')}
    >
      <ApmSurface>
        <div className="flex flex-col gap-4">
          <FilterToolbar align="start" spacing="flush" className="w-full" contentClassName="w-full flex-wrap">
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              className="min-w-40"
              placeholder={t('apm.common.allServices', '全部服务')}
              value={serviceId || undefined}
              options={serviceOptions}
              onChange={(value) => {
                setServiceId(value ?? '');
                setPage(1);
              }}
            />
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              className="min-w-32"
              placeholder={t('apm.common.allEnvironments', '全部环境')}
              value={environment || undefined}
              options={environmentOptions}
              onChange={(value) => {
                setEnvironment(value ?? '');
                setPage(1);
              }}
            />
            <Segmented<StatusFilter>
              aria-label={t('apm.common.status', '状态')}
              value={status}
              options={[
                { label: t('apm.common.allStatuses', '全部状态'), value: 'all' },
                { label: t('apm.home.releaseSuccess', '成功'), value: 'success' },
                { label: t('apm.home.releaseInProgress', '进行中'), value: 'in_progress' },
                { label: t('apm.home.releaseRollback', '回滚'), value: 'rollback' },
                { label: t('apm.home.releaseFailed', '失败'), value: 'failed' },
              ]}
              onChange={(value) => {
                setStatus(value);
                setPage(1);
              }}
            />
            <Button
              aria-label={t('apm.deployments.refresh', '刷新部署事件')}
              className="ml-auto"
              icon={<ReloadOutlined aria-hidden="true" />}
              loading={state === 'loading'}
              onClick={() => setRefreshKey((value) => value + 1)}
            />
          </FilterToolbar>
          <Typography.Text type="secondary">
            {t('apm.deployments.description', '发布由遥测 service.version 推断；接入 CI/CD 上报后将补充部署人与失败状态。')}
          </Typography.Text>
          {content}
        </div>
      </ApmSurface>
    </ApmRouteShell>
  );
}
