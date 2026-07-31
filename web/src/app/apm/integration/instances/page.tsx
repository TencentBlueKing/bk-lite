'use client';

import { useEffect, useMemo, useState } from 'react';
import { SearchOutlined } from '@ant-design/icons';
import { Alert, Input, Select, Table, Tag, Typography, type TableColumnsType } from 'antd';
import dayjs from 'dayjs';
import useApmApi from '@/app/apm/api';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, {
  catalogErrorKind,
  type CatalogStateKind,
} from '@/app/apm/components/catalog-state';
import ServiceIdentity from '@/app/apm/components/service-identity';
import ApmStatusTag from '@/app/apm/components/status-tag';
import type { ApmServiceInstance, CatalogStatus } from '@/app/apm/types';

type PageState = CatalogStateKind | 'ready';

export default function ApmIntegrationInstancesPage() {
  const { getHealth, getIngestSources, getInstances, isLoading: authLoading } = useApmApi();
  const [instances, setInstances] = useState<ApmServiceInstance[]>([]);
  const [hasMissingIdentity, setHasMissingIdentity] = useState(false);
  const [catalogDegraded, setCatalogDegraded] = useState(false);
  const [status, setStatus] = useState<CatalogStatus | undefined>();
  const [keyword, setKeyword] = useState('');
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

  const filteredInstances = useMemo(() => {
    const normalizedKeyword = keyword.trim().toLowerCase();
    if (!normalizedKeyword) return instances;
    return instances.filter((item) => (
      `${item.service_namespace} ${item.service_name} ${item.instance_id}`
        .toLowerCase()
        .includes(normalizedKeyword)
    ));
  }, [instances, keyword]);

  const columns: TableColumnsType<ApmServiceInstance> = [
    {
      title: '服务',
      key: 'service',
      render: (_, item) => (
        <ServiceIdentity namespace={item.service_namespace} name={item.service_name} />
      ),
    },
    { title: '环境', dataIndex: 'environment', width: 120, responsive: ['sm'], render: (value) => <Tag bordered={false}>{value || '未设置'}</Tag> },
    {
      title: '实例 ID',
      dataIndex: 'instance_id',
      render: (value) => <Typography.Text ellipsis className="block max-w-56 font-mono text-xs">{value}</Typography.Text>,
    },
    { title: '版本', dataIndex: 'version', width: 100, responsive: ['lg'], render: (value) => value || '—' },
    { title: '接入源', dataIndex: 'ingest_source_name', width: 140, responsive: ['xl'] },
    {
      title: '最近上报',
      dataIndex: 'last_seen_at',
      width: 190,
      responsive: ['md'],
      render: (value) => <span className="tabular-nums">{dayjs(value).format('YYYY-MM-DD HH:mm:ss')}</span>,
    },
    { title: '状态', dataIndex: 'status', width: 100, render: (value: CatalogStatus) => <ApmStatusTag status={value} /> },
    {
      title: '组织',
      dataIndex: 'organization_ids',
      width: 120,
      responsive: ['xl'],
      render: (value: number[]) => value.map((id) => <Tag bordered={false} key={id}>#{id}</Tag>),
    },
  ];

  return (
    <ApmRouteShell
      title="接入实例"
      description="按 service.instance.id 查看每一个实际上报的运行实例及其组织范围。"
    >
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
      <div className="flex flex-col gap-3">
        <ApmSurface padding="compact">
          <div className="flex flex-wrap items-center gap-3">
            <Input
              allowClear
              aria-label="按服务、应用或实例 ID 搜索"
              className="min-w-64 flex-1 md:max-w-sm"
              prefix={<SearchOutlined className="text-[var(--color-text-4)]" aria-hidden="true" />}
              placeholder="搜索服务、应用或实例 ID"
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
            />
            <Select<CatalogStatus>
              className="w-40"
              allowClear
              aria-label="按实例状态筛选"
              placeholder="全部状态"
              value={status}
              onChange={setStatus}
              options={[
                { value: 'active', label: '活跃' },
                { value: 'silent', label: '静默' },
                { value: 'archived', label: '已归档' },
              ]}
            />
            <Typography.Text type="secondary" className="ml-auto text-xs tabular-nums">
              已接入 {filteredInstances.length} 个实例
            </Typography.Text>
          </div>
        </ApmSurface>
        <ApmSurface padding="none" className="overflow-hidden">
          {state === 'ready' ? (
            <Table
              rowKey="id"
              columns={columns}
              dataSource={filteredInstances}
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
