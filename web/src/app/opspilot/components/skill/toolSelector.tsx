import React, { useState, useEffect, useMemo, useRef } from 'react';
import { Alert, Button, Form, Input,  InputNumber, Switch } from 'antd';
import CompactEmptyState from '@/components/compact-empty-state';

const { TextArea } = Input;
import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import SelectorOperateModal from './operateModal';
import Icon from '@/components/icon';
import { SelectTool, ToolVariable } from '@/app/opspilot/types/tool';
import { useSkillApi } from '@/app/opspilot/api/skill';
import OperateModal from '@/components/operate-modal';
import EditablePasswordField from '@/components/dynamic-form/editPasswordField';
import {
  isMonitorToolConfig,
  normalizeMonitorToolConfig,
  normalizeMonitorToolConfigs,
} from '@/app/opspilot/utils/monitorToolConfig';
import RedisToolEditor, { RedisToolEditorHandle } from './redisToolEditor';
import MysqlToolEditor, { MysqlToolEditorHandle } from './mysqlToolEditor';
import OracleToolEditor, { OracleToolEditorHandle } from './oracleToolEditor';
import MssqlToolEditor, { MssqlToolEditorHandle } from './mssqlToolEditor';
import PostgresToolEditor, { PostgresToolEditorHandle } from './postgresToolEditor';
import ElasticsearchToolEditor, { ElasticsearchToolEditorHandle } from './elasticsearchToolEditor';
import JenkinsToolEditor, { JenkinsToolEditorHandle } from './jenkinsToolEditor';
import KubernetesToolEditor, { KubernetesToolEditorHandle } from './kubernetesToolEditor';
import ActiveDirectoryToolEditor, { ActiveDirectoryToolEditorHandle } from './activeDirectoryToolEditor';
import MlopsToolEditor, { MlopsToolEditorHandle } from './mlopsToolEditor';

// ── tool type guards ──────────────────────────────────────────────────────────
const REDIS_TOOL_NAME = 'redis';
const MYSQL_TOOL_NAME = 'mysql';
const ORACLE_TOOL_NAME = 'oracle';
const MSSQL_TOOL_NAME = 'mssql';
const POSTGRES_TOOL_NAME = 'postgres';
const ES_TOOL_NAME = 'elasticsearch';
const JENKINS_TOOL_NAME = 'jenkins';
const AD_TOOL_NAME = 'activedirectory';
const MLOPS_TOOL_NAME = 'mlops';
const KUBERNETES_TOOL_NAMES = new Set(['kubernetes', 'kubernetes_data_collection']);

const isRedisTool = (tool?: SelectTool | null) => (tool?.rawName || tool?.name) === REDIS_TOOL_NAME;
const isMysqlTool = (tool?: SelectTool | null) => (tool?.rawName || tool?.name) === MYSQL_TOOL_NAME;
const isOracleTool = (tool?: SelectTool | null) => (tool?.rawName || tool?.name) === ORACLE_TOOL_NAME;
const isMssqlTool = (tool?: SelectTool | null) => (tool?.rawName || tool?.name) === MSSQL_TOOL_NAME;
const isPostgresTool = (tool?: SelectTool | null) => (tool?.rawName || tool?.name) === POSTGRES_TOOL_NAME;
const isEsTool = (tool?: SelectTool | null) => (tool?.rawName || tool?.name) === ES_TOOL_NAME;
const isJenkinsTool = (tool?: SelectTool | null) => (tool?.rawName || tool?.name) === JENKINS_TOOL_NAME;
const isActiveDirectoryTool = (tool?: SelectTool | null) => (tool?.rawName || tool?.name) === AD_TOOL_NAME;
const isMlopsTool = (tool?: SelectTool | null) => (tool?.rawName || tool?.name) === MLOPS_TOOL_NAME;
const isKubernetesTool = (tool?: SelectTool | null) => {
  const toolName = tool?.rawName || tool?.name;
  return toolName ? KUBERNETES_TOOL_NAMES.has(toolName) : false;
};
const isDbTool = (tool?: SelectTool | null) =>
  isRedisTool(tool) || isMysqlTool(tool) || isOracleTool(tool) || isMssqlTool(tool) ||
  isPostgresTool(tool) || isEsTool(tool) || isJenkinsTool(tool) || isKubernetesTool(tool) ||
  isActiveDirectoryTool(tool);

/** 连接类工具自带配置表单；其余工具只有声明了 kwargs 才需要打开配置。 */
export const toolHasConfigurableFields = (tool?: SelectTool | null) => {
  if (!tool || isMonitorToolConfig(tool)) return false;
  if (isMlopsTool(tool) || isDbTool(tool)) return true;
  const kwargs = Array.isArray(tool.kwargs) ? tool.kwargs : [];
  return kwargs.some((item) => Boolean(String(item?.key || '').trim()));
};

type CatalogTool = SelectTool & { id: number; rawName: string };

function matchCatalogTool(binding: SelectTool, catalog: CatalogTool[]) {
  const name = binding.rawName || binding.name;
  const sameId = catalog.find(tool => tool.id === binding.id);
  if (sameId && (sameId.rawName === name || sameId.name === name)) return sameId;
  // Built-in names are portable across installations. External MCP bindings require their original identity.
  if (binding.isBuildIn !== false) return catalog.find(tool => tool.isBuildIn && tool.rawName === name);
}

// ── component ─────────────────────────────────────────────────────────────────
interface ToolSelectorProps {
  defaultTools: SelectTool[];
  onChange: (selected: SelectTool[]) => void;
}

const ToolSelector: React.FC<ToolSelectorProps> = ({ defaultTools, onChange }) => {
  const { t } = useTranslation();
  const { fetchSkillTools } = useSkillApi();
  const [loading, setLoading] = useState<boolean>(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [pickerKind, setPickerKind] = useState<'tool' | 'mcp'>('tool');
  const [tools, setTools] = useState<CatalogTool[]>([]);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [editingBinding, setEditingBinding] = useState<SelectTool | null>(null);
  const selections = useMemo(() => defaultTools.map(binding => {
    const catalog = matchCatalogTool(binding, tools);
    const display = catalog ? { ...catalog, kwargs: binding.kwargs?.length ? binding.kwargs : catalog.kwargs } : binding;
    return { binding, catalog, display };
  }), [defaultTools, tools]);
  const editingTool = selections.find(item => item.binding === editingBinding)?.display;
  const [form] = Form.useForm();

  // refs to each DB editor's imperative save handle
  const redisRef = useRef<RedisToolEditorHandle>(null);
  const mysqlRef = useRef<MysqlToolEditorHandle>(null);
  const oracleRef = useRef<OracleToolEditorHandle>(null);
  const mssqlRef = useRef<MssqlToolEditorHandle>(null);
  const postgresRef = useRef<PostgresToolEditorHandle>(null);
  const esRef = useRef<ElasticsearchToolEditorHandle>(null);
  const jenkinsRef = useRef<JenkinsToolEditorHandle>(null);
  const kubernetesRef = useRef<KubernetesToolEditorHandle>(null);
  const adRef = useRef<ActiveDirectoryToolEditorHandle>(null);
  const mlopsRef = useRef<MlopsToolEditorHandle>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    fetchSkillTools().then(data => {
      if (active) setTools(data.map(tool => ({
        id: tool.id,
        name: tool.display_name || tool.name,
        rawName: tool.name,
        icon: tool.icon || 'gongjuji',
        description: tool.description_tr || tool.description || '',
        isBuildIn: tool.is_build_in !== false,
        systemTags: tool.system_tags || [],
        userTags: tool.user_tags || [],
        kwargs: (tool.params?.kwargs || []).filter(kwarg => kwarg.key),
      })));
    }).catch(error => {
      console.error(t('common.fetchFailed'), error);
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, []);

  const commitSelectedTools = (next: SelectTool[]) => onChange(normalizeMonitorToolConfigs(next));
  const isMcpTool = (tool?: SelectTool | null) => tool?.isBuildIn === false;

  const openModal = (kind: 'tool' | 'mcp') => {
    setPickerKind(kind);
    setModalVisible(true);
  };

  const handleModalConfirm = (selectedIds: number[]) => {
    const pickingMcp = pickerKind === 'mcp';
    const kept = selections.filter(({ catalog }) =>
      !catalog || isMcpTool(catalog) !== pickingMcp || selectedIds.includes(catalog.id)
    );
    const alreadySelected = new Set(kept.map(({ catalog, binding }) => catalog?.id ?? binding.id));
    const added = tools.filter(tool => isMcpTool(tool) === pickingMcp && selectedIds.includes(tool.id) && !alreadySelected.has(tool.id));
    if (kept.length !== selections.length || added.length) {
      commitSelectedTools([...kept.map(item => item.binding), ...added]);
    }
    setModalVisible(false);
  };

  const handleModalCancel = () => setModalVisible(false);

  const openEditModal = (binding: SelectTool, display: SelectTool) => {
    const normalizedTool = normalizeMonitorToolConfig(display);
    setEditingBinding(binding);
    if (isMonitorToolConfig(normalizedTool)) {
      form.setFieldsValue({ kwargs: [] });
    } else if (!isDbTool(normalizedTool)) {
      form.setFieldsValue({
        kwargs: normalizedTool.kwargs?.map((item) => ({ key: item.key, value: item.value, type: item.type, isRequired: item.isRequired })) || [],
      });
    }
    setEditModalVisible(true);
  };

  const saveToolConfig = (kwargs: ToolVariable[]) => {
    if (editingTool) {
      commitSelectedTools(defaultTools.map(tool => tool === editingBinding ? { ...editingTool, kwargs } : tool));
    }
    setEditModalVisible(false);
    setEditingBinding(null);
  };

  const handleEditModalOk = () => {
    if (isMonitorToolConfig(editingTool)) {
      saveToolConfig([]);
      return;
    }

    // For DB tools, delegate to the editor's imperative save (validation + serialization inside)
    if (isRedisTool(editingTool)) { redisRef.current?.save(); return; }
    if (isMysqlTool(editingTool)) { mysqlRef.current?.save(); return; }
    if (isOracleTool(editingTool)) { oracleRef.current?.save(); return; }
    if (isMssqlTool(editingTool)) { mssqlRef.current?.save(); return; }
    if (isPostgresTool(editingTool)) { postgresRef.current?.save(); return; }
    if (isEsTool(editingTool)) { esRef.current?.save(); return; }
    if (isJenkinsTool(editingTool)) { jenkinsRef.current?.save(); return; }
    if (isKubernetesTool(editingTool)) { kubernetesRef.current?.save(); return; }
    if (isActiveDirectoryTool(editingTool)) { adRef.current?.save(); return; }
    if (isMlopsTool(editingTool)) { mlopsRef.current?.save(); return; }

    // Generic form-based tool
    form.validateFields().then((values) => {
      saveToolConfig(values.kwargs);
    });
  };

  const handleEditModalCancel = () => {
    setEditModalVisible(false);
    setEditingBinding(null);
  };

  const renderToolGroup = (kind: 'tool' | 'mcp') => {
    const mcp = kind === 'mcp';
    const groupTools = selections.filter(({ display }) => isMcpTool(display) === mcp);
    return (
      <div className={mcp ? 'mt-4 border-t border-[var(--color-border-1)] pt-4' : undefined}>
        <div className="mb-1 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="text-[13px] font-medium text-[var(--color-text-1)]">
              {mcp ? t('skill.mcpSection', 'MCP') : t('skill.tool')}
            </span>
            {groupTools.length > 0 && (
              <span className="inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-[var(--color-count-alt-bg)] px-1.5 text-[11px] font-medium tabular-nums leading-none text-[var(--color-count-alt)]">
                {groupTools.length}
              </span>
            )}
          </div>
          <Button size="small" type="link" icon={<PlusOutlined />} onClick={() => openModal(kind)} className="px-0 text-xs">
            {mcp ? t('skill.addMcp', '添加 MCP') : t('skill.addTool')}
          </Button>
        </div>
        <p className="mb-2.5 mt-0 text-xs text-[var(--color-text-3)]">
          {mcp ? t('skill.mcpMountHint', '挂载已接入的 MCP 服务，由模型按需调用') : t('skill.toolMountHint')}
        </p>
        {groupTools.length === 0 ? (
          <div className="py-1 text-xs text-[var(--color-text-4)]">
            {mcp ? t('skill.mcpEmpty', '暂未添加 MCP，可点击右上角「添加 MCP」进行选择') : t('skill.toolEmpty')}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-2 pt-1">
            {groupTools.map(({ binding, catalog, display: tool }) => (
              <div
                key={JSON.stringify([binding.id, binding.rawName || binding.name])}
                className="flex flex-col rounded-lg p-2.5 transition-all bg-[var(--color-fill-1)]/70 hover:bg-[var(--color-fill-2)]"
              >
                <div className="flex w-full items-center justify-between">
                  <div className="flex min-w-0 items-center gap-1.5">
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-[var(--color-bg)] text-[var(--color-primary)] shadow-2xs">
                      <Icon className="text-xs" type={tool.icon || 'gongju'} />
                    </span>
                    <span className="truncate text-xs font-medium text-[var(--color-text-1)]" title={tool.name}>
                      {tool.name}
                    </span>
                    {!loading && !catalog && (
                      <span className="text-xs text-[var(--color-text-3)]">
                        {t('skill.toolOutsideCatalog', '当前目录不可见')}
                      </span>
                    )}
                  </div>
                  <div className="ml-2 flex shrink-0 items-center gap-1">
                    {toolHasConfigurableFields(tool) && (
                      <Button
                        type="link"
                        size="small"
                        className="h-6 px-1 text-[11px]"
                        onClick={() => openEditModal(binding, tool)}
                      >
                        <EditOutlined className="text-xs" />
                        <span className="ml-0.5">{t('skill.configureTool')}</span>
                      </Button>
                    )}
                    <DeleteOutlined
                      className="cursor-pointer p-1 text-xs text-[var(--color-text-4)] transition-colors hover:text-red-500"
                      aria-label={t('common.delete', '删除') + ' ' + tool.name}
                      onClick={() => commitSelectedTools(defaultTools.filter(item => item !== binding))}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  const pickerMcp = pickerKind === 'mcp';
  const unavailableIds = new Set(selections.filter(item => !item.catalog).map(item => item.binding.id));
  const pickerTools = tools.filter(tool => isMcpTool(tool) === pickerMcp && !unavailableIds.has(tool.id));

  return (
    <div>
      {renderToolGroup('tool')}
      {renderToolGroup('mcp')}

      <SelectorOperateModal
        title={pickerMcp ? t('skill.selectMcp', '选择 MCP') : t('skill.selecteTool')}
        visible={modalVisible}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        loading={loading}
        options={pickerTools}
        isNeedGuide={false}
        showToolDetail={true}
        selectedOptions={selections.flatMap(({ catalog }) => catalog && isMcpTool(catalog) === pickerMcp ? [catalog.id] : [])}
        onOk={handleModalConfirm}
        onCancel={handleModalCancel}
      />

      <OperateModal
        title={t('common.edit')}
        visible={editModalVisible}
        onOk={handleEditModalOk}
        onCancel={handleEditModalCancel}
        okText={t('common.save')}
        cancelText={t('common.cancel')}
        width={isDbTool(editingTool) ? 800 : undefined}
      >
        <Form form={form} layout="vertical">
          {isMonitorToolConfig(editingTool) ? (
            <Alert
              type="info"
              showIcon
              message={t('tool.monitor.callerIdentityTitle')}
              description={t('tool.monitor.callerIdentityDescription')}
            />
          ) : isRedisTool(editingTool) ? (
            <RedisToolEditor ref={redisRef} initialKwargs={editingTool?.kwargs ?? []} onSave={saveToolConfig} />
          ) : isMysqlTool(editingTool) ? (
            <MysqlToolEditor ref={mysqlRef} initialKwargs={editingTool?.kwargs ?? []} onSave={saveToolConfig} />
          ) : isOracleTool(editingTool) ? (
            <OracleToolEditor ref={oracleRef} initialKwargs={editingTool?.kwargs ?? []} onSave={saveToolConfig} />
          ) : isMssqlTool(editingTool) ? (
            <MssqlToolEditor ref={mssqlRef} initialKwargs={editingTool?.kwargs ?? []} onSave={saveToolConfig} />
          ) : isPostgresTool(editingTool) ? (
            <PostgresToolEditor ref={postgresRef} initialKwargs={editingTool?.kwargs ?? []} onSave={saveToolConfig} />
          ) : isEsTool(editingTool) ? (
            <ElasticsearchToolEditor ref={esRef} initialKwargs={editingTool?.kwargs ?? []} onSave={saveToolConfig} />
          ) : isJenkinsTool(editingTool) ? (
            <JenkinsToolEditor ref={jenkinsRef} initialKwargs={editingTool?.kwargs ?? []} onSave={saveToolConfig} />
          ) : isKubernetesTool(editingTool) ? (
            <KubernetesToolEditor ref={kubernetesRef} initialKwargs={editingTool?.kwargs ?? []} onSave={saveToolConfig} />
          ) : isActiveDirectoryTool(editingTool) ? (
            <ActiveDirectoryToolEditor ref={adRef} initialKwargs={editingTool?.kwargs ?? []} onSave={saveToolConfig} />
          ) : isMlopsTool(editingTool) ? (
            <MlopsToolEditor ref={mlopsRef} initialKwargs={editingTool?.kwargs ?? []} onSave={saveToolConfig} />
          ) : (
            <Form.List name="kwargs">
              {(fields) => (
                <>
                  {fields.length === 0 && (
                    <CompactEmptyState description={t('common.noData')} />
                  )}
                  {fields.map(({ key, name, fieldKey, ...restField }) => {
                    const fieldType = form.getFieldValue(['kwargs', name, 'type']);
                    const fieldLabel = form.getFieldValue(['kwargs', name, 'key']);
                    const isRequired = form.getFieldValue(['kwargs', name, 'isRequired']);

                    const renderInput = () => {
                      switch (fieldType) {
                        case 'text':
                          return <Input />;
                        case 'textarea':
                          return <TextArea rows={4} />;
                        case 'password':
                          return <EditablePasswordField />;
                        case 'number':
                          return <InputNumber style={{ width: '100%' }} />;
                        case 'checkbox':
                          return <Switch />;
                        default:
                          return <Input />;
                      }
                    };

                    return (
                      <Form.Item
                        key={key}
                        {...restField}
                        name={[name, 'value']}
                        fieldKey={[fieldKey ?? '', 'value']}
                        label={fieldLabel}
                        rules={[{ required: isRequired, message: `${t('common.inputMsg')}${fieldLabel}` }]}
                        valuePropName={fieldType === 'checkbox' ? 'checked' : 'value'}
                      >
                        {renderInput()}
                      </Form.Item>
                    );
                  })}
                </>
              )}
            </Form.List>
          )}
        </Form>
      </OperateModal>
    </div>
  );
};

export default ToolSelector;
