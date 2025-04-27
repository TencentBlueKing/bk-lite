'use client';
import React, { useState, useEffect } from 'react';
import { Form, message, Button, Menu, Modal } from 'antd';
import { Store } from 'antd/lib/form/interface';
import { useTranslation } from '@/utils/i18n';
import EntityList from '@/components/entity-list';
import DynamicForm from '@/components/dynamic-form';
import OperateModal from '@/components/operate-modal';
import { useUserInfoContext } from '@/context/userInfo';
import { Tool, TagOption } from '@/app/opspilot/types/tool';
import { getFormFields } from '@/app/opspilot/constants/tool'
import PermissionWrapper from "@/components/permission";
import styles from '@/app/opspilot/styles/common.module.scss';
import { useToolApi } from '@/app/opspilot/api/tool';

const ToolListPage: React.FC = () => {
  const { useForm } = Form;
  const { t } = useTranslation();
  const { groups, selectedGroup } = useUserInfoContext();
  const { fetchTools, createTool, updateTool, deleteTool } = useToolApi();
  const formFields = getFormFields(t, groups);
  const [loading, setLoading] = useState<boolean>(false);
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
  const [isModalVisible, setIsModalVisible] = useState<boolean>(false);
  const [selectedTool, setSelectedTool] = useState<Tool | null>(null);
  const [toolData, setToolData] = useState<Tool[]>([]);
  const [filteredToolData, setFilteredToolData] = useState<Tool[]>([]);
  const [allTags, setAllTags] = useState<TagOption[]>([]);

  const [form] = useForm();

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const data = await fetchTools();
      const uniqueTags = Array.from(new Set(data.flatMap((tool: any) => tool.tags))) as string[];
      setAllTags(uniqueTags.map((tag: string) => ({ value: tag, label: t(`tool.${tag}`) })));

      const tools = data.map((tool: any) => ({
        ...tool,
        description: tool.description_tr,
        icon: tool.icon || 'gongjuji',
        tags: tool.tags,
        tagList: tool.tags.map((key: string) => t(`tool.${key}`))
      }));

      setToolData(tools);
      setFilteredToolData(tools);
    } catch (error) {
      console.error(t('common.fetchFailed'), error);
    } finally {
      setLoading(false);
    }
  };

  const handleOk = () => {
    form
      .validateFields()
      .then(async (values: Store) => {
        try {
          setConfirmLoading(true);
          const queryParams = {
            ...values,
            icon: 'gongjuji',
            params: {
              name: values.name,
              url: values.url
            }
          }
          if (!selectedTool?.id) {
            await createTool(queryParams);
          } else {
            await updateTool(selectedTool.id, queryParams);
          }
          form.resetFields();
          setIsModalVisible(false);
          fetchData();
          message.success(t('common.saveSuccess'));
        } catch (error: any) {
          if (error.errorFields && error.errorFields.length) {
            const firstFieldErrorMessage = error.errorFields[0].errors[0];
            message.error(firstFieldErrorMessage || t('common.valFailed'));
          } else {
            message.error(t('common.saveFailed'));
          }
        } finally {
          setConfirmLoading(false);
        }
      })
      .catch((error) => {
        console.error('common.valFailed:', error);
      });
  };

  const handleCancel = () => {
    form.resetFields();
    setIsModalVisible(false);
  };

  const menuActions = (tool: Tool) => {
    return (
      <Menu className={`${styles.menuContainer}`}>
        <Menu.Item key="edit">
          <PermissionWrapper requiredPermissions={['Edit']}>
            <span className="block w-full" onClick={() => showModal(tool)}>{t('common.edit')}</span>
          </PermissionWrapper>
        </Menu.Item>
        {!tool.is_build_in && (<Menu.Item key="delete">
          <PermissionWrapper requiredPermissions={['Delete']}>
            <span className="block w-full" onClick={() => handleDelete(tool)}>{t('common.delete')}</span>
          </PermissionWrapper>
        </Menu.Item>)}
      </Menu>
    );
  };

  const showModal = (tool: Tool | null) => {
    setSelectedTool(tool);
    setIsModalVisible(true);
    Promise.resolve().then(() => {
      form.setFieldsValue({
        ...tool,
        url: tool?.params?.url,
        team: tool ? tool.team : [selectedGroup?.id],
      });
    });
  };

  const handleDelete = (tool: Tool) => {
    Modal.confirm({
      title: `${t('tool.deleteConfirm')}`,
      onOk: async () => {
        try {
          await deleteTool(tool.id);
          fetchData();
          message.success(t('common.delSuccess'));
        } catch {
          message.error(t('common.delFailed'));
        }
      },
    });
  }

  const changeFilter = (selectedTags: string[]) => {
    if (selectedTags.length === 0) {
      setFilteredToolData(toolData);
    } else {
      const filteredData = toolData.filter((tool) =>
        tool.tags.some((tag: string) => selectedTags.includes(tag))
      );
      setFilteredToolData(filteredData);
    }
  };

  return (
    <div className="w-full h-full">
      <EntityList<Tool>
        data={filteredToolData}
        loading={loading}
        menuActions={menuActions}
        operateSection={
          <PermissionWrapper requiredPermissions={['Add']}>
            <Button type="primary" className="ml-2" onClick={() => showModal(null)}>
              {t('common.add')}
            </Button>
          </PermissionWrapper>
        }
        filter={true}
        filterLoading={loading}
        filterOptions={allTags}
        changeFilter={changeFilter}
      />
      <OperateModal
        title={selectedTool ? `${t('common.edit')}` : `${t('common.add')}`}
        visible={isModalVisible}
        confirmLoading={confirmLoading}
        onOk={handleOk}
        onCancel={handleCancel}
      >
        <DynamicForm
          form={form}
          fields={formFields}
          initialValues={{ team: selectedTool?.team || [] }}
        />
      </OperateModal>
    </div>
  );
};

export default ToolListPage;
