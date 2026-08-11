'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { AppstoreAddOutlined, EditOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons';
import { Button, Form, Input, message, Modal, Table, Tag, Typography, type TableColumnsType } from 'antd';
import dayjs from 'dayjs';
import useApmApi from '@/app/apm/api';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import type { ApmApplication, ApmApplicationInput } from '@/app/apm/types';
import FilterToolbar from '@/components/filter-toolbar';
import GroupTreeSelect from '@/components/group-tree-select';
import Permission from '@/components/permission';
import { useUserInfoContext } from '@/context/userInfo';

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
      setApplications(items);
      setState(items.length ? 'ready' : 'empty');
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
            <Typography.Text strong className="block">{item.name}</Typography.Text>
            <Typography.Text type="secondary" className="block font-mono text-xs">
              {item.is_builtin ? '空 namespace' : item.application_id}
            </Typography.Text>
          </div>
        </div>
      ),
    },
    { title: '说明', dataIndex: 'description', responsive: ['md'], render: (value) => value || '—' },
    { title: '服务数', dataIndex: 'service_count', width: 100, align: 'right' },
    {
      title: '组织', dataIndex: 'organization_ids', width: 180, responsive: ['lg'],
      render: (values: number[]) => values.map((id) => <Tag bordered={false} key={id}>{groupNames.get(id) ?? `#${id}`}</Tag>),
    },
    {
      title: '类型', key: 'type', width: 100,
      render: (_, item) => <Tag color={item.is_builtin ? 'blue' : undefined}>{item.is_builtin ? '内置' : '自定义'}</Tag>,
    },
    { title: '更新时间', dataIndex: 'updated_at', width: 170, responsive: ['xl'], render: (value) => dayjs(value).format('YYYY-MM-DD HH:mm') },
    {
      title: '操作', key: 'action', width: 90, align: 'right',
      render: (_, item) => item.is_builtin
        ? <Typography.Text type="secondary">系统维护</Typography.Text>
        : (
          <Permission requiredPermissions={['Operate']} permissionPath="/apm/integration/applications">
            <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEdit(item)}>编辑</Button>
          </Permission>
        ),
    },
  ];

  return (
    <ApmRouteShell title="应用管理" description="维护 APM 应用边界；空 namespace 的服务自动归入内置未归类应用。">
      {messageContextHolder}
      <div className="flex flex-col gap-3">
        <ApmSurface padding="compact">
          <FilterToolbar align="start" spacing="flush" className="w-full" contentClassName="w-full">
            <Input allowClear className="min-w-64 flex-1 md:max-w-sm" prefix={<SearchOutlined />} placeholder="搜索应用 ID / 名称" value={keyword} onChange={(event) => setKeyword(event.target.value)} />
            <Typography.Text type="secondary" className="text-xs">共 {filtered.length} 个应用</Typography.Text>
            <Permission requiredPermissions={['Operate']} permissionPath="/apm/integration/applications">
              <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>创建应用</Button>
            </Permission>
          </FilterToolbar>
        </ApmSurface>
        <ApmSurface padding="none" className="overflow-hidden">
          {state === 'ready' ? <Table rowKey="id" columns={columns} dataSource={filtered} pagination={{ defaultPageSize: 20, showSizeChanger: true }} /> : <CatalogState kind={state} />}
        </ApmSurface>
      </div>

      <Modal title={editing ? '编辑应用' : '创建应用'} open={modalOpen} confirmLoading={submitting} okText={editing ? '保存' : '创建'} cancelText="取消" onOk={() => void submit()} onCancel={() => setModalOpen(false)} forceRender>
        <Form form={form} layout="vertical" preserve={false} className="pt-3">
          <Form.Item name="application_id" label="应用 ID" extra="创建后不可修改，将作为 service.namespace。" rules={editing ? [] : [{ required: true, message: '请输入应用 ID' }, { pattern: /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/, message: '仅支持字母、数字、点、下划线和连字符' }]} hidden={Boolean(editing)}>
            <Input placeholder="例如 shop" autoComplete="off" />
          </Form.Item>
          <Form.Item name="name" label="应用名称" rules={[{ required: true, whitespace: true, message: '请输入应用名称' }, { max: 128 }]}>
            <Input placeholder="例如 电商主站" />
          </Form.Item>
          <Form.Item name="description" label="应用说明" rules={[{ max: 512 }]}>
            <Input.TextArea rows={3} placeholder="说明业务范围或负责人（可选）" />
          </Form.Item>
          <Form.Item name="organization_ids" label="组织" rules={[{ required: true, type: 'array', min: 1, message: '至少选择一个组织' }]}>
            <GroupTreeSelect multiple mode="ownership" showSearch placeholder="选择可管理此应用的组织" />
          </Form.Item>
        </Form>
      </Modal>
    </ApmRouteShell>
  );
}
