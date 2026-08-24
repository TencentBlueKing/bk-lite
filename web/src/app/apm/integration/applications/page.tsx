'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { AppstoreAddOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons';
import { Button, Drawer, Form, Input, message, Space, type TableColumnsType } from 'antd';
import useApmApi from '@/app/apm/api';
import ApmDataTable, { APM_TABLE_COLUMN_WIDTHS } from '@/app/apm/components/apm-data-table';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import { formatDateTime } from '@/app/apm/components/metric-format';
import type { ApmApplication, ApmApplicationInput } from '@/app/apm/types';
import FilterToolbar from '@/components/filter-toolbar';
import GroupTreeSelect from '@/components/group-tree-select';
import Permission from '@/components/permission';
import { useUserInfoContext } from '@/context/userInfo';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { useTranslation } from '@/utils/i18n';

type PageState = CatalogStateKind | 'ready';

export default function ApmApplicationsPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const [messageApi, messageContextHolder] = message.useMessage();
  const { getApplications, createApplication, updateApplication, isLoading } = useApmApi();
  const { flatGroups } = useUserInfoContext();
  const [form] = Form.useForm<ApmApplicationInput>();
  const [applications, setApplications] = useState<ApmApplication[]>([]);
  const [editing, setEditing] = useState<ApmApplication | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [state, setState] = useState<PageState>('loading');

  const groupNames = useMemo(
    () => new Map(flatGroups.map((group) => [Number(group.id), group.name])),
    [flatGroups]
  );

  const load = useCallback(async () => {
    if (isLoading) return;
    setState('loading');
    try {
      const items = await getApplications();
      const visible = items.filter((item) => !item.is_builtin);
      setApplications(visible);
      setState(visible.length ? 'ready' : 'empty');
    } catch (error) {
      setState(catalogErrorKind(error));
    }
  }, [getApplications, isLoading]);

  useEffect(() => { void load(); }, [load]);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ name: '', application_id: '', description: '', organization_ids: [] });
    setDrawerOpen(true);
  };

  const openEdit = (application: ApmApplication) => {
    setEditing(application);
    form.resetFields();
    form.setFieldsValue({
      name: application.name,
      description: application.description,
      organization_ids: application.organization_ids,
    });
    setDrawerOpen(true);
  };

  const submit = async (values: ApmApplicationInput) => {
    setSubmitting(true);
    try {
      if (editing) {
        await updateApplication(editing.id, values);
        messageApi.success(t('apm.applications.updated', '应用已更新'));
      } else {
        await createApplication(values);
        messageApi.success(t('apm.applications.created', '应用已创建'));
      }
      setDrawerOpen(false);
      await load();
    } finally {
      setSubmitting(false);
    }
  };

  const filtered = useMemo(() => {
    const value = keyword.trim().toLowerCase();
    return value
      ? applications.filter((item) => `${item.application_id} ${item.name} ${item.description}`.toLowerCase().includes(value))
      : applications;
  }, [applications, keyword]);
  const pageRows = useMemo(
    () => filtered.slice((page - 1) * pageSize, page * pageSize),
    [filtered, page, pageSize],
  );

  const columns: TableColumnsType<ApmApplication> = [
    {
      title: t('apm.applications.name', '应用'),
      key: 'application',
      render: (_, item) => (
        <div className="flex items-center gap-3">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[var(--color-primary-bg-active)] text-[var(--color-primary)]">
            <AppstoreAddOutlined aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <Link href={`/apm/integration/applications/${item.id}`} className="font-medium text-[var(--color-primary)] hover:underline">
              {item.name}
            </Link>
            {item.application_id && item.application_id !== item.name ? (
              <EllipsisWithTooltip className="truncate font-mono text-xs text-[var(--color-text-3)]" text={item.application_id} />
            ) : null}
          </div>
        </div>
      ),
    },
    { title: t('apm.applications.note', '说明'), dataIndex: 'description', responsive: ['lg'], render: (value) => <EllipsisWithTooltip className="truncate" text={value || '—'} /> },
    { title: t('apm.applications.serviceCount', '服务数'), dataIndex: 'service_count', width: APM_TABLE_COLUMN_WIDTHS.status, align: 'right', className: 'tabular-nums', responsive: ['md'] },
    {
      title: t('apm.common.organization', '组织'), dataIndex: 'organization_ids', width: APM_TABLE_COLUMN_WIDTHS.organization, responsive: ['xl'],
      render: (values: number[]) => (
        <EllipsisWithTooltip
          className="truncate"
          text={values.map((id) => groupNames.get(id) ?? `#${id}`).join('、') || '—'}
        />
      ),
    },
    { title: t('apm.applications.updatedAt', '更新时间'), dataIndex: 'updated_at', width: APM_TABLE_COLUMN_WIDTHS.timestamp, responsive: ['xxl'], className: 'tabular-nums', render: (value) => formatDateTime(value, false) },
    {
      title: t('apm.common.operation', '操作'), key: 'action', width: APM_TABLE_COLUMN_WIDTHS.actionGroup, align: 'right', fixed: 'right',
      render: (_, item) => (
        <Permission requiredPermissions={['Operate']} permissionPath="/apm/integration/applications">
          <Space className="whitespace-nowrap" size={8}>
            <Button
              className="!px-0"
              size="small"
              type="link"
              onClick={() => router.push(`/apm/integration/add?application_id=${encodeURIComponent(item.application_id)}`)}
            >
              {t('apm.applications.addIngest', '添加接入')}
            </Button>
            <Button
              className="!px-0"
              size="small"
              type="link"
              onClick={() => router.push(`/apm/integration/applications/${item.id}`)}
            >
              {t('apm.applications.viewDetail', '查看详情')}
            </Button>
            <Button className="!px-0" size="small" type="link" onClick={() => openEdit(item)}>
              {t('common.edit', '编辑')}
            </Button>
          </Space>
        </Permission>
      ),
    },
  ];

  return (
    <ApmRouteShell title={t('apm.applications.title', '应用管理')} description={t('apm.applications.description', '维护 APM 应用边界，并从对应应用发起遥测接入。')}>
      {messageContextHolder}
      <ApmSurface>
        <div className="flex flex-col gap-4">
          <FilterToolbar align="start" spacing="flush" className="w-full" contentClassName="w-full">
            <Input allowClear className="min-w-0 flex-1 md:max-w-sm" prefix={<SearchOutlined aria-hidden="true" />} placeholder={t('apm.applications.searchPlaceholder', '搜索应用 ID / 名称')} value={keyword} onChange={(event) => { setKeyword(event.target.value); setPage(1); }} />
            <Permission className="ml-auto" requiredPermissions={['Operate']} permissionPath="/apm/integration/applications">
              <Button type="primary" icon={<PlusOutlined aria-hidden="true" />} onClick={openCreate}>{t('apm.applications.create', '创建应用')}</Button>
            </Permission>
          </FilterToolbar>
          {state === 'ready' ? (
            <ApmDataTable
              rowKey="id"
              columns={columns}
              dataSource={pageRows}
              headerAlignment="column"
              pagination={{
                current: page,
                pageSize,
                total: filtered.length,
                pageSizeOptions: [10, 20, 50, 100],
                showSizeChanger: true,
                onChange: (nextPage, nextPageSize) => {
                  setPage(nextPageSize === pageSize ? nextPage : 1);
                  setPageSize(nextPageSize);
                },
              }}
            />
          ) : <CatalogState kind={state} onRetry={state === 'forbidden' ? undefined : () => void load()} />}
        </div>
      </ApmSurface>

      <Drawer
        destroyOnHidden
        open={drawerOpen}
        title={editing ? t('apm.applications.edit', '编辑应用') : t('apm.applications.create', '创建应用')}
        width="min(480px, 100vw)"
        styles={{ body: { overflowY: 'auto' } }}
        footer={(
          <Space className="flex w-full justify-end">
            <Button disabled={submitting} onClick={() => setDrawerOpen(false)}>{t('common.cancel', '取消')}</Button>
            <Button form="apm-application-form" htmlType="submit" loading={submitting} type="primary">
              {editing ? t('common.save', '保存') : t('common.create', '创建')}
            </Button>
          </Space>
        )}
        onClose={() => setDrawerOpen(false)}
      >
        <Form<ApmApplicationInput>
          form={form}
          id="apm-application-form"
          layout="vertical"
          preserve={false}
          requiredMark="optional"
          onFinish={(values) => void submit(values)}
        >
          <Form.Item name="application_id" label={t('apm.applications.id', '应用 ID')} extra={t('apm.applications.idHint', '创建后不可修改，将作为 service.namespace。')} rules={editing ? [] : [{ required: true, message: t('apm.applications.idRequired', '请输入应用 ID') }, { pattern: /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/, message: t('apm.applications.idPattern', '仅支持字母、数字、点、下划线和连字符') }]} hidden={Boolean(editing)}>
            <Input placeholder={t('apm.applications.idPlaceholder', '例如 shop')} autoComplete="off" />
          </Form.Item>
          <Form.Item name="name" label={t('apm.applications.nameLabel', '应用名称')} rules={[{ required: true, whitespace: true, message: t('apm.applications.nameRequired', '请输入应用名称') }, { max: 128 }]}>
            <Input placeholder={t('apm.applications.namePlaceholder', '例如 电商主站')} />
          </Form.Item>
          <Form.Item name="description" label={t('apm.applications.noteLabel', '应用说明')} rules={[{ max: 512 }]}>
            <Input.TextArea rows={3} maxLength={512} showCount placeholder={t('apm.applications.notePlaceholder', '说明业务范围或负责人（可选）')} />
          </Form.Item>
          <Form.Item name="organization_ids" label={t('apm.common.organization', '组织')} rules={[{ required: true, type: 'array', min: 1, message: t('apm.applications.orgRequired', '至少选择一个组织') }]}>
            <GroupTreeSelect multiple mode="ownership" showSearch placeholder={t('apm.applications.orgPlaceholder', '选择可管理此应用的组织')} />
          </Form.Item>
        </Form>
      </Drawer>
    </ApmRouteShell>
  );
}
