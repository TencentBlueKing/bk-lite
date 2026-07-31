'use client';

import { useEffect, useState } from 'react';
import { Alert, Select, Table, type TableColumnsType } from 'antd';
import dayjs from 'dayjs';
import useApmApi from '@/app/apm/api';
import ApmRouteShell from '@/app/apm/components/apm-route-shell';
import CatalogState, {
  catalogErrorKind,
  type CatalogStateKind,
} from '@/app/apm/components/catalog-state';
import ApmStatusTag from '@/app/apm/components/status-tag';
import type { ApmServiceInstance, CatalogStatus } from '@/app/apm/types';

type PageState = CatalogStateKind | 'ready';

export default function ApmIntegrationInstancesPage() {
  const { getHealth, getIngestSources, getInstances, isLoading: authLoading } = useApmApi();
  const [instances, setInstances] = useState<ApmServiceInstance[]>([]);
  const [hasMissingIdentity, setHasMissingIdentity] = useState(false);
  const [catalogDegraded, setCatalogDegraded] = useState(false);
  const [status, setStatus] = useState<CatalogStatus | undefined>();
  const [state, setState] = useState<PageState>('loading');

  useEffect(() => {
    if (authLoading) return;
    let active = true;
    setState('loading');
    Promise.all([
      getInstances({ status, include_archived: status === 'archived' }),
      getIngestSources(),
      getHealth().catch(() => ({ catalog_reconcile: { status: 'degraded' as const } })),
    ])
      .then(([items, sources, health]) => {
        if (!active) return;
        setInstances(items);
        setHasMissingIdentity(sources.some((source) => source.missing_instance_identity));
        setCatalogDegraded(health.catalog_reconcile.status === 'degraded');
        setState(items.length ? 'ready' : 'empty');
      })
      .catch((error) => {
        if (active) setState(catalogErrorKind(error));
      });
    return () => {
      active = false;
    };
  }, [authLoading, getHealth, getIngestSources, getInstances, status]);

  const columns: TableColumnsType<ApmServiceInstance> = [
    {
      title: '服务',
      key: 'service',
      render: (_, item) => `${item.service_namespace || '未归类应用'} / ${item.service_name}`,
    },
    { title: '环境', dataIndex: 'environment', render: (value) => value || '未设置' },
    { title: '实例 ID', dataIndex: 'instance_id', ellipsis: true },
    { title: '版本', dataIndex: 'version', render: (value) => value || '—' },
    { title: '接入方式', dataIndex: 'ingest_source_name' },
    { title: '最近上报', dataIndex: 'last_seen_at', render: (value) => dayjs(value).format('YYYY-MM-DD HH:mm:ss') },
    { title: '状态', dataIndex: 'status', render: (value: CatalogStatus) => <ApmStatusTag status={value} /> },
    { title: '组织', dataIndex: 'organization_ids', render: (value: number[]) => value.join(', ') },
  ];

  return (
    <ApmRouteShell
      title="接入实例"
      description="按 service.instance.id 查看每一个实际上报的运行实例及其组织范围。"
    >
      <Alert
        className="mb-4"
        type="info"
        showIcon
        message="目录由运行期任务每分钟幂等对账；新实例通常在 1–2 分钟内出现。"
      />
      {hasMissingIdentity ? (
        <Alert
          className="mb-4"
          type="warning"
          showIcon
          message="检测到最近 15 分钟内缺少 service.instance.id 的 Span"
          description="这些 Span 仍参与服务级指标，但不会创建虚假的接入实例。请按接入片段配置动态实例 ID。"
        />
      ) : null}
      {catalogDegraded ? (
        <Alert
          className="mb-4"
          type="warning"
          showIcon
          message="目录对账暂时降级"
          description="下方是最近一次成功对账后的元数据，可能落后于 Trace 与指标存储。"
        />
      ) : null}
      <Select
        className="mb-4 w-40"
        allowClear
        placeholder="全部状态"
        value={status}
        onChange={setStatus}
        options={[
          { value: 'active', label: '活跃' },
          { value: 'silent', label: '静默' },
          { value: 'archived', label: '已归档' },
        ]}
      />
      {state === 'ready' ? (
        <Table rowKey="id" columns={columns} dataSource={instances} pagination={{ pageSize: 20 }} />
      ) : (
        <CatalogState kind={state} />
      )}
    </ApmRouteShell>
  );
}
