import React, { useState, useEffect, useRef } from 'react';
import { Alert, Button, Tooltip, Form, Input,  InputNumber, Switch } from 'antd';
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

// ── tool type guards ──────────────────────────────────────────────────────────
const REDIS_TOOL_NAME = 'redis';
const MYSQL_TOOL_NAME = 'mysql';
const ORACLE_TOOL_NAME = 'oracle';
const MSSQL_TOOL_NAME = 'mssql';
const POSTGRES_TOOL_NAME = 'postgres';
const ES_TOOL_NAME = 'elasticsearch';
const JENKINS_TOOL_NAME = 'jenkins';
const KUBERNETES_TOOL_NAMES = new Set(['kubernetes', 'kubernetes_data_collection']);

const isRedisTool = (tool?: SelectTool | null) => (tool?.rawName || tool?.name) === REDIS_TOOL_NAME;
const isMysqlTool = (tool?: SelectTool | null) => (tool?.rawName || tool?.name) === MYSQL_TOOL_NAME;
const isOracleTool = (tool?: SelectTool | null) => (tool?.rawName || tool?.name) === ORACLE_TOOL_NAME;
const isMssqlTool = (tool?: SelectTool | null) => (tool?.rawName || tool?.name) === MSSQL_TOOL_NAME;
const isPostgresTool = (tool?: SelectTool | null) => (tool?.rawName || tool?.name) === POSTGRES_TOOL_NAME;
const isEsTool = (tool?: SelectTool | null) => (tool?.rawName || tool?.name) === ES_TOOL_NAME;
const isJenkinsTool = (tool?: SelectTool | null) => (tool?.rawName || tool?.name) === JENKINS_TOOL_NAME;
const isKubernetesTool = (tool?: SelectTool | null) => {
  const toolName = tool?.rawName || tool?.name;
  return toolName ? KUBERNETES_TOOL_NAMES.has(toolName) : false;
};
const isDbTool = (tool?: SelectTool | null) =>
  isRedisTool(tool) || isMysqlTool(tool) || isOracleTool(tool) || isMssqlTool(tool) ||
  isPostgresTool(tool) || isEsTool(tool) || isJenkinsTool(tool) || isKubernetesTool(tool);

const isSameToolVariant = (tool?: SelectTool | null, defaultTool?: SelectTool | null) => {
  if (!tool || !defaultTool) return false;
  return (tool.rawName || tool.name) === (defaultTool.rawName || defaultTool.name);
};

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
  const [tools, setTools] = useState<SelectTool[]>([]);
  const [selectedTools, setSelectedTools] = useState<SelectTool[]>([]);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [editingTool, setEditingTool] = useState<SelectTool | null>(null);
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

  const commitSelectedTools = (nextTools: SelectTool[]) => {
    const normalizedTools = normalizeMonitorToolConfigs(nextTools);
    setSelectedTools(normalizedTools);
    onChange(normalizedTools);
  };

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const data = await fetchSkillTools();
      const normalizedDefaultTools = normalizeMonitorToolConfigs(defaultTools);
      const defaultToolMap = new Map(normalizedDefaultTools.map((tool) => [tool.id, tool]));
      const defaultRedisTool = normalizedDefaultTools.find((tool) => isRedisTool(tool));
      const defaultMysqlTool = normalizedDefaultTools.find((tool) => isMysqlTool(tool));
      const defaultOracleTool = normalizedDefaultTools.find((tool) => isOracleTool(tool));
      const defaultMssqlTool = normalizedDefaultTools.find((tool) => isMssqlTool(tool));
      const defaultPostgresTool = normalizedDefaultTools.find((tool) => isPostgresTool(tool));
      const defaultEsTool = normalizedDefaultTools.find((tool) => isEsTool(tool));
      const defaultJenkinsTool = normalizedDefaultTools.find((tool) => isJenkinsTool(tool));
      const defaultKubernetesTool = normalizedDefaultTools.find((tool) => isKubernetesTool(tool));
      const fetchedTools = data.map((tool) => {
        const defaultTool = defaultToolMap.get(tool.id);
        const kwargs = (tool.params.kwargs || [])
          .filter((kwarg) => kwarg.key)
          .map((kwarg) => ({
            ...kwarg,
            value: (defaultTool?.kwargs ?? []).find((dk) => dk.key === kwarg.key)?.value ?? kwarg.value,
          }));
        return normalizeMonitorToolConfig({
          id: tool.id,
          name: tool.display_name || tool.name,
          rawName: tool.name,
          icon: tool.icon || 'gongjuji',
          description: tool.description_tr || tool.description || '',
          kwargs,
        });
      });
      setTools(fetchedTools);

      const initialSelectedTools = fetchedTools
        .filter((tool) => defaultToolMap.has(tool.id)
          || (isRedisTool(tool) && !!defaultRedisTool)
          || (isMysqlTool(tool) && !!defaultMysqlTool)
          || (isOracleTool(tool) && !!defaultOracleTool)
          || (isMssqlTool(tool) && !!defaultMssqlTool)
          || (isPostgresTool(tool) && !!defaultPostgresTool)
          || (isEsTool(tool) && !!defaultEsTool)
          || (isJenkinsTool(tool) && !!defaultJenkinsTool)
          || (isKubernetesTool(tool) && !!defaultKubernetesTool && isSameToolVariant(tool, defaultKubernetesTool)))
        .map((tool) => {
          const matchedDefaultTool = defaultToolMap.get(tool.id)
            || (isRedisTool(tool) ? defaultRedisTool : undefined)
            || (isMysqlTool(tool) ? defaultMysqlTool : undefined)
            || (isOracleTool(tool) ? defaultOracleTool : undefined)
            || (isMssqlTool(tool) ? defaultMssqlTool : undefined)
            || (isPostgresTool(tool) ? defaultPostgresTool : undefined)
            || (isEsTool(tool) ? defaultEsTool : undefined)
            || (isJenkinsTool(tool) ? defaultJenkinsTool : undefined)
            || (isKubernetesTool(tool) && isSameToolVariant(tool, defaultKubernetesTool) ? defaultKubernetesTool : undefined);
          if (!matchedDefaultTool) return tool;
          return { ...tool, kwargs: matchedDefaultTool.kwargs?.length ? matchedDefaultTool.kwargs : tool.kwargs };
        });
      commitSelectedTools(initialSelectedTools);
    } catch (error) {
      console.error(t('common.fetchFailed'), error);
    } finally {
      setLoading(false);
    }
  };

  const openModal = () => setModalVisible(true);

  const handleModalConfirm = (selectedIds: number[]) => {
    const updatedSelectedTools = tools.filter((tool) => selectedIds.includes(tool.id));
    commitSelectedTools(updatedSelectedTools);
    setModalVisible(false);
  };

  const handleModalCancel = () => setModalVisible(false);

  const removeSelectedTool = (toolId: number) => {
    const updatedSelectedTools = selectedTools.filter((tool) => tool.id !== toolId);
    commitSelectedTools(updatedSelectedTools);
  };

  const openEditModal = (tool: SelectTool) => {
    const normalizedTool = normalizeMonitorToolConfig(tool);
    setEditingTool(normalizedTool);
    if (isMonitorToolConfig(normalizedTool)) {
      form.setFieldsValue({ kwargs: [] });
    } else if (!isDbTool(normalizedTool)) {
      form.setFieldsValue({
        kwargs: normalizedTool.kwargs?.map((item) => ({ key: item.key, value: item.value, type: item.type, isRequired: item.isRequired })) || [],
      });
    }
    setEditModalVisible(true);
  };

  /** Called by each DB editor via onSave callback — updates selectedTools and closes modal */
  const handleDbToolSaved = (kwargs: ToolVariable[]) => {
    if (editingTool) {
      const updatedTool = { ...editingTool, kwargs };
      const updatedSelectedTools = selectedTools.map((tool) => (tool.id === editingTool.id ? updatedTool : tool));
      commitSelectedTools(updatedSelectedTools);
    }
    setEditModalVisible(false);
    setEditingTool(null);
  };

  const handleEditModalOk = () => {
    if (isMonitorToolConfig(editingTool)) {
      if (editingTool) {
        const updatedSelectedTools = selectedTools.map((tool) => (
          tool.id === editingTool.id ? normalizeMonitorToolConfig(editingTool) : tool
        ));
        commitSelectedTools(updatedSelectedTools);
      }
      setEditModalVisible(false);
      setEditingTool(null);
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

    // Generic form-based tool
    form.validateFields().then((values) => {
      if (editingTool) {
        const updatedTool = { ...editingTool, kwargs: values.kwargs };
        const updatedSelectedTools = selectedTools.map((tool) => (tool.id === editingTool.id ? updatedTool : tool));
        commitSelectedTools(updatedSelectedTools);
      }
      setEditModalVisible(false);
      setEditingTool(null);
    });
  };

  const handleEditModalCancel = () => {
    setEditModalVisible(false);
    setEditingTool(null);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <span className="text-[13px] font-medium text-[var(--color-text-1)]">{t('skill.tool')}</span>
          {selectedTools.length > 0 && (
            <span className="inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-[var(--color-count-alt-bg)] px-1.5 text-[11px] font-medium tabular-nums leading-none text-[var(--color-count-alt)]">
              {selectedTools.length}
            </span>
          )}
        </div>
        <Button size="small" type="link" icon={<PlusOutlined />} onClick={openModal} className="px-0 text-xs">
          添加工具
        </Button>
      </div>
      <p className="text-xs text-[var(--color-text-3)] mb-2.5 mt-0">扩展智能体的外部 API 和插件调用能力</p>
      {selectedTools.length === 0 ? (
        <div className="text-xs text-[var(--color-text-4)] py-1">
          暂未添加工具，可点击右上角「添加工具」进行选择
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
          {selectedTools.map((tool) => (
            <div
              key={tool.id}
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
                </div>
                <div className="ml-2 flex shrink-0 items-center gap-1">
                  <Button
                    type="link"
                    size="small"
                    className="h-6 px-1 text-[11px]"
                    onClick={() => openEditModal(tool)}
                  >
                    <EditOutlined className="text-xs" />
                    <span className="ml-0.5">配置</span>
                  </Button>
                  <DeleteOutlined
                    className="cursor-pointer p-1 text-xs text-[var(--color-text-4)] transition-colors hover:text-red-500"
                    onClick={() => removeSelectedTool(tool.id)}
                  />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <SelectorOperateModal
        title={t('skill.selecteTool')}
        visible={modalVisible}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        loading={loading}
        options={tools}
        isNeedGuide={false}
        showToolDetail={true}
        selectedOptions={selectedTools.map((tool) => tool.id)}
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
            <RedisToolEditor ref={redisRef} initialKwargs={editingTool?.kwargs ?? []} onSave={handleDbToolSaved} />
          ) : isMysqlTool(editingTool) ? (
            <MysqlToolEditor ref={mysqlRef} initialKwargs={editingTool?.kwargs ?? []} onSave={handleDbToolSaved} />
          ) : isOracleTool(editingTool) ? (
            <OracleToolEditor ref={oracleRef} initialKwargs={editingTool?.kwargs ?? []} onSave={handleDbToolSaved} />
          ) : isMssqlTool(editingTool) ? (
            <MssqlToolEditor ref={mssqlRef} initialKwargs={editingTool?.kwargs ?? []} onSave={handleDbToolSaved} />
          ) : isPostgresTool(editingTool) ? (
            <PostgresToolEditor ref={postgresRef} initialKwargs={editingTool?.kwargs ?? []} onSave={handleDbToolSaved} />
          ) : isEsTool(editingTool) ? (
            <ElasticsearchToolEditor ref={esRef} initialKwargs={editingTool?.kwargs ?? []} onSave={handleDbToolSaved} />
          ) : isJenkinsTool(editingTool) ? (
            <JenkinsToolEditor ref={jenkinsRef} initialKwargs={editingTool?.kwargs ?? []} onSave={handleDbToolSaved} />
          ) : isKubernetesTool(editingTool) ? (
            <KubernetesToolEditor ref={kubernetesRef} initialKwargs={editingTool?.kwargs ?? []} onSave={handleDbToolSaved} />
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
