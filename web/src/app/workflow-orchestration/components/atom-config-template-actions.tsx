'use client';

import { FolderOpenOutlined, SaveOutlined } from '@ant-design/icons';
import { App, Button, Form, Input, Popconfirm, Space } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';

import CustomTable from '@/components/custom-table';
import OperateModal from '@/components/operate-modal';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';
import type { AtomConfigTemplateRecord, PaginatedResponse } from '../lib/types';
import { WorkflowPermission } from './workflow-permission';

const API = '/workflow_orchestration/api/atom-config-templates';
const PAGE_SIZE = 10;

export function AtomConfigTemplateActions({
  atomKey,
  parameters,
  onLoad,
}: {
  atomKey: string;
  parameters: Record<string, unknown>;
  onLoad: (parameters: Record<string, unknown>) => void;
}) {
  const { get, post, patch, del } = useApiClient();
  const { message } = App.useApp();
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const [nameForm] = Form.useForm<{ name: string }>();
  const [loadOpen, setLoadOpen] = useState(false);
  const [nameOpen, setNameOpen] = useState(false);
  const [editing, setEditing] = useState<AtomConfigTemplateRecord>();
  const [templates, setTemplates] = useState<AtomConfigTemplateRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZE);
  const [query, setQuery] = useState('');
  const [listLoading, setListLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const loadTemplates = async ({
    nextQuery = query,
    nextPage = page,
    nextPageSize = pageSize,
  }: {
    nextQuery?: string;
    nextPage?: number;
    nextPageSize?: number;
  } = {}) => {
    setListLoading(true);
    try {
      const params = new URLSearchParams({
        atom_key: atomKey,
        page: String(nextPage),
        page_size: String(nextPageSize),
      });
      const trimmed = nextQuery.trim();
      if (trimmed) params.set('query', trimmed);
      const response = await get<PaginatedResponse<AtomConfigTemplateRecord>>(`${API}/?${params.toString()}`);
      setTemplates(response?.items || []);
      setTotal(response?.count || 0);
      setPage(nextPage);
      setPageSize(nextPageSize);
      setQuery(nextQuery);
    } finally {
      setListLoading(false);
    }
  };

  const openCreate = () => {
    setEditing(undefined);
    nameForm.setFieldsValue({ name: '' });
    setNameOpen(true);
  };

  const openRename = (template: AtomConfigTemplateRecord) => {
    setEditing(template);
    nameForm.setFieldsValue({ name: template.name });
    setNameOpen(true);
  };

  const submitName = async () => {
    const values = await nameForm.validateFields();
    setSaving(true);
    try {
      if (editing) {
        await patch<AtomConfigTemplateRecord>(`${API}/${editing.id}/`, { name: values.name.trim() });
        message.success(t('workflowOrchestration.editor.configTemplateRenamed', '配置模板已重命名'));
        await loadTemplates();
      } else {
        await post<AtomConfigTemplateRecord>(`${API}/`, {
          name: values.name.trim(),
          atom_key: atomKey,
          parameters,
        });
        message.success(t('workflowOrchestration.editor.configTemplateSaved', '配置模板已保存'));
      }
      setNameOpen(false);
      nameForm.resetFields();
    } finally {
      setSaving(false);
    }
  };

  const removeTemplate = async (template: AtomConfigTemplateRecord) => {
    await del(`${API}/${template.id}/`);
    message.success(t('workflowOrchestration.editor.configTemplateDeleted', '配置模板已删除'));
    const nextTotal = Math.max(0, total - 1);
    const lastPage = Math.max(1, Math.ceil(nextTotal / pageSize) || 1);
    await loadTemplates({ nextPage: Math.min(page, lastPage) });
  };

  const applyTemplate = (template: AtomConfigTemplateRecord) => {
    onLoad(structuredClone(template.parameters));
    setLoadOpen(false);
    message.success(t('workflowOrchestration.editor.configTemplateLoaded', '配置模板已加载'));
  };

  const columns: ColumnsType<AtomConfigTemplateRecord> = [
    {
      title: t('workflowOrchestration.editor.configTemplateName', '模板名称'),
      dataIndex: 'name',
      key: 'name',
      ellipsis: true,
      render: (name: string) => <span className="font-medium text-[var(--color-text-1)]">{name}</span>,
    },
    {
      title: t('workflowOrchestration.editor.configTemplateUpdatedBy', '更新人'),
      key: 'updated_by',
      width: 140,
      ellipsis: true,
      render: (_: unknown, template) => template.updated_by || template.created_by || '--',
    },
    {
      title: t('workflowOrchestration.editor.configTemplateUpdatedAt', '更新时间'),
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 160,
      render: (value: string | null | undefined) => (value ? convertToLocalizedTime(value, 'YYYY-MM-DD HH:mm') : '--'),
    },
    {
      title: t('common.actions', '操作'),
      key: 'actions',
      width: 180,
      render: (_: unknown, template) => (
        <Space size={10}>
          <WorkflowPermission operation="Edit">
            <Button type="link" size="small" className="px-0" onClick={() => applyTemplate(template)}>
              {t('workflowOrchestration.editor.loadTemplateAction', '选用')}
            </Button>
          </WorkflowPermission>
          <WorkflowPermission operation="Edit">
            <Button type="link" size="small" className="px-0" onClick={() => openRename(template)}>
              {t('workflowOrchestration.editor.renameTemplateAction', '修改')}
            </Button>
          </WorkflowPermission>
          <WorkflowPermission operation="Edit">
            <Popconfirm
              title={t('workflowOrchestration.editor.deleteConfigTemplateConfirm', '删除这个配置模板？')}
              okText={t('common.delete', '删除')}
              cancelText={t('common.cancel', '取消')}
              okButtonProps={{ danger: true }}
              onConfirm={() => void removeTemplate(template)}
            >
              <Button danger type="link" size="small" className="px-0">
                {t('workflowOrchestration.editor.deleteTemplateAction', '删除')}
              </Button>
            </Popconfirm>
          </WorkflowPermission>
        </Space>
      ),
    },
  ];

  return <>
    <WorkflowPermission operation="Edit">
      <Button size="small" icon={<FolderOpenOutlined />} onClick={() => {
        setQuery('');
        setPage(1);
        setLoadOpen(true);
        void loadTemplates({ nextQuery: '', nextPage: 1, nextPageSize: pageSize });
      }}>
        {t('workflowOrchestration.editor.loadConfigTemplate', '加载模板')}
      </Button>
    </WorkflowPermission>
    <WorkflowPermission operation="Edit">
      <Button size="small" icon={<SaveOutlined />} onClick={openCreate}>
        {t('workflowOrchestration.editor.saveAsConfigTemplate', '配置模板')}
      </Button>
    </WorkflowPermission>

    <OperateModal
      title={editing ? t('workflowOrchestration.editor.renameConfigTemplate', '修改模板') : t('workflowOrchestration.editor.saveAsConfigTemplate', '配置模板')}
      open={nameOpen}
      destroyOnHidden
      confirmLoading={saving}
      okText={editing ? t('common.confirm', '确定') : t('common.save', '保存')}
      cancelText={t('common.cancel', '取消')}
      onOk={() => void submitName()}
      onCancel={() => { setNameOpen(false); setEditing(undefined); nameForm.resetFields(); }}
    >
      <Form form={nameForm} layout="vertical" className="pt-3">
        <Form.Item
          label={t('workflowOrchestration.editor.configTemplateName', '模板名称')}
          name="name"
          rules={[{ required: true, whitespace: true, message: t('workflowOrchestration.editor.enterConfigTemplateName', '请输入模板名称') }]}
        >
          <Input maxLength={120} autoFocus />
        </Form.Item>
      </Form>
    </OperateModal>

    <OperateModal
      title={t('workflowOrchestration.editor.loadConfigTemplate', '加载模板')}
      open={loadOpen}
      width={780}
      destroyOnHidden
      footer={null}
      onCancel={() => setLoadOpen(false)}
    >
      <div className="flex h-[480px] flex-col gap-4 pt-2">
        <p className="mb-0 shrink-0 text-[11px] leading-4 text-[var(--color-text-4)]">
          {t('workflowOrchestration.editor.sharedConfigTemplateHint', '当前组织成员共享这些模板；选用后会覆盖当前节点参数。')}
        </p>
        <Input.Search
          allowClear
          className="w-full shrink-0"
          placeholder={t('workflowOrchestration.editor.searchConfigTemplates', '搜索配置模板')}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onSearch={(value) => void loadTemplates({ nextQuery: value, nextPage: 1 })}
        />
        <div className="min-h-0 flex-1">
          <CustomTable<AtomConfigTemplateRecord>
            rowKey="id"
            size="small"
            loading={listLoading}
            dataSource={templates}
            columns={columns}
            scroll={{}}
            pagination={{
              current: page,
              pageSize,
              total,
              showSizeChanger: true,
              onChange: (nextPage, nextPageSize) => {
                void loadTemplates({
                  nextPage: nextPageSize === pageSize ? nextPage : 1,
                  nextPageSize,
                });
              },
            }}
          />
        </div>
      </div>
    </OperateModal>
  </>;
}
