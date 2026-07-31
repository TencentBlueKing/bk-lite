'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { EyeOutlined, SearchOutlined } from '@ant-design/icons';
import { Alert, Button, Input, Select, Table, Tag, Typography, type TableColumnsType } from 'antd';
import dayjs from 'dayjs';
import useApmApi from '@/app/apm/api';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, {
  catalogErrorKind,
  type CatalogStateKind,
} from '@/app/apm/components/catalog-state';
import ServiceIdentity from '@/app/apm/components/service-identity';
import ApmStatusTag from '@/app/apm/components/status-tag';
import type { ApmEnvironmentView, ApmService, CatalogStatus } from '@/app/apm/types';

interface ServiceEnvironmentRow extends ApmEnvironmentView {
  key: string;
  serviceId: string;
  namespace: string;
  serviceName: string;
}

type PageState = CatalogStateKind | 'ready';

export default function ApmServicesPage() {
  const { getHealth, getServices, isLoading: authLoading } = useApmApi();
  const [services, setServices] = useState<ApmService[]>([]);
  const [catalogDegraded, setCatalogDegraded] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [environment, setEnvironment] = useState<string>();
  const [status, setStatus] = useState<CatalogStatus>();
  const [state, setState] = useState<PageState>('loading');

  useEffect(() => {
    if (authLoading) return;
    let active = true;
    Promise.all([
      getServices(),
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
  }, [authLoading, getHealth, getServices]);

  const rows = useMemo(
    () =>
      services.flatMap((service) =>
        service.environment_views.map((environment) => ({
          ...environment,
          key: `${service.id}:${environment.environment}`,
          serviceId: service.id,
          namespace: service.namespace,
          serviceName: service.name,
        }))
      ),
    [services]
  );

  const environmentOptions = useMemo(
    () => Array.from(new Set(rows.map((item) => item.environment)))
      .sort()
      .map((value) => ({ value, label: value || '未设置' })),
    [rows]
  );

  const filteredRows = useMemo(() => {
    const normalizedKeyword = keyword.trim().toLowerCase();
    return rows.filter((item) => {
      const matchesKeyword = !normalizedKeyword
        || `${item.namespace} ${item.serviceName}`.toLowerCase().includes(normalizedKeyword);
      return matchesKeyword
        && (environment === undefined || item.environment === environment)
        && (status === undefined || item.status === status);
    });
  }, [environment, keyword, rows, status]);

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
      title: '操作',
      key: 'action',
      width: 120,
      align: 'right',
      render: (_, item) => (
        <Link href={`/apm/services/${item.serviceId}?environment=${encodeURIComponent(item.environment)}`}>
          <Button type="link" size="small" icon={<EyeOutlined aria-hidden="true" />}>
            查看 RED
          </Button>
        </Link>
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
            <Input
              allowClear
              aria-label="按应用或服务名称搜索"
              className="min-w-56 flex-1 md:max-w-sm"
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
            <Select<CatalogStatus>
              allowClear
              aria-label="按服务状态筛选"
              className="w-36"
              placeholder="全部状态"
              value={status}
              options={[
                { value: 'active', label: '活跃' },
                { value: 'silent', label: '静默' },
                { value: 'archived', label: '已归档' },
              ]}
              onChange={setStatus}
            />
            <Typography.Text type="secondary" className="ml-auto text-xs tabular-nums">
              {filteredRows.length} 个环境视图 · {services.length} 个逻辑服务
            </Typography.Text>
          </div>
        </ApmSurface>
        <ApmSurface padding="none" className="overflow-hidden">
          {state === 'ready' && !rows.length ? (
            <CatalogState kind="empty" description="服务已发现，但尚无具有实例身份的环境视图。" />
          ) : state === 'ready' ? (
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
      </div>
    </ApmRouteShell>
  );
}
