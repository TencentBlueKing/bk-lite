import React, { useState, useEffect, useRef } from 'react';
import { Button, Tooltip, Form, Input, Empty, InputNumber, Switch } from 'antd';

const { TextArea } = Input;
import { DeleteOutlined, EditOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import SelectorOperateModal from './operateModal';
import Icon from '@/components/icon';
import styles from './index.module.scss';
import { SelectTool, ToolVariable } from '@/app/opspilot/types/tool';
import { useSkillApi } from '@/app/opspilot/api/skill';
import OperateModal from '@/components/operate-modal';
import EditablePasswordField from '@/components/dynamic-form/editPasswordField';
import GroupTreeSelect from '@/components/group-tree-select';
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
const MONITOR_TOOL_NAME = 'monitor';
const POSTGRES_TOOL_NAME = 'postgres';
const ES_TOOL_NAME = 'elasticsearch';
const JENKINS_TOOL_NAME = 'jenkins';
const KUBERNETES_TOOL_NAMES = new Set(['kubernetes', 'kubernetes_data_collection']);

const isRedisTool = (tool?: SelectTool | null) => (tool?.rawName || tool?.name) === REDIS_TOOL_NAME;
const isMysqlTool = (tool?: SelectTool | null) => (tool?.rawName || tool?.name) === MYSQL_TOOL_NAME;
const isOracleTool = (tool?: SelectTool | null) => (tool?.rawName || tool?.name) === ORACLE_TOOL_NAME;
const isMssqlTool = (tool?: SelectTool | null) => (tool?.rawName || tool?.name) === MSSQL_TOOL_NAME;
const isMonitorTool = (tool?: SelectTool | null) => (tool?.rawName || tool?.name) === MONITOR_TOOL_NAME;
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

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const data = await fetchSkillTools();
      const defaultToolMap = new Map(defaultTools.map((tool) => [tool.id, tool]));
      const defaultRedisTool = defaultTools.find((tool) => isRedisTool(tool));
      const defaultMysqlTool = defaultTools.find((tool) => isMysqlTool(tool));
      const defaultOracleTool = defaultTools.find((tool) => isOracleTool(tool));
      const defaultMssqlTool = defaultTools.find((tool) => isMssqlTool(tool));
      const defaultPostgresTool = defaultTools.find((tool) => isPostgresTool(tool));
      const defaultEsTool = defaultTools.find((tool) => isEsTool(tool));
      const defaultJenkinsTool = defaultTools.find((tool) => isJenkinsTool(tool));
      const defaultKubernetesTool = defaultTools.find((tool) => isKubernetesTool(tool));
      const fetchedTools = data.map((tool) => {
        const defaultTool = defaultToolMap.get(tool.id);
        const kwargs = (tool.params.kwargs || [])
          .filter((kwarg) => kwarg.key)
          .map((kwarg) => ({
            ...kwarg,
            value: (defaultTool?.kwargs ?? []).find((dk) => dk.key === kwarg.key)?.value ?? kwarg.value,
          }));
        return {
          id: tool.id,
          name: tool.display_name || tool.name,
          rawName: tool.name,
          icon: tool.icon || 'gongjuji',
          description: tool.description_tr || tool.description || '',
          kwargs,
        };
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
      setSelectedTools(initialSelectedTools);
      onChange(initialSelectedTools);
    } catch (error) {
      console.error(t('common.fetchFailed'), error);
    } finally {
      setLoading(false);
    }
  };

  const openModal = () => setModalVisible(true);

  const handleModalConfirm = (selectedIds: number[]) => {
    const updatedSelectedTools = tools.filter((tool) => selectedIds.includes(tool.id));
    setSelectedTools(updatedSelectedTools);
    onChange(updatedSelectedTools);
    setModalVisible(false);
  };

  const handleModalCancel = () => setModalVisible(false);

  const removeSelectedTool = (toolId: number) => {
    const updatedSelectedTools = selectedTools.filter((tool) => tool.id !== toolId);
    setSelectedTools(updatedSelectedTools);
    onChange(updatedSelectedTools);
  };

  const openEditModal = (tool: SelectTool) => {
    setEditingTool(tool);
    if (!isDbTool(tool)) {
      form.setFieldsValue({
        kwargs: tool.kwargs?.map((item) => ({ key: item.key, value: item.value, type: item.type, isRequired: item.isRequired })) || [],
      });
    }
    setEditModalVisible(true);
  };

  /** Called by each DB editor via onSave callback — updates selectedTools and closes modal */
  const handleDbToolSaved = (kwargs: ToolVariable[]) => {
    if (editingTool) {
      const updatedTool = { ...editingTool, kwargs };
      const updatedSelectedTools = selectedTools.map((tool) => (tool.id === editingTool.id ? updatedTool : tool));
      setSelectedTools(updatedSelectedTools);
      onChange(updatedSelectedTools);
    }
    setEditModalVisible(false);
    setEditingTool(null);
  };

  const handleEditModalOk = () => {
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
        setSelectedTools(updatedSelectedTools);
        onChange(updatedSelectedTools);
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
      <Button onClick={openModal}>+ {t('common.add')}</Button>
      <div className="grid grid-cols-2 gap-4 mt-2 pb-2">
        {selectedTools.map((tool) => (
          <div key={tool.id} className={`w-full rounded-md px-4 py-2 flex items-center justify-between ${styles.borderContainer}`}>
            <Tooltip title={tool.name}>
              <div className='flex items-center'>
                <Icon className='text-xl mr-1' type={tool.icon} />
                <span className="inline-block text-ellipsis overflow-hidden whitespace-nowrap">{tool.name}</span>
              </div>
            </Tooltip>
            <div className="flex items-center space-x-2 text-[var(--color-text-3)]">
              <EditOutlined
                className="hover:text-[var(--color-primary)] transition-colors duration-200"
                onClick={() => openEditModal(tool)}
              />
              <DeleteOutlined
                className="hover:text-[var(--color-primary)] transition-colors duration-200"
                onClick={() => removeSelectedTool(tool.id)}
              />
            </div>
          </div>
        ))}
      </div>

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
          {isRedisTool(editingTool) ? (
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
                    <Empty description={t('common.noData')} />
                  )}
                  {fields.map(({ key, name, fieldKey, ...restField }) => {
                    const fieldType = form.getFieldValue(['kwargs', name, 'type']);
                    const fieldLabel = form.getFieldValue(['kwargs', name, 'key']);
                    const isRequired = form.getFieldValue(['kwargs', name, 'isRequired']);

                    const renderInput = () => {
                      if (isMonitorTool(editingTool) && fieldLabel === 'team_id') {
                        return (
                          <GroupTreeSelect
                            multiple={false}
                            showSearch
                            placeholder={t('common.pleaseSelect')}
                          />
                        );
                      }

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
