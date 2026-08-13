'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { AppstoreAddOutlined, EditOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons';
import { Button, Form, Input, message, Modal, Space, Typography, type TableColumnsType } from 'antd';
import dayjs from 'dayjs';
import useApmApi from '@/app/apm/api';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import type { ApmApplication, ApmApplicationInput } from '@/app/apm/types';
import FilterToolbar from '@/components/filter-toolbar';
import GroupTreeSelect from '@/components/group-tree-select';
import Permission from '@/components/permission';
import { useUserInfoContext } from '@/context/userInfo';
import CustomTable from '@/components/custom-table';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';

type PageState = CatalogStateKind | 'ready';

export default function ApmApplicationsPage() {
  const [messageApi, messageContextHolder] = message.useMessage();
  const { getApplications, createApplication, updateApplication, isLoading } = useApmApi();
  const { flatGroups } = useUserInfoContext();
  const [form] = Form.useForm<ApmApplicationInput>();
  const [applications, setApplications] = useState<ApmApplication[]>([]);
  const [editing, setEditing] = useState<ApmApplication | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
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
    setModalOpen(true);
  };

  const openEdit = (application: ApmApplication) => {
    setEditing(application);
    form.resetFields();
    form.setFieldsValue({
      name: application.name,
      description: application.description,
      organization_ids: application.organization_ids,
    });
    setModalOpen(true);
  };

  const submit = async () => {
    const values = await form.validateFields();
    setSubmitting(true);
    try {
      if (editing) {
        await updateApplication(editing.id, values);
        messageApi.success('应用已更新');
      } else {
        await createApplication(values);
        messageApi.success('应用已创建');
      }
      setModalOpen(false);
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
      title: '应用',
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
            <EllipsisWithTooltip className="truncate font-mono text-xs text-[var(--color-text-3)]" text={item.application_id} />
          </div>
        </div>
      ),
    },
    { title: '说明', dataIndex: 'description', responsive: ['md'], render: (value) => <EllipsisWithTooltip className="truncate" text={value || '—'} /> },
    { title: '服务数', dataIndex: 'service_count', width: 100, align: 'right', className: 'tabular-nums' },
    {
      title: '组织', dataIndex: 'organization_ids', width: 180, responsive: ['lg'],
      render: (values: number[]) => (
        <EllipsisWithTooltip
          className="truncate"
          text={values.map((id) => groupNames.get(id) ?? `#${id}`).join('、') || '—'}
        />
      ),
    },
    { title: '更新时间', dataIndex: 'updated_at', width: 170, responsive: ['xl'], className: 'tabular-nums', render: (value) => dayjs(value).format('YYYY-MM-DD HH:mm') },
    {
      title: '操作', key: 'action', width: 210, align: 'right', fixed: 'right',
      render: (_, item) => (
          <Permission requiredPermissions={['Operate']} permissionPath="/apm/integration/applications">
            <Space size={0}>
              <Link href={`/apm/integration/add?application_id=${encodeURIComponent(item.application_id)}`}>
                <Button type="link" size="small">添加接入</Button>
              </Link>
              <Link href={`/apm/integration/applications/${item.id}`}>
                <Button type="link" size="small">详情</Button>
              </Link>
              <Button type="link" size="small" icon={<EditOutlined aria-hidden="true" />} onClick={() => openEdit(item)}>编辑</Button>
            </Space>
          </Permission>
      ),
    },
  ];

  return (
    <ApmRouteShell title="应用管理" description="维护 APM 应用边界，并从对应应用发起遥测接入。">
      {messageContextHolder}
      <div className="flex flex-col gap-3">
        <ApmSurface padding="compact">
          <FilterToolbar align="start" spacing="flush" className="w-full" contentClassName="w-full">
            <Input allowClear className="min-w-0 flex-1 md:max-w-sm" prefix={<SearchOutlined aria-hidden="true" />} placeholder="搜索应用 ID / 名称" value={keyword} onChange={(event) => { setKeyword(event.target.value); setPage(1); }} />
            <Typography.Text type="secondary" className="text-xs">共 {filtered.length} 个应用</Typography.Text>
            <Permission requiredPermissions={['Operate']} permissionPath="/apm/integration/applications">
              <Button type="primary" icon={<PlusOutlined aria-hidden="true" />} onClick={openCreate}>创建应用</Button>
            </Permission>
          </FilterToolbar>
        </ApmSurface>
        <ApmSurface padding="none" className="overflow-hidden">
          {state === 'ready' ? (
            <CustomTable
              autoScrollX={false}
              rowKey="id"
              columns={columns}
              dataSource={pageRows}
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
        </ApmSurface>
      </div>

      <Modal title={editing ? '编辑应用' : '创建应用'} open={modalOpen} confirmLoading={submitting} okText={editing ? '保存' : '创建'} cancelText="取消" styles={{ body: { maxHeight: 'calc(100vh - 240px)', overflowY: 'auto' } }} onOk={() => void submit()} onCancel={() => setModalOpen(false)} forceRender>
        <Form form={form} layout="vertical" preserve={false} className="pt-3">
          <Form.Item name="application_id" label="应用 ID" extra="创建后不可修改，将作为 service.namespace。" rules={editing ? [] : [{ required: true, message: '请输入应用 ID' }, { pattern: /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/, message: '仅支持字母、数字、点、下划线和连字符' }]} hidden={Boolean(editing)}>
            <Input placeholder="例如 shop" autoComplete="off" />
          </Form.Item>
          <Form.Item name="name" label="应用名称" rules={[{ required: true, whitespace: true, message: '请输入应用名称' }, { max: 128 }]}>
            <Input placeholder="例如 电商主站" />
          </Form.Item>
          <Form.Item name="description" label="应用说明" rules={[{ max: 512 }]}>
            <Input.TextArea rows={3} maxLength={512} showCount placeholder="说明业务范围或负责人（可选）" />
          </Form.Item>
          <Form.Item name="organization_ids" label="组织" rules={[{ required: true, type: 'array', min: 1, message: '至少选择一个组织' }]}>
            <GroupTreeSelect multiple mode="ownership" showSearch placeholder="选择可管理此应用的组织" />
          </Form.Item>
        </Form>
      </Modal>
    </ApmRouteShell>
  );
}
