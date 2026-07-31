'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { EditOutlined, EyeOutlined, InboxOutlined, SearchOutlined, UndoOutlined } from '@ant-design/icons';
import { Alert, Button, Input, message, Popconfirm, Select, Space, Table, Tag, Typography, type TableColumnsType } from 'antd';
import dayjs from 'dayjs';
import useApmApi from '@/app/apm/api';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, {
  catalogErrorKind,
  type CatalogStateKind,
} from '@/app/apm/components/catalog-state';
import OrganizationAssignmentModal from '@/app/apm/components/organization-assignment-modal';
import ServiceIdentity from '@/app/apm/components/service-identity';
import ApmStatusTag from '@/app/apm/components/status-tag';
import type { ApmEnvironmentView, ApmService, CatalogStatus } from '@/app/apm/types';
import Permission from '@/components/permission';
import { useUserInfoContext } from '@/context/userInfo';

interface ServiceEnvironmentRow extends ApmEnvironmentView {
  key: string;
  serviceId: string;
  namespace: string;
  serviceName: string;
  serviceOrganizationIds: number[];
  serviceArchivedAt: string | null;
}

type PageState = CatalogStateKind | 'ready';

export default function ApmServicesPage() {
  const {
    getHealth,
    getServices,
    setServiceArchived,
    setServiceOrganizations,
    isLoading: authLoading,
  } = useApmApi();
  const { flatGroups } = useUserInfoContext();
  const [services, setServices] = useState<ApmService[]>([]);
  const [catalogDegraded, setCatalogDegraded] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [environment, setEnvironment] = useState<string>();
  const [status, setStatus] = useState<CatalogStatus>();
  const [state, setState] = useState<PageState>('loading');
  const [refreshKey, setRefreshKey] = useState(0);
  const [organizationService, setOrganizationService] = useState<ApmService | null>(null);
  const [organizationSubmitting, setOrganizationSubmitting] = useState(false);

  const groupNames = useMemo(
    () => new Map(flatGroups.map((group) => [Number(group.id), group.name])),
    [flatGroups]
  );

  useEffect(() => {
    if (authLoading) return;
    let active = true;
    setState('loading');
    Promise.all([
      getServices({ include_archived: status === 'archived' }),
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
  }, [authLoading, getHealth, getServices, refreshKey, status]);

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

  const rows = useMemo(
    () =>
      services.flatMap((service) => {
        const environmentViews = service.environment_views.length
          ? service.environment_views
          : [{ environment: '', last_seen_at: service.last_seen_at, status: service.status }];
        return environmentViews.map((environment) => ({
          ...environment,
          status: service.archived_at ? 'archived' as const : environment.status,
          key: `${service.id}:${environment.environment}`,
          serviceId: service.id,
          namespace: service.namespace,
          serviceName: service.name,
          serviceOrganizationIds: service.organization_ids,
          serviceArchivedAt: service.archived_at,
        }));
      }),
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
      title: '组织',
      dataIndex: 'serviceOrganizationIds',
      width: 140,
      responsive: ['xl'],
      render: (value: number[]) => value.map((id) => (
        <Tag bordered={false} key={id}>{groupNames.get(id) ?? `#${id}`}</Tag>
      )),
    },
    {
      title: '操作',
      key: 'action',
      width: 300,
      align: 'right',
      render: (_, item) => (
        <Space size={0}>
          {item.environment ? (
            <Link href={`/apm/services/${item.serviceId}?environment=${encodeURIComponent(item.environment)}`}>
              <Button type="link" size="small" icon={<EyeOutlined aria-hidden="true" />}>
                查看 RED
              </Button>
            </Link>
          ) : (
            <Button type="link" size="small" disabled title="收到带环境与实例身份的 Span 后可查询 RED">
              待实例身份
            </Button>
          )}
          <Permission requiredPermissions={['Operate']} permissionPath="/apm/services">
            <Space size={0}>
              {!item.serviceArchivedAt ? (
                <Button
                  type="link"
                  size="small"
                  icon={<EditOutlined aria-hidden="true" />}
                  onClick={() => setOrganizationService(services.find((service) => service.id === item.serviceId) ?? null)}
                >
                  组织
                </Button>
              ) : null}
              <Popconfirm
                title={item.serviceArchivedAt ? '确认解档服务？' : '确认归档服务？'}
                description={item.serviceArchivedAt ? '解档后服务将重新出现在默认目录。' : '归档不会删除 Trace 或指标数据。'}
                okText={item.serviceArchivedAt ? '解档' : '归档'}
                cancelText="取消"
                onConfirm={() => setArchived(item.serviceId, !item.serviceArchivedAt)}
              >
                <Button
                  type="link"
                  size="small"
                  danger={!item.serviceArchivedAt}
                  icon={item.serviceArchivedAt ? <UndoOutlined aria-hidden="true" /> : <InboxOutlined aria-hidden="true" />}
                >
                  {item.serviceArchivedAt ? '解档' : '归档'}
                </Button>
              </Popconfirm>
            </Space>
          </Permission>
        </Space>
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
          {state === 'ready' ? (
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
      <OrganizationAssignmentModal
        open={Boolean(organizationService)}
        title={`调整服务组织${organizationService ? `：${organizationService.namespace}/${organizationService.name}` : ''}`}
        organizationIds={organizationService?.organization_ids ?? []}
        submitting={organizationSubmitting}
        description="服务组织独立于接入源与实例，仅影响此逻辑服务的可见和可操作范围。"
        onCancel={() => setOrganizationService(null)}
        onSubmit={submitOrganizations}
      />
    </ApmRouteShell>
  );
}
