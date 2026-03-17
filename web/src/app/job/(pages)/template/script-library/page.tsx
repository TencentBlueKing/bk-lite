'use client';

import React, { useEffect, useState, useCallback, useMemo } from 'react';
import {
  Button,
  Tag,
  Modal,
  message,
  Form,
  Input,
  Switch,
  Table,
} from 'antd';
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import CustomTable from '@/components/custom-table';
import OperateModal from '@/components/operate-modal';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import useJobApi from '@/app/job/api';
import { Script, ScriptFormData, ScriptParam, ScriptType } from '@/app/job/types';
import { ColumnItem } from '@/types';
import GroupTreeSelect from '@/components/group-tree-select';
import SearchCombination from '@/components/search-combination';
import { SearchFilters, FieldConfig } from '@/components/search-combination/types';
import ScriptEditor from '@/app/job/components/script-editor';
import { useRouter } from 'next/navigation';

const SCRIPT_TYPE_COLOR: Record<ScriptType, string> = {
  shell: 'blue',
  python: 'orange',
  bat: 'green',
  powershell: 'purple',
};

const SCRIPT_TYPE_OPTIONS: { value: ScriptType; label: string }[] = [
  { value: 'shell', label: 'Shell' },
  { value: 'python', label: 'Python' },
  { value: 'bat', label: 'Bat' },
  { value: 'powershell', label: 'PowerShell' },
];

const ScriptLibraryPage = () => {
  const { t } = useTranslation();
  const { isLoading: isApiReady } = useApiClient();
  const {
    getScriptList,
    getScriptDetail,
    createScript,
    updateScript,
    deleteScript,
  } = useJobApi();
  const router = useRouter();

  const [form] = Form.useForm();
  const [paramForm] = Form.useForm();
  const [data, setData] = useState<Script[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchFilters, setSearchFilters] = useState<SearchFilters>({});
  const [pagination, setPagination] = useState({
    current: 1,
    total: 0,
    pageSize: 20,
  });

  const [modalOpen, setModalOpen] = useState(false);
  const [modalType, setModalType] = useState<'add' | 'edit' | 'view'>('add');
  const [editingScript, setEditingScript] = useState<Script | null>(null);
  const [confirmLoading, setConfirmLoading] = useState(false);

  // Script editor state
  const [scriptLang, setScriptLang] = useState<ScriptType>('shell');
  const [scriptContent, setScriptContent] = useState<Record<ScriptType, string>>({
    shell: '',
    bat: '',
    python: '',
    powershell: '',
  });

  // Params management
  const [params, setParams] = useState<ScriptParam[]>([]);
  const [paramModalOpen, setParamModalOpen] = useState(false);
  const [editingParamIndex, setEditingParamIndex] = useState<number | null>(null);

  const fetchData = useCallback(
    async (fetchParams: { filters?: SearchFilters; current?: number; pageSize?: number } = {}) => {
      setLoading(true);
      try {
        const filters = fetchParams.filters ?? searchFilters;
        const queryParams: Record<string, unknown> = {
          page: fetchParams.current ?? pagination.current,
          page_size: fetchParams.pageSize ?? pagination.pageSize,
        };
        if (filters && Object.keys(filters).length > 0) {
          Object.entries(filters).forEach(([field, conditions]) => {
            conditions.forEach((condition) => {
              if (condition.lookup_expr === 'in' && Array.isArray(condition.value)) {
                queryParams[field] = (condition.value as string[]).join(',');
              } else {
                queryParams[field] = condition.value;
              }
            });
          });
        }
        const res = await getScriptList(queryParams as any);
        setData(res.items || []);
        setPagination((prev) => ({
          ...prev,
          total: res.count || 0,
        }));
      } finally {
        setLoading(false);
      }
    },
    [searchFilters, pagination.current, pagination.pageSize]
  );

  useEffect(() => {
    if (!isApiReady) {
      fetchData();
    }
  }, [isApiReady]);

  useEffect(() => {
    if (!isApiReady) {
      fetchData();
    }
  }, [pagination.current, pagination.pageSize]);

  const handleSearchChange = useCallback((filters: SearchFilters) => {
    setSearchFilters(filters);
    setPagination((prev) => ({ ...prev, current: 1 }));
    fetchData({ filters, current: 1 });
  }, [fetchData]);

  const fieldConfigs: FieldConfig[] = useMemo(() => [
    {
      name: 'name',
      label: t('job.scriptName'),
      lookup_expr: 'icontains',
    },
    {
      name: 'script_type',
      label: t('job.scriptType'),
      lookup_expr: 'in',
      options: SCRIPT_TYPE_OPTIONS.map((o) => ({ id: o.value, name: o.label })),
    },
    {
      name: 'team',
      label: t('job.organization'),
      lookup_expr: 'icontains',
    },
    {
      name: 'created_by',
      label: t('job.creator'),
      lookup_expr: 'icontains',
    },
    {
      name: 'description',
      label: t('job.scriptDescription'),
      lookup_expr: 'icontains',
    },
  ], [t]);

  const handleTableChange = (pag: any) => {
    setPagination(pag);
  };

  const formatTime = (timeStr: string) => {
    if (!timeStr) return '-';
    const d = new Date(timeStr);
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  };

  const resetEditorState = () => {
    setScriptLang('shell');
    setScriptContent({ shell: '', bat: '', python: '', powershell: '' });
    setParams([]);
  };

  const openAddModal = () => {
    setModalType('add');
    setEditingScript(null);
    form.resetFields();
    resetEditorState();
    setModalOpen(true);
  };

  const openEditModal = (record: Script) => {
    setModalType('edit');
    setEditingScript(record);
    form.resetFields();
    resetEditorState();
    setModalOpen(true);

    void (async () => {
      try {
        const detail = await getScriptDetail(record.id);
        form.setFieldsValue({
          name: detail.name,
          description: detail.description,
          team: detail.team || [],
        });
        const lang = detail.script_type || 'shell';
        setScriptLang(lang);
        setScriptContent({
          shell: '',
          bat: '',
          python: '',
          powershell: '',
          [lang]: detail.content || '',
        });
        setParams(detail.params || []);
        setEditingScript(detail);
      } catch {
        message.error(t('common.operationFailed'));
        setModalOpen(false);
      }
    })();
  };

  const openViewModal = (record: Script) => {
    setModalType('view');
    setEditingScript(record);
    form.resetFields();
    resetEditorState();
    setModalOpen(true);

    void (async () => {
      try {
        const detail = await getScriptDetail(record.id);
        form.setFieldsValue({
          name: detail.name,
          description: detail.description,
          team: detail.team || [],
        });
        const lang = detail.script_type || 'shell';
        setScriptLang(lang);
        setScriptContent({
          shell: '',
          bat: '',
          python: '',
          powershell: '',
          [lang]: detail.content || '',
        });
        setParams(detail.params || []);
        setEditingScript(detail);
      } catch {
        message.error(t('common.operationFailed'));
        setModalOpen(false);
      }
    })();
  };

  const handleDelete = (record: Script) => {
    Modal.confirm({
      title: t('job.deleteScript'),
      content: t('job.deleteScriptConfirm'),
      okText: t('job.confirm'),
      cancelText: t('job.cancel'),
      centered: true,
      onOk: async () => {
        await deleteScript(record.id);
        message.success(t('job.deleteScript'));
        fetchData();
      },
    });
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setConfirmLoading(true);
      const formData: ScriptFormData = {
        name: values.name,
        description: values.description || '',
        script_type: scriptLang,
        content: scriptContent[scriptLang] || '',
        params,
        team: values.team || [],
      };

      if (modalType === 'add') {
        await createScript(formData);
        message.success(t('job.addScript'));
      } else if (editingScript) {
        await updateScript(editingScript.id, formData);
        message.success(t('job.editScript'));
      }
      setModalOpen(false);
      fetchData();
    } catch {
      // validation or API error
    } finally {
      setConfirmLoading(false);
    }
  };

  // Param modal handlers
  const openAddParamModal = () => {
    setEditingParamIndex(null);
    paramForm.resetFields();
    paramForm.setFieldsValue({ is_encrypted: false });
    setParamModalOpen(true);
  };

  const openEditParamModal = (index: number) => {
    setEditingParamIndex(index);
    paramForm.resetFields();
    paramForm.setFieldsValue(params[index]);
    setParamModalOpen(true);
  };

  const handleParamSubmit = async () => {
    try {
      const values = await paramForm.validateFields();
      const param: ScriptParam = {
        name: values.name,
        description: values.description || '',
        default: values.default || '',
        is_encrypted: values.is_encrypted || false,
      };
      if (editingParamIndex !== null) {
        const updated = [...params];
        updated[editingParamIndex] = param;
        setParams(updated);
      } else {
        setParams([...params, param]);
      }
      setParamModalOpen(false);
    } catch {
      // validation error
    }
  };

  const handleDeleteParam = (index: number) => {
    setParams(params.filter((_, i) => i !== index));
  };

  const paramColumns = [
    {
      title: t('job.paramName'),
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: t('job.defaultValue'),
      dataIndex: 'default',
      key: 'default',
      render: (val: string) => val || '-',
    },
    {
      title: t('job.isEncrypted'),
      dataIndex: 'is_encrypted',
      key: 'is_encrypted',
      render: (val: boolean) => (val ? '✓' : '-'),
    },
    {
      title: t('job.paramDescription'),
      dataIndex: 'description',
      key: 'description',
      render: (val: string) => val || '-',
    },
    {
      title: t('job.operation'),
      key: 'action',
      width: 100,
      render: (_: unknown, __: ScriptParam, index: number) => (
        <div className="flex items-center gap-3">
          <a
            className="text-[var(--color-primary)] cursor-pointer"
            onClick={() => openEditParamModal(index)}
          >
            {t('job.editRule')}
          </a>
          <a
            className="text-red-500 cursor-pointer"
            onClick={() => handleDeleteParam(index)}
          >
            <DeleteOutlined />
          </a>
        </div>
      ),
    },
  ];

  const columns: ColumnItem[] = [
    {
      title: t('job.scriptName'),
      dataIndex: 'name',
      key: 'name',
      width: 180,
    },
    {
      title: t('job.scriptType'),
      dataIndex: 'script_type',
      key: 'script_type',
      width: 120,
      render: (_: unknown, record: Script) => (
        <Tag color={SCRIPT_TYPE_COLOR[record.script_type] || 'default'} style={{ margin: 0 }}>
          {record.script_type_display || record.script_type?.toUpperCase()}
        </Tag>
      ),
    },
    {
      title: t('job.organization'),
      dataIndex: 'team_name',
      key: 'team_name',
      width: 120,
      render: (_: unknown, record: Script) => (
        <div className="flex flex-wrap gap-1">
          {(record.team_name && record.team_name.length > 0)
            ? record.team_name.map((name: string, idx: number) => (
              <Tag key={idx}>{name}</Tag>
            ))
            : '-'}
        </div>
      ),
    },
    {
      title: t('job.creator'),
      dataIndex: 'created_by',
      key: 'created_by',
      width: 120,
    },
    {
      title: t('job.updateTime'),
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 180,
      render: (_: unknown, record: Script) => <span>{formatTime(record.updated_at)}</span>,
    },
    {
      title: t('job.scriptDescription'),
      dataIndex: 'description',
      key: 'description',
      width: 200,
      ellipsis: true,
    },
    {
      title: t('job.operation'),
      dataIndex: 'action',
      key: 'action',
      width: 220,
      render: (_: unknown, record: Script) => (
        <div className="flex items-center gap-3">
          <a
            className="text-[var(--color-primary)] cursor-pointer"
            onClick={() => openViewModal(record)}
          >
            {t('job.viewScript')}
          </a>
          <a
            className="text-[var(--color-primary)] cursor-pointer"
            onClick={() => openEditModal(record)}
          >
            {t('job.editRule')}
          </a>
          <a
            className="text-[var(--color-primary)] cursor-pointer"
            onClick={() => router.push(`/job/execution/quick-exec?script_id=${record.id}`)}
          >
            {t('job.executeScript')}
          </a>
          <a
            className="text-[var(--color-primary)] cursor-pointer"
            onClick={() => handleDelete(record)}
          >
            {t('job.deleteScript')}
          </a>
        </div>
      ),
    },
  ];

  const isViewMode = modalType === 'view';

  return (
    <div className="w-full h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div
        className="rounded-lg px-6 py-4 mb-4 flex-shrink-0"
        style={{
          background: 'var(--color-bg-1)',
          border: '1px solid var(--color-border-1)',
        }}
      >
        <h2
          className="text-base font-medium m-0 mb-1"
          style={{ color: 'var(--color-text-1)' }}
        >
          {t('job.scriptLibraryTitle')}
        </h2>
        <p className="text-sm m-0" style={{ color: 'var(--color-text-3)' }}>
          {t('job.scriptLibraryDesc')}
        </p>
      </div>

      {/* Table Section */}
      <div
        className="rounded-lg px-6 py-6 flex-1 min-h-0 flex flex-col"
        style={{
          background: 'var(--color-bg-1)',
          border: '1px solid var(--color-border-1)',
        }}
      >
        {/* Toolbar */}
        <div className="flex justify-between mb-4 flex-shrink-0">
          <SearchCombination
            fieldConfigs={fieldConfigs}
            onChange={handleSearchChange}
            fieldWidth={120}
            selectWidth={300}
          />
          <div className="flex gap-2">
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={openAddModal}
            >
              {t('job.addScript')}
            </Button>
          </div>
        </div>

        {/* Table */}
        <div className="flex-1 min-h-0">
          <CustomTable
            columns={columns}
            dataSource={data}
            loading={loading}
            rowKey="id"
            pagination={pagination}
            onChange={handleTableChange}
          />
        </div>
      </div>

      {/* Add/Edit/View Modal */}
      <OperateModal
        title={
          modalType === 'add'
            ? t('job.addScript')
            : modalType === 'edit'
              ? t('job.editScript')
              : t('job.viewScript')
        }
        open={modalOpen}
        destroyOnClose
        confirmLoading={confirmLoading}
        onCancel={() => setModalOpen(false)}
        footer={
          isViewMode ? (
            <Button onClick={() => setModalOpen(false)}>{t('job.cancel')}</Button>
          ) : (
            <div className="flex justify-end gap-2">
              <Button onClick={() => setModalOpen(false)}>{t('job.cancel')}</Button>
              <Button type="primary" loading={confirmLoading} onClick={handleSubmit}>
                {t('job.save')}
              </Button>
            </div>
          )
        }
        width={720}
      >
        <Form form={form} layout="vertical" colon={false} disabled={isViewMode}>
          <Form.Item
            name="name"
            label={t('job.scriptName')}
            rules={[{ required: true, message: t('job.scriptNamePlaceholder') }]}
          >
            <Input placeholder={t('job.scriptNamePlaceholder')} />
          </Form.Item>

          <Form.Item label={t('job.scriptContent')}>
            <ScriptEditor
              value={scriptContent}
              onChange={isViewMode ? undefined : setScriptContent}
              activeLang={scriptLang}
              onLangChange={setScriptLang}
              readOnly={isViewMode}
            />
          </Form.Item>

          <Form.Item
            name="team"
            label={t('job.organization')}
          >
            <GroupTreeSelect multiple placeholder={t('job.organizationPlaceholder')} />
          </Form.Item>

          <Form.Item
            name="description"
            label={t('job.scriptDescription')}
          >
            <Input.TextArea
              rows={3}
              placeholder={t('job.scriptDescriptionPlaceholder')}
            />
          </Form.Item>

          {/* Parameter Definition */}
          <div className="mb-2">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium" style={{ color: 'var(--color-text-1)' }}>
                {t('job.paramDefinition')}
              </span>
              {!isViewMode && (
                <Button
                  type="dashed"
                  size="small"
                  icon={<PlusOutlined />}
                  onClick={openAddParamModal}
                >
                  {t('job.addParam')}
                </Button>
              )}
            </div>
            {params.length > 0 && (
              <Table
                columns={isViewMode ? paramColumns.filter((c) => c.key !== 'action') : paramColumns}
                dataSource={params}
                rowKey={(_, index) => String(index)}
                pagination={false}
                size="small"
              />
            )}
          </div>
        </Form>
      </OperateModal>

      {/* Add/Edit Param Modal */}
      <OperateModal
        title={editingParamIndex !== null ? t('job.editParam') : t('job.addParamTitle')}
        open={paramModalOpen}
        onCancel={() => setParamModalOpen(false)}
        footer={
          <div className="flex justify-end gap-2">
            <Button onClick={() => setParamModalOpen(false)}>{t('job.cancel')}</Button>
            <Button type="primary" onClick={handleParamSubmit}>
              {t('job.confirm')}
            </Button>
          </div>
        }
        width={520}
      >
        <Form form={paramForm} layout="vertical" colon={false}>
          <Form.Item
            name="name"
            label={t('job.paramName')}
            rules={[{ required: true, message: t('job.paramNamePlaceholder') }]}
          >
            <Input placeholder={t('job.paramNamePlaceholder')} />
          </Form.Item>

          <Form.Item
            name="is_encrypted"
            label={t('job.isEncrypted')}
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>

          <Form.Item
            name="default"
            label={t('job.defaultValue')}
          >
            <Input placeholder={t('job.defaultValuePlaceholder')} />
          </Form.Item>

          <Form.Item
            name="description"
            label={t('job.paramDescription')}
          >
            <Input.TextArea
              rows={3}
              placeholder={t('job.paramDescriptionPlaceholder')}
            />
          </Form.Item>
        </Form>
      </OperateModal>
    </div>
  );
};

export default ScriptLibraryPage;
