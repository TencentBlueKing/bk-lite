'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Table, type TableColumnsType } from 'antd';
import dayjs from 'dayjs';
import useApmApi from '@/app/apm/api';
import ApmRouteShell from '@/app/apm/components/apm-route-shell';
import CatalogState, {
  catalogErrorKind,
  type CatalogStateKind,
} from '@/app/apm/components/catalog-state';
import ApmStatusTag from '@/app/apm/components/status-tag';
import type { ApmEnvironmentView, ApmService } from '@/app/apm/types';

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

  const columns: TableColumnsType<ServiceEnvironmentRow> = [
    { title: '应用', dataIndex: 'namespace', render: (value) => value || '未归类应用' },
    { title: '服务', dataIndex: 'serviceName' },
    { title: '环境', dataIndex: 'environment', render: (value) => value || '未设置' },
    { title: '最近发现', dataIndex: 'last_seen_at', render: (value) => dayjs(value).format('YYYY-MM-DD HH:mm:ss') },
    { title: '状态', dataIndex: 'status', render: (value) => <ApmStatusTag status={value} /> },
    {
      title: '操作',
      key: 'action',
      render: (_, item) => (
        <Link href={`/apm/services/${item.serviceId}?environment=${encodeURIComponent(item.environment)}`}>
          <Button type="link">查看 RED</Button>
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
      <Alert
        className="mb-4"
        type="info"
        showIcon
        message="“全部环境”按环境逐行展示，不会把 production、testing 等环境的健康值混算。"
      />
      {catalogDegraded ? (
        <Alert
          className="mb-4"
          type="warning"
          showIcon
          message="目录对账暂时降级，当前列表可能不是最新状态。"
        />
      ) : null}
      {state === 'ready' && !rows.length ? (
        <CatalogState kind="empty" description="服务已发现，但尚无具有实例身份的环境视图。" />
      ) : state === 'ready' ? (
        <Table columns={columns} dataSource={rows} pagination={{ pageSize: 20 }} />
      ) : (
        <CatalogState kind={state} />
      )}
    </ApmRouteShell>
  );
}
