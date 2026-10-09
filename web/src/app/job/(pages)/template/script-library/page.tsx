'use client';

import React, { useEffect, useState, useCallback, useMemo } from 'react';
import {
  Button,
  Tag,
  Popconfirm,
  message,
  Form,
  Input,
  Switch,
  Upload,
  Modal,
  Radio,
  Select,
} from 'antd';
import {
  PlusOutlined,
  MinusOutlined,
  DeleteOutlined,
  CheckOutlined,
  CloseOutlined,
  ExportOutlined,
  ImportOutlined,
} from '@ant-design/icons';
import CustomTable from '@/components/custom-table';
import OperateModal from '@/components/operate-modal';
import ImportFileModalShell from '@/components/import-file-modal-shell';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import useJobApi from '@/app/job/api';
import { Script, ScriptFormData, ScriptParam, ScriptParamType, ScriptType } from '@/app/job/types';
import { ColumnItem } from '@/types';
import GroupTreeSelect from '@/components/group-tree-select';
import SearchCombination from '@/components/search-combination';
import { SearchFilters, FieldConfig } from '@/components/search-combination/types';
import ScriptEditor from '@/app/job/components/script-editor';
import OrganizationTags, { getOrganizationColumnWidth } from '@/app/job/components/organization-tags';
import { useRouter } from 'next/navigation';
import styles from './page.module.scss';

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

interface EnumOptionsEditorProps {
  value?: string[];
  onChange?: (value: string[]) => void;
  placeholder?: string;
}

/** Form 受控组件：枚举选项加减行编辑 */
const EnumOptionsEditor: React.FC<EnumOptionsEditorProps> = ({
  value,
  onChange,
  placeholder,
}) => {
  const options = value && value.length > 0 ? value : [''];

  const update = (next: string[]) => {
    onChange?.(next);
  };

  return (
    <ul className="m-0 p-0 list-none">
      {options.map((option, index) => (
        <li key={`enum-opt-${index}`} className="mb-2 flex items-center">
          <Input
            className="mr-[10px] flex-1"
            value={option}
            placeholder={placeholder}
            onChange={(e) => {
              const next = options.map((item, i) => (i === index ? e.target.value : item));
              update(next);
            }}
          />
          <PlusOutlined
            className="mr-[10px] cursor-pointer text-[var(--color-primary)]"
            onClick={() => {
              const next = [...options];
              next.splice(index + 1, 0, '');
              update(next);
            }}
          />
          {options.length > 1 && (
            <MinusOutlined
              className="cursor-pointer text-[var(--color-primary)]"
              onClick={() => update(options.filter((_, i) => i !== index))}
            />
          )}
        </li>
      ))}
    </ul>
  );
};

const ScriptLibraryPage = () => {
  const { t } = useTranslation();
  const { isLoading: isApiReady } = useApiClient();
  const {
    getScriptList,
    getScriptDetail,
    createScript,
    updateScript,
    deleteScript,
    exportScripts,
    importScripts,
  } = useJobApi();
  const router = useRouter();

  const [form] = Form.useForm();
  const [paramForm] = Form.useForm();
  const [importForm] = Form.useForm();
  const [data, setData] = useState<Script[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
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

  const [importModalOpen, setImportModalOpen] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importConfirmLoading, setImportConfirmLoading] = useState(false);

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
  const [paramFormVisible, setParamFormVisible] = useState(false);
  const [editingParamIndex, setEditingParamIndex] = useState<number | null>(null);
  const paramTypeWatch = Form.useWatch('type', paramForm) as ScriptParamType | undefined;
  const enumOptionsWatch = Form.useWatch('options', paramForm) as string[] | undefined;
  const isEnumParam = (paramTypeWatch || 'text') === 'enum';
  const enumOptions = enumOptionsWatch && enumOptionsWatch.length > 0 ? enumOptionsWatch : [''];

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

  const handleDelete = async (record: Script) => {
    await deleteScript(record.id);
    message.success(t('job.deleteScript'));
    fetchData();
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

  const handleExportScripts = async () => {
    if (selectedRowKeys.length === 0) {
      message.warning(t('job.selectScriptsToExport'));
      return;
    }
    try {
      const ids = selectedRowKeys.map((key) => Number(key));
      const blob = await exportScripts(ids);
      const url = window.URL.createObjectURL(new Blob([blob]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'script-pack.zip');
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      message.success(t('job.exportScriptsSuccess'));
    } catch {
      message.error(t('job.exportScriptsFailed'));
    }
  };

  const openImportModal = () => {
    importForm.resetFields();
    setImportFile(null);
    setImportModalOpen(true);
  };

  const handleImportScripts = async () => {
    try {
      const values = await importForm.validateFields();
      if (!importFile) {
        message.warning(t('job.pleaseUploadFile'));
        return;
      }
      setImportConfirmLoading(true);
      const result = await importScripts(importFile, values.team || []);
      setImportModalOpen(false);
      setSelectedRowKeys([]);
      const summary = t('job.importScriptsResult')
        .replace('{{created}}', String(result.created.length))
        .replace('{{skipped}}', String(result.skipped.length))
        .replace('{{failed}}', String(result.failed.length));
      const detailLines = [
        ...result.skipped.map((item) => `${item.name}: ${item.reason}`),
        ...result.failed.map((item) => `${item.name}: ${item.reason}`),
      ];
      Modal.info({
        title: t('job.importScriptsSuccess'),
        content: (
          <div className="space-y-2">
            <div>{summary}</div>
            {detailLines.length > 0 && (
              <ul className="m-0 pl-4 text-[var(--color-text-3)]">
                {detailLines.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            )}
          </div>
        ),
      });
      fetchData();
    } catch {
      // validation or API error
    } finally {
      setImportConfirmLoading(false);
    }
  };

  // Inline param form handlers
  const openAddParamForm = () => {
    setEditingParamIndex(null);
    paramForm.resetFields();
    paramForm.setFieldsValue({
      type: 'text',
      is_encrypted: false,
      is_required: false,
      default: undefined,
      description: undefined,
      options: [''],
    });
    setParamFormVisible(true);
  };

  const openEditParamForm = (index: number) => {
    setEditingParamIndex(index);
    const current = params[index];
    const type: ScriptParamType = current.type === 'enum' ? 'enum' : 'text';
    const initialOptions =
      type === 'enum' && current.options && current.options.length > 0
        ? [...current.options]
        : [''];
    paramForm.resetFields();
    paramForm.setFieldsValue({
      ...current,
      type,
      // 空默认用 undefined，避免 Select allowClear 把 '' 当成有值而显示清空图标
      default: current.default || undefined,
      is_encrypted: type === 'enum' ? false : !!current.is_encrypted,
      options: initialOptions,
    });
    setParamFormVisible(true);
  };

  const cancelParamForm = () => {
    paramForm.resetFields();
    setEditingParamIndex(null);
    setParamFormVisible(false);
  };

  const handleParamTypeChange = (type: ScriptParamType) => {
    if (type === 'enum') {
      const currentOptions = paramForm.getFieldValue('options') as string[] | undefined;
      const nextOptions = currentOptions && currentOptions.length > 0 ? currentOptions : [''];
      paramForm.setFieldsValue({ is_encrypted: false, options: nextOptions });
      const currentDefault = paramForm.getFieldValue('default');
      if (currentDefault && !nextOptions.map((item) => item.trim()).includes(currentDefault)) {
        paramForm.setFieldsValue({ default: undefined });
      }
    }
  };

  const handleParamSubmit = async () => {
    try {
      const values = await paramForm.validateFields();
      const type: ScriptParamType = values.type === 'enum' ? 'enum' : 'text';
      const cleanedOptions = (values.options as string[] | undefined || [])
        .map((item) => item.trim())
        .filter(Boolean);
      const param: ScriptParam = {
        name: values.name,
        description: values.description || '',
        default: values.default || '',
        is_encrypted: type === 'enum' ? false : values.is_encrypted || false,
        is_required: values.is_required || false,
        type,
        ...(type === 'enum' ? { options: cleanedOptions } : {}),
      };
      if (editingParamIndex !== null) {
        const updated = [...params];
        updated[editingParamIndex] = param;
        setParams(updated);
      } else {
        setParams([...params, param]);
      }
      cancelParamForm();
    } catch {
      // validation error
    }
  };

  const handleDeleteParam = (index: number) => {
    setParams(params.filter((_, i) => i !== index));
  };

  // name / default / description 不写 render，交给 CustomTable 的 EllipsisWithTooltip
  const paramColumns = [
    {
      title: t('job.paramName'),
      dataIndex: 'name',
      key: 'name',
      width: 120,
    },
    {
      title: t('job.paramType'),
      dataIndex: 'type',
      key: 'type',
      width: 72,
      render: (val: ScriptParamType | undefined) =>
        val === 'enum' ? t('job.paramTypeEnum') : t('job.paramTypeText'),
    },
    {
      title: t('job.defaultValue'),
      dataIndex: 'default',
      key: 'default',
      width: 100,
    },
    {
      title: t('job.isRequired'),
      dataIndex: 'is_required',
      key: 'is_required',
      width: 88,
      render: (val: boolean) =>
        val ? <CheckOutlined className="text-green-500" /> : <CloseOutlined className="text-gray-400" />,
    },
    {
      title: t('job.isEncrypted'),
      dataIndex: 'is_encrypted',
      key: 'is_encrypted',
      width: 88,
      render: (val: boolean) =>
        val ? <CheckOutlined className="text-green-500" /> : <CloseOutlined className="text-gray-400" />,
    },
    {
      title: t('job.paramDescription'),
      dataIndex: 'description',
      key: 'description',
    },
    {
      title: t('job.operation'),
      key: 'action',
      width: 100,
      fixed: 'right' as const,
      render: (_: unknown, __: ScriptParam, index: number) => (
        <div className="flex items-center gap-3">
          <a
            className="text-[var(--color-primary)] cursor-pointer"
            onClick={() => openEditParamForm(index)}
          >
            {t('job.editRule')}
          </a>
          <Popconfirm
            title={t('common.deleteConfirm')}
            okText={t('job.confirm')}
            cancelText={t('job.cancel')}
            okButtonProps={{ danger: true }}
            onConfirm={() => handleDeleteParam(index)}
          >
            <a className="text-red-500 cursor-pointer">
              <DeleteOutlined />
            </a>
          </Popconfirm>
        </div>
      ),
    },
  ];

  const organizationColumnWidth = getOrganizationColumnWidth(data);

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
        <Tag color={SCRIPT_TYPE_COLOR[record.script_type] || 'default'} className="m-0">
          {record.script_type_display || record.script_type?.toUpperCase()}
        </Tag>
      ),
    },
    {
      title: t('job.organization'),
      dataIndex: 'team_name',
      key: 'team_name',
      width: organizationColumnWidth,
      render: (_: unknown, record: Script) => <OrganizationTags names={record.team_name} />,
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
      fixed: 'right',
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
          <Popconfirm
            title={t('job.deleteScript')}
            description={t('job.deleteScriptConfirm')}
            okText={t('job.confirm')}
            cancelText={t('job.cancel')}
            okButtonProps={{ danger: true }}
            onConfirm={() => handleDelete(record)}
          >
            <a className="text-[var(--color-primary)] cursor-pointer">
              {t('job.deleteScript')}
            </a>
          </Popconfirm>
        </div>
      ),
    },
  ];

  const isViewMode = modalType === 'view';

  return (
    <div className="w-full h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div
        className="rounded-lg px-6 py-4 mb-4 flex-shrink-0 bg-[var(--color-bg-1)] border border-[var(--color-border-1)]"
      >
        <h2
          className="text-base font-medium m-0 mb-1 text-[var(--color-text-1)]"
        >
          {t('job.scriptLibraryTitle')}
        </h2>
        <p className="text-sm m-0 text-[var(--color-text-3)]">
          {t('job.scriptLibraryDesc')}
        </p>
      </div>

      {/* Table Section */}
      <div
        className="rounded-lg px-6 py-6 flex-1 min-h-0 flex flex-col bg-[var(--color-bg-1)] border border-[var(--color-border-1)]"
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
            <Button icon={<ExportOutlined />} onClick={handleExportScripts}>
              {t('job.batchExportScripts')}
            </Button>
            <Button icon={<ImportOutlined />} onClick={openImportModal}>
              {t('job.batchImportScripts')}
            </Button>
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
            rowSelection={{
              selectedRowKeys,
              onChange: (keys) => setSelectedRowKeys(keys),
            }}
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
        destroyOnHidden
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
            rules={[{ required: true, message: t('job.organizationRequired') }]}
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

        </Form>

        {/* Parameter Definition（置于主表单之外，内联表单使用独立的 paramForm 实例，避免 Form 嵌套） */}
        <div className="mb-2">
          <div className="mb-2">
            <span className="text-sm font-medium text-[var(--color-text-1)]">
              {t('job.paramDefinition')}
            </span>
          </div>
          {params.length > 0 && (
            <CustomTable
              columns={isViewMode ? paramColumns.filter((c) => c.key !== 'action') : paramColumns}
              dataSource={params}
              rowKey={(_, index) => String(index)}
              pagination={false}
              size="small"
              scroll={{ x: 720 }}
            />
          )}

          {!isViewMode && !paramFormVisible && (
            <div className={styles.addParamWrapper}>
              <Button
                type="text"
                icon={<PlusOutlined />}
                className={styles.addParamButton}
                onClick={openAddParamForm}
              >
                {t('job.addParam')}
              </Button>
            </div>
          )}

          {!isViewMode && paramFormVisible && (
            <div
              className="mt-2 rounded-md border border-[var(--color-border-1)] bg-[var(--color-fill-1)] p-4"
            >
              <div className="mb-3 text-sm font-medium text-[var(--color-text-1)]">
                {editingParamIndex !== null ? t('job.editParam') : t('job.addParamTitle')}
              </div>
              <Form
                form={paramForm}
                layout="vertical"
                colon={false}
                onValuesChange={(changed, all) => {
                  if (!('options' in changed) || !all.default) {
                    return;
                  }
                  const nextOptions = (changed.options as string[] | undefined) || [];
                  if (!nextOptions.includes(all.default)) {
                    paramForm.setFieldsValue({ default: undefined });
                  }
                }}
              >
                <Form.Item
                  name="name"
                  label={t('job.paramName')}
                  rules={[{ required: true, message: t('job.paramNamePlaceholder') }]}
                >
                  <Input placeholder={t('job.paramNamePlaceholder')} />
                </Form.Item>

                <Form.Item
                  name="type"
                  label={t('job.paramType')}
                  initialValue="text"
                  rules={[{ required: true, message: t('job.paramTypePlaceholder') }]}
                >
                  <Radio.Group
                    options={[
                      { label: t('job.paramTypeText'), value: 'text' },
                      { label: t('job.paramTypeEnum'), value: 'enum' },
                    ]}
                    onChange={(e) => handleParamTypeChange(e.target.value)}
                  />
                </Form.Item>

                <div className="flex gap-12">
                  <Form.Item name="is_required" label={t('job.isRequired')} valuePropName="checked">
                    <Switch />
                  </Form.Item>
                  {!isEnumParam && (
                    <Form.Item name="is_encrypted" label={t('job.isEncrypted')} valuePropName="checked">
                      <Switch />
                    </Form.Item>
                  )}
                </div>

                {isEnumParam && (
                  <Form.Item
                    name="options"
                    label={t('job.paramOptions')}
                    required
                    rules={[
                      {
                        validator: async (_, value: string[] | undefined) => {
                          const cleaned = (value || []).map((item) => item.trim()).filter(Boolean);
                          if (cleaned.length === 0) {
                            return Promise.reject(new Error(t('job.paramEnumOptionsRequired')));
                          }
                        },
                      },
                    ]}
                  >
                    <EnumOptionsEditor placeholder={t('job.paramOptionPlaceholder')} />
                  </Form.Item>
                )}

                <Form.Item
                  name="default"
                  label={t('job.defaultValue')}
                  rules={
                    isEnumParam
                      ? [
                        {
                          validator: async (_, value: string | undefined) => {
                            if (!value) {
                              return;
                            }
                            const cleaned = enumOptions.map((item) => item.trim()).filter(Boolean);
                            if (!cleaned.includes(value)) {
                              return Promise.reject(new Error(t('job.paramEnumDefaultInvalid')));
                            }
                          },
                        },
                      ]
                      : undefined
                  }
                >
                  {isEnumParam ? (
                    <Select
                      allowClear
                      placeholder={t('job.defaultValuePlaceholder')}
                      options={enumOptions
                        .map((item) => item.trim())
                        .filter(Boolean)
                        .map((item) => ({ label: item, value: item }))}
                    />
                  ) : (
                    <Input placeholder={t('job.defaultValuePlaceholder')} />
                  )}
                </Form.Item>

                <Form.Item name="description" label={t('job.paramDescription')}>
                  <Input.TextArea rows={2} placeholder={t('job.paramDescriptionPlaceholder')} />
                </Form.Item>

                <div className="flex justify-end gap-2">
                  <Button onClick={cancelParamForm}>{t('job.cancel')}</Button>
                  <Button type="primary" onClick={handleParamSubmit}>
                    {t('job.confirm')}
                  </Button>
                </div>
              </Form>
            </div>
          )}
        </div>
      </OperateModal>

      <ImportFileModalShell
        title={t('job.importScriptsTitle')}
        open={importModalOpen}
        width={600}
        confirmLoading={importConfirmLoading}
        confirmText={t('job.confirmImport')}
        cancelText={t('job.cancel')}
        confirmDisabled={!importFile}
        onConfirm={handleImportScripts}
        onCancel={() => setImportModalOpen(false)}
        primaryFirst={false}
        uploadProps={{
          accept: '.zip',
          maxCount: 1,
          fileList: importFile
            ? [{ uid: '-1', name: importFile.name, status: 'done' as const }]
            : [],
          beforeUpload: (file) => {
            if (!file.name.toLowerCase().endsWith('.zip')) {
              message.error(t('job.onlyZipAllowed'));
              return Upload.LIST_IGNORE;
            }
            setImportFile(file);
            return false;
          },
          onRemove: () => {
            setImportFile(null);
          },
          uploadText: t('job.dragUploadText'),
          uploadHint: (
            <>
              <div>{t('job.importScriptsHint')}</div>
              <div>{t('job.importScriptsLimitHint')}</div>
            </>
          ),
        }}
        afterUploadPanel={
          <Form form={importForm} layout="vertical" colon={false} className="mt-4">
            <Form.Item
              name="team"
              label={t('job.organization')}
              rules={[{ required: true, message: t('job.organizationRequired') }]}
            >
              <GroupTreeSelect multiple placeholder={t('job.organizationPlaceholder')} />
            </Form.Item>
          </Form>
        }
      />
    </div>
  );
};

export default ScriptLibraryPage;
