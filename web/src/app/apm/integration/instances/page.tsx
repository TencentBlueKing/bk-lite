'use client';

import { useEffect, useMemo, useState } from 'react';
import { EditOutlined, InboxOutlined, SearchOutlined, UndoOutlined } from '@ant-design/icons';
import { Alert, Button, Input, message, Popconfirm, Radio, Select, Space, Table, Tag, Typography, type TableColumnsType } from 'antd';
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
import type { ApmApplication, ApmServiceInstance, CatalogStatus } from '@/app/apm/types';
import Permission from '@/components/permission';
import { useUserInfoContext } from '@/context/userInfo';
import { useTranslation } from '@/utils/i18n';

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
  const { t } = useTranslation();
  const {
    getApplications,
    getHealth,
    getInstancePage,
    setInstanceArchived,
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

  const setArchived = async (instance: ApmServiceInstance, archived: boolean) => {
    await setInstanceArchived(instance.id, archived);
    message.success(archived ? '实例已归档' : '实例已解档');
    setRefreshKey((value) => value + 1);
  };

  const applicationOptions = useMemo(() => applications.map((application) => ({
    value: application.application_id,
    label: `${application.name}（${application.application_id || '未归类'}）`,
  })), [applications]);

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
    { title: '应用', dataIndex: 'application_name', width: 140, responsive: ['xl'], render: (value, item) => value || item.application_id || '—' },
    {
      title: '接入时间',
      dataIndex: 'first_seen_at',
      width: 170,
      responsive: ['xl'],
      render: (value) => <span className="tabular-nums">{dayjs(value).format('YYYY-MM-DD HH:mm')}</span>,
    },
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
      render: (value: number[]) => value.map((id) => (
        <Tag bordered={false} key={id}>{groupNames.get(id) ?? `#${id}`}</Tag>
      )),
    },
    {
      title: '操作',
      key: 'action',
      width: 190,
      align: 'right',
      render: (_, item) => (
        <Permission requiredPermissions={['Operate']} permissionPath="/apm/integration/instances">
          <Space size={0}>
            {!item.archived_at ? (
              <Button
                type="link"
                size="small"
                icon={<EditOutlined aria-hidden="true" />}
                onClick={() => setOrganizationInstance(item)}
              >
                组织
              </Button>
            ) : null}
            <Popconfirm
              title={item.archived_at ? '确认解档实例？' : '确认归档实例？'}
              description={item.archived_at ? '解档后实例将重新出现在默认列表。' : '归档不会删除已经存储的遥测数据。'}
              okText={item.archived_at ? '解档' : '归档'}
              cancelText="取消"
              onConfirm={() => setArchived(item, !item.archived_at)}
            >
              <Button
                type="link"
                size="small"
                danger={!item.archived_at}
                icon={item.archived_at ? <UndoOutlined aria-hidden="true" /> : <InboxOutlined aria-hidden="true" />}
              >
                {item.archived_at ? '解档' : '归档'}
              </Button>
            </Popconfirm>
          </Space>
        </Permission>
      ),
    },
  ];

  return (
    <ApmRouteShell
      title="接入实例"
      description="查看由遥测数据自动发现的运行实例；服务健康度与 RED 指标请前往“服务”。"
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
      <div className="flex flex-col gap-3">
        <ApmSurface padding="compact">
          <div className="flex flex-wrap items-center gap-3">
            <Input.Search
              allowClear
              aria-label="按服务、应用或实例 ID 搜索"
              className="min-w-64 flex-1 md:max-w-sm"
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
            <Typography.Text type="secondary" className="ml-auto text-xs tabular-nums">
              已接入 {total} 个实例
            </Typography.Text>
            <Typography.Text type="secondary" className="basis-full text-xs">
              {t('apm.instances.defaultActiveHelp', '默认显示活跃实例；切换状态或时间范围可查看静默、归档与历史实例。')}
            </Typography.Text>
          </div>
        </ApmSurface>
        <ApmSurface padding="none" className="overflow-hidden">
          {state === 'ready' ? (
            <Table
              rowKey="id"
              columns={columns}
              dataSource={instances}
              pagination={{
                current: page,
                pageSize,
                total,
                pageSizeOptions: [10, 20, 50, 100],
                showSizeChanger: true,
                showTotal: (total) => `共 ${total} 条`,
              }}
              onChange={(pagination) => {
                setPage(pagination.current ?? 1);
                setPageSize(pagination.pageSize ?? 20);
              }}
            />
          ) : (
            <CatalogState kind={state} />
          )}
        </ApmSurface>
      </div>
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
