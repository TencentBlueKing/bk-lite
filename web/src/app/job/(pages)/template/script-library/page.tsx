'use client';

import React, { useState, useRef } from 'react';
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
} from '@ant-design/icons';
import CustomTable from '@/components/custom-table';
import OperateModal from '@/components/operate-modal';
import ImportFileModalShell from '@/components/import-file-modal-shell';
import { useTranslation } from '@/utils/i18n';
import { useUserInfoContext } from '@/context/userInfo';
import usePermissions from '@/hooks/usePermissions';
import LibraryBatchMenu from '../library-batch-menu';
import useTemplateLibraryList from '../use-template-library-list';
import useJobApi from '@/app/job/api';
import { Script, ScriptFormData, ScriptParam, ScriptParamType, ScriptType } from '@/app/job/types';
import { ColumnItem } from '@/types';
import GroupTreeSelect from '@/components/group-tree-select';
import SearchActionBar from '@/components/search-action-bar';
import TopSection from '@/components/top-section';
import ScriptEditor from '@/components/script-editor';
import { buildJobBuiltinScriptVariables } from '@/app/job/constants/builtin-script-vars';
import TemplateVersionDrawer from '@/app/job/components/template-version-drawer';
import VersionBadge from '@/components/version-badge';
import OrganizationTags, { getOrganizationColumnWidth } from '@/app/job/components/organization-tags';
import Permission from '@/components/permission';
import { useRouter } from 'next/navigation';
import styles from './page.module.scss';

const PARAM_FORM_NAME = 'scriptParameter';

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
  const { userId, selectedGroup } = useUserInfoContext();
  return <ScriptLibrary key={JSON.stringify([userId, selectedGroup?.id])} />;
};

const ScriptLibrary = () => {
  const { t } = useTranslation();
  const { hasPermission } = usePermissions();
  const {
    getScriptList,
    getScriptSelectionIds,
    batchDeleteScripts,
    getScriptDetail,
    createScript,
    updateScript,
    deleteScript,
    exportScripts,
    importScripts,
  } = useJobApi();
  const router = useRouter();

  const [form] = Form.useForm();
  const [paramForm] = Form.useForm<ScriptParam>();
  const [importForm] = Form.useForm();
  const {
    data, loading, searchKey, setSearchKey, appliedSearch, pagination, selection, fetchData, handleSearch, handleTableChange,
  } = useTemplateLibraryList({ resource: 'script', loadPage: getScriptList, loadIds: getScriptSelectionIds });

  const [modalOpen, setModalOpen] = useState(false);
  const [modalType, setModalType] = useState<'add' | 'edit' | 'view'>('add');
  const [editingScript, setEditingScript] = useState<Script | null>(null);
  const [confirmLoading, setConfirmLoading] = useState(false);

  const [importModalOpen, setImportModalOpen] = useState(false);
  const [versionScriptId, setVersionScriptId] = useState<number | null>(null);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importConfirmLoading, setImportConfirmLoading] = useState(false);

  // Script editor state
  const [scriptLang, setScriptLang] = useState<ScriptType>('shell');
  const [scriptVariablePanelExpanded, setScriptVariablePanelExpanded] = useState(false);
  const [scriptContent, setScriptContent] = useState<Record<ScriptType, string>>({
    shell: '',
    bat: '',
    python: '',
    powershell: '',
  });

  // Params management
  const [params, setParams] = useState<ScriptParam[]>([]);
  const [paramEditor, setParamEditor] = useState<'add' | number | null>(null);
  const paramListRef = useRef<HTMLDivElement>(null);
  const confirmedParamIndex = useRef<number | null>(null);
  const isEnumParam = Form.useWatch('type', paramForm) === 'enum';
  const enumOptionsWatch = Form.useWatch('options', paramForm);
  const enumOptions = enumOptionsWatch && enumOptionsWatch.length > 0 ? enumOptionsWatch : [''];

  const formatTime = (timeStr: string) => {
    if (!timeStr) return '-';
    const d = new Date(timeStr);
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  };

  const resetEditorState = (content = { shell: '', bat: '', python: '', powershell: '' }) => {
    setScriptLang('shell');
    setScriptContent(content);
    setParams([]);
    setParamEditor(null);
    confirmedParamIndex.current = null;
    setScriptVariablePanelExpanded(false);
  };

  const openAddModal = () => {
    setModalType('add');
    setEditingScript(null);
    form.resetFields();
    resetEditorState({
      shell: t('job.scriptTemplateShell'),
      bat: t('job.scriptTemplateBat'),
      python: t('job.scriptTemplatePython'),
      powershell: t('job.scriptTemplatePowershell'),
    });
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
    selection.removeFromSelection(record.id);
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

  const handleExportScripts = async (ids: number[]) => {
    try {
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
      selection.clearSelection();
      const summary = t('job.importScriptsResult', undefined, {
        created: result.created.length,
        skipped: result.skipped.length,
        failed: result.failed.length,
      });
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

  const openAddParamForm = () => {
    paramForm.resetFields();
    paramForm.setFieldsValue({
      type: 'text',
      is_encrypted: false,
      is_required: false,
      default: undefined,
      description: undefined,
      options: [''],
    });
    setParamEditor('add');
  };

  const openEditParamForm = (index: number) => {
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
    setParamEditor(index);
  };

  const focusConfirmedParam = () => {
    const index = confirmedParamIndex.current;
    if (index !== null) {
      paramListRef.current?.querySelector<HTMLButtonElement>(`[data-param-edit="${index}"]`)?.focus();
      confirmedParamIndex.current = null;
    }
  };

  const handleParamTypeChange = (type: ScriptParamType) => {
    if (type === 'enum') {
      const currentOptions = paramForm.getFieldValue('options');
      const nextOptions = currentOptions && currentOptions.length > 0 ? currentOptions : [''];
      paramForm.setFieldsValue({ is_encrypted: false, options: nextOptions });
      const currentDefault = paramForm.getFieldValue('default');
      if (currentDefault && !nextOptions.map((item) => item.trim()).includes(currentDefault)) {
        paramForm.setFieldsValue({ default: undefined });
      }
    }
  };

  const handleParamSubmit = (values: ScriptParam) => {
    if (paramEditor === null) return;
    const type = values.type ?? 'text';
    const param: ScriptParam = {
      name: values.name,
      description: values.description || '',
      default: values.default || '',
      is_encrypted: type === 'enum' ? false : !!values.is_encrypted,
      is_required: !!values.is_required,
      type,
    };
    if (type === 'enum') {
      param.options = (values.options ?? []).map((item) => item.trim()).filter(Boolean);
    }
    const index = paramEditor === 'add' ? params.length : paramEditor;
    const updated = [...params];
    updated[index] = param;
    setParams(updated);
    confirmedParamIndex.current = index;
    setParamEditor(null);
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
          <Button
            type="link"
            size="small"
            className="!p-0"
            data-param-edit={index}
            onClick={() => openEditParamForm(index)}
          >
            {t('job.editRule')}
          </Button>
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
      title: t('job.version'),
      dataIndex: 'current_revision_label',
      key: 'current_revision_label',
      width: 160,
      render: (value: string) => <VersionBadge value={value} fallback="--" />,
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
      width: 260,
      fixed: 'right',
      render: (_: unknown, record: Script) => (
        <div className="flex items-center gap-3">
          <a
            className="text-[var(--color-primary)] cursor-pointer"
            onClick={() => openViewModal(record)}
          >
            {t('job.viewScript')}
          </a>
          <Permission requiredPermissions={['Edit']}>
            <a
              className="text-[var(--color-primary)] cursor-pointer"
              onClick={() => openEditModal(record)}
            >
              {t('job.editRule')}
            </a>
          </Permission>
          <Permission requiredPermissions={['Add']} permissionPath="/job/execution/quick-exec">
            <a
              className="text-[var(--color-primary)] cursor-pointer"
              onClick={() => router.push(`/job/execution/quick-exec?script_id=${record.id}`)}
            >
              {t('job.executeScript')}
            </a>
          </Permission>
          <a
            className="text-[var(--color-primary)] cursor-pointer"
            onClick={() => setVersionScriptId(record.id)}
          >
            {t('job.version')}
          </a>
          <Permission requiredPermissions={['Delete']}>
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
          </Permission>
        </div>
      ),
    },
  ];

  const isViewMode = modalType === 'view';

  return (
    <div className="w-full h-full flex flex-col overflow-hidden">
      <TopSection
        title={t('job.scriptLibraryTitle')}
        content={t('job.scriptLibraryDesc')}
        className="mb-4 shrink-0"
      />

      {/* Table Section */}
      <div
        className="rounded-lg px-6 py-6 flex-1 min-h-0 flex flex-col bg-[var(--color-bg-1)] border border-[var(--color-border-1)]"
      >
        <SearchActionBar
          searchProps={{
            placeholder: t('common.search'),
            allowClear: true,
            value: searchKey,
            onChange: (event) => setSearchKey(event.target.value),
            onSearch: handleSearch,
          }}
          actions={(
            <>
              <LibraryBatchMenu
                key={appliedSearch}
                resource="script"
                selectedIds={selection.selectedIds}
                busy={loading || selection.selectingAll}
                selectionVersion={selection.selectionVersion}
                deleteItems={batchDeleteScripts}
                onSuccess={() => {
                  selection.clearSelection();
                  fetchData();
                }}
                onImport={openImportModal}
                onExport={handleExportScripts}
              />
              <Permission requiredPermissions={['Add']}>
                <Button
                  type="primary"
                  icon={<PlusOutlined />}
                  onClick={openAddModal}
                >
                  {t('common.new')}
                </Button>
              </Permission>
            </>
          )}
        />

        {/* Table */}
        <div className="flex-1 min-h-0">
          <CustomTable
            columns={columns}
            dataSource={data}
            loading={loading}
            rowKey="id"
            pagination={pagination}
            onChange={handleTableChange}
            rowSelection={hasPermission(['View', 'Edit', 'Delete']) ? selection.rowSelection : undefined}
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
        width={scriptVariablePanelExpanded ? 1080 : 720}
      >
        <Form form={form} layout="vertical" colon={false} disabled={isViewMode}>
          <Form.Item
            name="name"
            label={t('job.scriptName')}
            rules={[{ required: true, message: t('job.scriptNamePlaceholder') }]}
          >
            <Input placeholder={t('job.scriptNamePlaceholder')} />
          </Form.Item>

          <Form.Item label={t('job.scriptContent')} tooltip={t('job.optionalVariablesHint')}>
            <ScriptEditor
              value={scriptContent}
              onChange={isViewMode ? undefined : setScriptContent}
              activeLang={scriptLang}
              onLangChange={setScriptLang}
              readOnly={isViewMode}
              variablePanel={{
                visible: true,
                followFullscreen: false,
                defaultExpanded: false,
                variables: buildJobBuiltinScriptVariables(t),
              }}
              onVariablePanelExpandedChange={setScriptVariablePanelExpanded}
            />
          </Form.Item>

          <Form.Item
            name="team"
            label={t('job.organization')}
            rules={[{ required: true, message: t('job.organizationRequired') }]}
          >
            <GroupTreeSelect multiple placeholder={t('job.organizationPlaceholder')} />
          </Form.Item>

          <Form.Item label={t('job.paramDefinition')}>
            <div ref={paramListRef}>
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

              {!isViewMode && (
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
            </div>
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

        <OperateModal
          title={t(typeof paramEditor === 'number' ? 'job.editParam' : 'job.addParamTitle')}
          open={paramEditor !== null}
          okText={t('job.confirm')}
          cancelText={t('job.cancel')}
          okButtonProps={{ htmlType: 'submit', form: PARAM_FORM_NAME }}
          onCancel={() => setParamEditor(null)}
          afterClose={focusConfirmedParam}
        >
          <Form
            name={PARAM_FORM_NAME}
            form={paramForm}
            onFinish={handleParamSubmit}
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
          </Form>
        </OperateModal>
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
      <TemplateVersionDrawer
        open={versionScriptId !== null}
        kind="script"
        targetId={versionScriptId}
        onClose={() => setVersionScriptId(null)}
        onRestored={() => fetchData()}
      />
    </div>
  );
};

export default ScriptLibraryPage;
