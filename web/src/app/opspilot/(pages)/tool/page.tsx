'use client';
import React, { useState, useEffect } from 'react';
import { Form, message, Button, Menu, Modal, Drawer } from 'antd';
import { Store } from 'antd/lib/form/interface';
import { useTranslation } from '@/utils/i18n';
import EntityList from '@/components/entity-list';
import DynamicForm from '@/components/dynamic-form';
import OperateModal from '@/components/operate-modal';
import GroupTreeSelect from '@/components/group-tree-select';
import { useUserInfoContext } from '@/context/userInfo';
import { Tool, TagOption } from '@/app/opspilot/types/tool';
import PermissionWrapper from "@/components/permission";
import styles from '@/app/opspilot/styles/common.module.scss';
import { useToolApi } from '@/app/opspilot/api/tool';
import VariableList from '@/app/opspilot/components/tool/variableList';
import UrlInputWithButton from '@/app/opspilot/components/tool/urlInputWithButton';
import Icon from '@/components/icon';

const ToolListPage: React.FC = () => {
  const { useForm } = Form;
  const { t } = useTranslation();
  const { selectedGroup } = useUserInfoContext();
  const { fetchTools, createTool, updateTool, deleteTool, fetchAvailableTools } = useToolApi();
  const [loading, setLoading] = useState<boolean>(false);
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
  const [isModalVisible, setIsModalVisible] = useState<boolean>(false);
  const [selectedTool, setSelectedTool] = useState<Tool | null>(null);
  const [toolData, setToolData] = useState<Tool[]>([]);
  const [filteredToolData, setFilteredToolData] = useState<Tool[]>([]);
  const [allTags, setAllTags] = useState<TagOption[]>([]);
  const [selectedToolForDetail, setSelectedToolForDetail] = useState<Tool | null>(null);
  const [availableTools, setAvailableTools] = useState<any[]>([]);
  const [fetchingTools, setFetchingTools] = useState<boolean>(false);

  const iconTypes = ['yinliugongju-biaotiyouhua', 'yinliugongju-biaotifenxi', 'yinliugongju-dijiayinliu', 'gongjuqu', 'gongjuxiang', 'gongju1'];
  
  const getRandomIcon = () => {
    return iconTypes[Math.floor(Math.random() * iconTypes.length)];
  };

  const [form] = useForm();

  const handleFetchTools = async () => {
    const url = form.getFieldValue('url');
    if (!url) {
      message.warning(`${t('common.inputMsg')}${t('tool.mcpUrl')}`);
      return;
    }
    
    setFetchingTools(true);
    try {
      const tools = await fetchAvailableTools(url);
      setAvailableTools(tools || []);
      if (!tools || tools.length === 0) {
        message.info(t('tool.noToolsAvailable'));
      }
    } catch {
      message.error(t('tool.fetchToolsFailed'));
      setAvailableTools([]);
    } finally {
      setFetchingTools(false);
    }
  };

  const renderToolsList = (tools: any[]) => {
    return tools.map((tool: any, index: number) => (
      <div 
        key={index}
        className="p-3 bg-gradient-to-br from-slate-50 to-blue-50 rounded-lg hover:shadow-md transition-all duration-200"
      >
        <div className="flex items-start gap-3">
          <div className="flex-shrink-0 w-8 h-8 bg-white rounded-lg flex items-center justify-center shadow-sm">
            <Icon type={getRandomIcon()} className="text-blue-500 text-2xl" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="font-medium text-gray-800 mb-1 truncate">
              {tool.name}
            </div>
            <div className="text-xs text-gray-600 leading-relaxed line-clamp-2">
              {tool.description || '暂无描述'}
            </div>
            {tool.parameters && Object.keys(tool.parameters).length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {Object.keys(tool.parameters).map((param: string) => (
                  <span 
                    key={param}
                    className="inline-block text-xs bg-white text-blue-600 px-2 py-0.5 rounded border border-blue-200"
                  >
                    {param}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    ));
  };

  const isBuiltIn = selectedTool?.is_build_in || false;

  const formFields = [
    {
      name: 'name',
      type: 'input',
      label: t('tool.name'),
      placeholder: `${t('common.inputMsg')}${t('tool.name')}`,
      rules: [{ required: true, message: `${t('common.inputMsg')}${t('tool.name')}` }],
      disabled: isBuiltIn,
    },
    {
      name: 'tags',
      type: 'select',
      label: t('tool.label'),
      placeholder: `${t('common.selectMsg')}${t('tool.label')}`,
      options: [
        { value: 'search', label: `${t('tool.search')} ${t('tool.title')}` },
        { value: 'general', label: `${t('tool.general')} ${t('tool.title')}` },
        { value: 'maintenance', label: `${t('tool.maintenance')} ${t('tool.title')}` },
        { value: 'media', label: `${t('tool.media')} ${t('tool.title')}` },
        { value: 'collaboration', label: `${t('tool.collaboration')} ${t('tool.title')}` },
        { value: 'other', label: `${t('tool.other')} ${t('tool.title')}` },
      ],
      mode: 'multiple',
      rules: [{ required: true, message: `${t('common.selectMsg')}${t('tool.label')}` }],
      disabled: isBuiltIn,
    },
    {
      name: 'url',
      type: 'custom',
      label: t('tool.mcpUrl'),
      component: (
        <UrlInputWithButton 
          disabled={isBuiltIn}
          placeholder={`${t('common.inputMsg')}${t('tool.mcpUrl')}`}
          onFetch={handleFetchTools}
          fetchLoading={fetchingTools}
          fetchButtonText={t('tool.fetchTools')}
        />
      ),
      rules: [{ required: true, message: `${t('common.inputMsg')}${t('tool.mcpUrl')}` }],
    },
    {
      name: 'variables',
      type: 'custom',
      label: t('tool.variables'),
      component: (
        <VariableList
          value={form.getFieldValue('variables') || []}
          onChange={(newVal: any) => {
            form.setFieldsValue({ variables: newVal });
          }}
          disabled={isBuiltIn}
        />
      ),
    },
    {
      name: 'team',
      type: 'custom',
      label: t('common.group'),
      component: (
        <GroupTreeSelect
          value={form.getFieldValue('team') || []}
          onChange={(value) => {
            form.setFieldsValue({ team: value });
          }}
          placeholder={`${t('common.selectMsg')}${t('common.group')}`}
          multiple={true}
        />
      ),
      rules: [{ required: true, message: `${t('common.selectMsg')}${t('common.group')}` }],
    },
    {
      name: 'description',
      type: 'textarea',
      label: t('tool.description'),
      rows: 4,
      placeholder: `${t('common.inputMsg')}${t('tool.description')}`,
      rules: [{ required: true, message: `${t('common.inputMsg')}${t('tool.description')}` }],
      disabled: isBuiltIn,
    },
  ];

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
          const kwargs = (values.variables || []).map((variable: { key: string; type: string; isRequired: boolean }) => ({
            ...variable,
            value: '',
          }));
          const queryParams = {
            ...values,
            icon: 'gongjuji',
            params: {
              name: values.name,
              url: values.url,
              kwargs
            },
            tools: availableTools, // 添加获取到的工具列表
          };
          if (!selectedTool?.id) {
            await createTool(queryParams);
          } else {
            await updateTool(selectedTool.id, queryParams);
          }
          form.resetFields();
          setIsModalVisible(false);
          setAvailableTools([]);
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
    setAvailableTools([]);
  };

  const menuActions = (tool: Tool) => {
    return (
      <Menu className={`${styles.menuContainer}`}>
        <Menu.Item key="edit">
          <PermissionWrapper 
            requiredPermissions={['Edit']}
            instPermissions={tool.permissions}>
            <span className="block w-full" onClick={() => showModal(tool)}>{t('common.edit')}</span>
          </PermissionWrapper>
        </Menu.Item>
        {!tool.is_build_in && (<Menu.Item key="delete">
          <PermissionWrapper 
            requiredPermissions={['Delete']}
            instPermissions={tool.permissions}>
            <span className="block w-full" onClick={() => handleDelete(tool)}>{t('common.delete')}</span>
          </PermissionWrapper>
        </Menu.Item>)}
      </Menu>
    );
  };

  const showModal = (tool: Tool | null) => {
    setSelectedTool(tool);
    setIsModalVisible(true);
    setAvailableTools([]);
    Promise.resolve().then(() => {
      form.setFieldsValue({
        ...tool,
        url: tool?.params?.url,
        team: tool ? tool.team : [selectedGroup?.id],
        variables: tool?.params?.kwargs,
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

  const handleCardClick = (tool: Tool) => {
    setSelectedToolForDetail(tool);
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
        onCardClick={handleCardClick}
      />
      <OperateModal
        title={selectedTool ? `${t('common.edit')}` : `${t('common.add')}`}
        visible={isModalVisible}
        confirmLoading={confirmLoading}
        onOk={handleOk}
        onCancel={handleCancel}
        width={1200}
      >
        <div className="flex gap-4">
          <div className="flex-1">
            <DynamicForm
              form={form}
              fields={formFields}
              initialValues={{ team: selectedTool?.team || [] }}
            />
          </div>
          <div className="w-96 border-l pl-4">
            <div className="mb-3 flex items-center justify-between">
              <span className="font-semibold text-base">{t('tool.availableTools')}</span>
              {availableTools.length > 0 && (
                <span className="text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded">
                  共 {availableTools.length} 个
                </span>
              )}
            </div>
            <div className="max-h-[500px] overflow-y-auto space-y-3">
              {fetchingTools ? (
                <div className="flex items-center justify-center h-40 text-gray-400">
                  <span>加载中...</span>
                </div>
              ) : availableTools.length > 0 ? (
                renderToolsList(availableTools)
              ) : (
                <div className="flex flex-col items-center justify-center h-40 text-gray-400">
                  <Icon type="gongjuxiang" className="text-4xl mb-2 opacity-50" />
                  <span className="text-sm">暂无工具</span>
                  <span className="text-xs mt-1">请先获取工具列表</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </OperateModal>
      <Drawer
        title={selectedToolForDetail ? `${t('tool.title')} - ${selectedToolForDetail.name}` : t('common.viewDetails')}
        placement="right"
        onClose={() => setSelectedToolForDetail(null)}
        open={!!selectedToolForDetail}
        width={600}
      >
        {selectedToolForDetail && (
          <div className="space-y-4">
            {/* 描述部分 */}
            <div>
              <h3 className="text-sm font-semibold text-gray-700 mb-2">{t('tool.description')}</h3>
              <div className="text-sm text-gray-600 p-3 rounded leading-relaxed whitespace-pre-wrap">
                {selectedToolForDetail.description || '暂无描述'}
              </div>
            </div>
            
            {/* 工具列表部分 */}
            {selectedToolForDetail.tools && selectedToolForDetail.tools.length > 0 && (
              <div>
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-gray-700">{t('tool.availableTools')}</h3>
                  <span className="text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded">
                    共 {selectedToolForDetail.tools.length} 个
                  </span>
                </div>
                <div className="space-y-3">
                  {renderToolsList(selectedToolForDetail.tools)}
                </div>
              </div>
            )}
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default ToolListPage;
