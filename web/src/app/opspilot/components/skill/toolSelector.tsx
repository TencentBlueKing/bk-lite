import React, { useState, useEffect } from 'react';
import { Button, Tooltip, Form, Input, Empty, InputNumber, Switch } from 'antd';

const { TextArea } = Input;
import { DeleteOutlined, EditOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import SelectorOperateModal from './operateModal';
import Icon from '@/components/icon';
import styles from './index.module.scss';
import { SelectTool } from '@/app/opspilot/types/tool';
import { useSkillApi } from '@/app/opspilot/api/skill';
import OperateModal from '@/components/operate-modal';
import EditablePasswordField from '@/components/dynamic-form/editPasswordField';

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

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const data = await fetchSkillTools();
      const defaultToolMap = new Map(defaultTools.map((tool) => [tool.id, tool]));
      const fetchedTools = data.map((tool: any) => {
        const defaultTool = defaultToolMap.get(tool.id);
        return {
          id: tool.id,
          name: tool.display_name || tool.name,
          icon: tool.icon || 'gongjuji',
          description: tool.description_tr || tool.description || '',
          kwargs: (tool.params.kwargs || [])
            .filter((kwarg: any) => kwarg.key)
            .map((kwarg: any) => ({
              ...kwarg,
              value: (defaultTool?.kwargs ?? []).find((dk: any) => dk.key === kwarg.key)?.value || kwarg.value,
            })),
        };
      });
      setTools(fetchedTools);

      const initialSelectedTools = fetchedTools.filter((tool) => defaultToolMap.has(tool.id));
      setSelectedTools(initialSelectedTools);
      onChange(initialSelectedTools);
    } catch (error) {
      console.error(t('common.fetchFailed'), error);
    } finally {
      setLoading(false);
    }
  };

  const openModal = () => {
    setModalVisible(true);
  };

  const handleModalConfirm = (selectedIds: number[]) => {
    const updatedSelectedTools = tools.filter((tool) => selectedIds.includes(tool.id));
    setSelectedTools(updatedSelectedTools);
    onChange(updatedSelectedTools);
    setModalVisible(false);
  };

  const handleModalCancel = () => {
    setModalVisible(false);
  };

  const removeSelectedTool = (toolId: number) => {
    const updatedSelectedTools = selectedTools.filter((tool) => tool.id !== toolId);
    setSelectedTools(updatedSelectedTools);
    onChange(updatedSelectedTools);
  };

  const openEditModal = (tool: SelectTool) => {
    setEditingTool(tool);
    form.setFieldsValue({
      kwargs: tool.kwargs?.map((item: any) => ({ key: item.key, value: item.value, type: item.type, isRequired: item.isRequired })) || [],  
    });
    setEditModalVisible(true);
  };

  const handleEditModalOk = () => {
    form.validateFields().then((values) => {
      if (editingTool) {
        const updatedTool = {
          ...editingTool,
          kwargs: values.kwargs,
        };
        const updatedSelectedTools = selectedTools.map((tool) =>
          tool.id === editingTool.id ? updatedTool : tool
        );
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
        selectedOptions={defaultTools.map((tool) => tool.id)}
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
      >
        <Form form={form} layout="vertical">
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
        </Form>
      </OperateModal>
    </div>
  );
};

export default ToolSelector;
