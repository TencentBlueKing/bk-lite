'use client';

import { useEffect, useMemo, useState } from 'react';
import { SearchOutlined } from '@ant-design/icons';
import { Alert, Button, Input, message, Radio, Select, Tag, Typography, type TableColumnsType } from 'antd';
import dayjs from 'dayjs';
import useApmApi from '@/app/apm/api';
import ApmDataTable from '@/app/apm/components/apm-data-table';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, {
  catalogErrorKind,
  type CatalogStateKind,
} from '@/app/apm/components/catalog-state';
import OrganizationAssignmentModal from '@/app/apm/components/organization-assignment-modal';
import ServiceIdentity from '@/app/apm/components/service-identity';
import ApmStatusTag from '@/app/apm/components/status-tag';
import type { ApmApplication, ApmServiceInstance, CatalogStatus } from '@/app/apm/types';
import Permission from '@/components/permission';
import FilterToolbar from '@/components/filter-toolbar';
import { useUserInfoContext } from '@/context/userInfo';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';

type PageState = CatalogStateKind | 'ready';
type TimeRange = '15m' | '1h' | '4h' | '1d' | '7d' | '30d' | 'all';

const RANGE_UNITS: Record<Exclude<TimeRange, 'all'>, [number, dayjs.ManipulateType]> = {
  '15m': [15, 'minute'],
  '1h': [1, 'hour'],
  '4h': [4, 'hour'],
  '1d': [1, 'day'],
  '7d': [7, 'day'],
  '30d': [30, 'day'],
};

export default function ApmIntegrationInstancesPage() {
  const {
    getApplications,
    getHealth,
    getInstancePage,
    setInstanceOrganizations,
    isLoading: authLoading,
  } = useApmApi();
  const { flatGroups } = useUserInfoContext();
  const [instances, setInstances] = useState<ApmServiceInstance[]>([]);
  const [applications, setApplications] = useState<ApmApplication[]>([]);
  const [total, setTotal] = useState(0);
  const [catalogDegraded, setCatalogDegraded] = useState(false);
  const [status, setStatus] = useState<CatalogStatus | undefined>('active');
  const [keyword, setKeyword] = useState('');
  const [appliedKeyword, setAppliedKeyword] = useState('');
  const [applicationId, setApplicationId] = useState('all');
  const [environment, setEnvironment] = useState('');
  const [timeRange, setTimeRange] = useState<TimeRange>('1d');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [state, setState] = useState<PageState>('loading');
  const [refreshKey, setRefreshKey] = useState(0);
  const [organizationInstance, setOrganizationInstance] = useState<ApmServiceInstance | null>(null);
  const [organizationSubmitting, setOrganizationSubmitting] = useState(false);

  const groupNames = useMemo(
    () => new Map(flatGroups.map((group) => [Number(group.id), group.name])),
    [flatGroups]
  );

  useEffect(() => {
    if (authLoading) return;
    let active = true;
    setState('loading');
    const endedAt = dayjs();
    const range = timeRange === 'all' ? undefined : RANGE_UNITS[timeRange];
    const startedAt = range ? endedAt.subtract(range[0], range[1]) : undefined;
    Promise.all([
      getInstancePage({
        page,
        page_size: pageSize,
        application: applicationId === 'all' ? undefined : applicationId,
        environment: environment.trim() || undefined,
        status,
        include_archived: status === 'archived',
        started_at: startedAt?.toISOString(),
        ended_at: startedAt ? endedAt.toISOString() : undefined,
        keyword: appliedKeyword.trim() || undefined,
      }),
      getApplications(),
      getHealth().catch(() => ({ catalog_reconcile: { status: 'degraded' as const } })),
    ])
      .then(([result, applicationItems, health]) => {
        if (!active) return;
        setInstances(result.items);
        setApplications(applicationItems);
        setTotal(result.count);
        setCatalogDegraded(health.catalog_reconcile.status === 'degraded');
        setState(result.items.length ? 'ready' : 'empty');
      })
      .catch((error) => {
        if (active) setState(catalogErrorKind(error));
      });
    return () => {
      active = false;
    };
  }, [
    applicationId,
    appliedKeyword,
    authLoading,
    environment,
    getApplications,
    getHealth,
    getInstancePage,
    page,
    pageSize,
    refreshKey,
    status,
    timeRange,
  ]);

  const submitOrganizations = async (organizationIds: number[]) => {
    if (!organizationInstance) return;
    setOrganizationSubmitting(true);
    try {
      await setInstanceOrganizations(organizationInstance.id, organizationIds);
      message.success('实例组织已更新');
      setOrganizationInstance(null);
      setRefreshKey((value) => value + 1);
    } finally {
      setOrganizationSubmitting(false);
    }
  };

  const applicationOptions = useMemo(() => applications.map((application) => ({
    value: application.application_id,
    label: `${application.name}（${application.application_id || '未设置 ID'}）`,
  })), [applications]);

  const columns: TableColumnsType<ApmServiceInstance> = [
    {
      title: '实例 ID',
      dataIndex: 'instance_id',
      width: '13%',
      render: (value) => <EllipsisWithTooltip className="max-w-52 truncate font-mono text-xs" text={value} />,
    },
    {
      title: '服务',
      key: 'service',
      width: '18%',
      responsive: ['sm'],
      render: (_, item) => (
        <ServiceIdentity namespace={item.service_namespace} name={item.service_name} />
      ),
    },
    { title: '所属应用', dataIndex: 'application_name', width: '12%', responsive: ['xl'], render: (value, item) => <EllipsisWithTooltip className="truncate" text={value || item.application_id || '—'} /> },
    { title: '环境', dataIndex: 'environment', width: '7%', responsive: ['md'], render: (value) => <Tag bordered={false}>{value || '未设置'}</Tag> },
    { title: '版本', dataIndex: 'version', width: '6%', responsive: ['lg'], render: (value) => value || '—' },
    {
      title: '首次接入',
      dataIndex: 'first_seen_at',
      width: '11%',
      responsive: ['xxl'],
      render: (value) => (
        <time className="whitespace-nowrap tabular-nums" dateTime={value}>
          {dayjs(value).format('YYYY-MM-DD HH:mm')}
        </time>
      ),
    },
    {
      title: '最近上报',
      dataIndex: 'last_seen_at',
      width: '12%',
      responsive: ['md'],
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
    { title: '实例状态', dataIndex: 'status', width: '8%', align: 'center', render: (value: CatalogStatus) => <ApmStatusTag status={value} /> },
    {
      title: '所属组织',
      dataIndex: 'organization_ids',
      width: '7%',
      responsive: ['xxl'],
      render: (value: number[]) => (
        <EllipsisWithTooltip
          className="truncate text-xs"
          text={value.length ? value.map((id) => groupNames.get(id) ?? `#${id}`).join('、') : '未分配'}
        />
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 112,
      align: 'right',
      fixed: 'right',
      render: (_, item) => (
        <Permission requiredPermissions={['Operate']} permissionPath="/apm/integration/instances">
          {!item.archived_at ? (
            <Button className="!px-0" type="link" size="small" onClick={() => setOrganizationInstance(item)}>调整组织</Button>
          ) : <Typography.Text type="secondary" className="!text-xs">只读</Typography.Text>}
        </Permission>
      ),
    },
  ];

  return (
    <ApmRouteShell
      title="接入实例"
      description="按运行实例查看上报状态与组织归属；逻辑服务健康请前往服务目录。"
    >
      {catalogDegraded ? (
        <Alert
          className="mb-4"
          type="warning"
          showIcon
          message="目录对账暂时降级"
          description="下方是最近一次成功对账后的元数据，可能落后于 Trace 与指标存储。"
        />
      ) : null}
      <ApmSurface>
        <div className="flex flex-col gap-4">
          <FilterToolbar align="start" spacing="flush" className="w-full" contentClassName="w-full">
            <Input.Search
              allowClear
              aria-label="按服务、应用或实例 ID 搜索"
              className="min-w-0 flex-1 md:max-w-sm"
              prefix={<SearchOutlined className="text-[var(--color-text-4)]" aria-hidden="true" />}
              placeholder="搜索服务名 / 应用 / 实例 ID"
              value={keyword}
              onChange={(event) => {
                setKeyword(event.target.value);
                if (!event.target.value) {
                  setAppliedKeyword('');
                  setPage(1);
                }
              }}
              onSearch={(value) => {
                setAppliedKeyword(value);
                setPage(1);
              }}
            />
            <Select
              className="w-40"
              aria-label="按应用筛选"
              value={applicationId}
              options={[{ value: 'all', label: '全部应用' }, ...applicationOptions]}
              onChange={(value) => {
                setApplicationId(value);
                setPage(1);
              }}
            />
            <Input
              allowClear
              className="w-36"
              aria-label="按环境筛选"
              value={environment}
              placeholder="全部环境（输入精确值）"
              onChange={(event) => {
                setEnvironment(event.target.value);
                setPage(1);
              }}
            />
            <Select<CatalogStatus>
              className="w-40"
              allowClear
              aria-label="按实例状态筛选"
              placeholder="全部状态"
              value={status}
              onChange={(value) => {
                setStatus(value);
                setPage(1);
              }}
              options={[
                { value: 'active', label: '活跃' },
                { value: 'silent', label: '静默' },
                { value: 'archived', label: '已归档' },
              ]}
            />
            <Typography.Text type="secondary" className="ml-auto text-xs tabular-nums">
              已接入 {total} 个实例
            </Typography.Text>
            <Radio.Group
              aria-label="接入上报时间范围"
              buttonStyle="solid"
              size="small"
              value={timeRange}
              onChange={(event) => {
                setTimeRange(event.target.value);
                setPage(1);
              }}
            >
              {([...Object.keys(RANGE_UNITS), 'all'] as TimeRange[]).map((value) => (
                <Radio.Button key={value} value={value}>{value === 'all' ? '全部' : value}</Radio.Button>
              ))}
            </Radio.Group>
          </FilterToolbar>
          {state === 'ready' ? (
            <ApmDataTable
              rowKey="id"
              columns={columns}
              dataSource={instances}
              headerAlignment="column"
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
            />
          ) : state === 'empty' ? (
            <CatalogState
              kind="empty"
              description="当前条件下没有接入实例。"
              action={<Button onClick={() => {
                setKeyword('');
                setAppliedKeyword('');
                setApplicationId('all');
                setEnvironment('');
                setStatus('active');
                setTimeRange('1d');
                setPage(1);
              }}>清除筛选</Button>}
            />
          ) : (
            <CatalogState kind={state} onRetry={state === 'forbidden' ? undefined : () => setRefreshKey((value) => value + 1)} />
          )}
        </div>
      </ApmSurface>
      <OrganizationAssignmentModal
        open={Boolean(organizationInstance)}
        title={`调整实例组织${organizationInstance ? `：${organizationInstance.instance_id}` : ''}`}
        organizationIds={organizationInstance?.organization_ids ?? []}
        submitting={organizationSubmitting}
        description="保存后此实例转为自定义组织，不再自动继承应用后续的组织调整。"
        onCancel={() => setOrganizationInstance(null)}
        onSubmit={submitOrganizations}
      />
    </ApmRouteShell>
  );
}
