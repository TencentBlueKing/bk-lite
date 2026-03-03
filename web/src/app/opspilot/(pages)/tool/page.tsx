'use client';
import React, { useState, useEffect } from 'react';
import { Form, message, Button, Menu, Modal, Drawer, Switch, Tooltip } from 'antd';
import { Store } from 'antd/lib/form/interface';
import { useTranslation } from '@/utils/i18n';
import EntityList from '@/components/entity-list';
import DynamicForm from '@/components/dynamic-form';
import OperateModal from '@/components/operate-modal';
import GroupTreeSelect from '@/components/group-tree-select';
import { useUserInfoContext } from '@/context/userInfo';
import { Tool, TagOption, ToolPayload } from '@/app/opspilot/types/tool';
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
  const [enableAuth, setEnableAuth] = useState<boolean>(false);

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
      const enable_auth = form.getFieldValue('enable_auth') || false;
      const auth_token = form.getFieldValue('auth_token') || '';
      const tools = await fetchAvailableTools(url, enable_auth, auth_token);
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
        className="p-3 bg-gradient-to-br from-[var(--color-fill-1)] to-[var(--color-primary-bg-active)] rounded-lg hover:shadow-md transition-all duration-200"
      >
        <div className="flex items-start gap-3">
          <div className="flex-shrink-0 w-8 h-8 bg-white rounded-lg flex items-center justify-center shadow-sm">
            <Icon type={getRandomIcon()} className="text-blue-500 text-2xl" />
          </div>
          <div className="flex-1 min-w-0">
            <Tooltip title={tool.name} placement="topLeft" overlayStyle={{ maxWidth: 500 }}>
              <div className="font-medium text-[var(--text-color-2)] mb-1 truncate">
                {tool.name}
              </div>
            </Tooltip>
            <Tooltip 
              title={<div style={{ maxHeight: 300, overflowY: 'auto' }}>{tool.description || t('common.noData')}</div>} 
              placement="topLeft" 
              overlayStyle={{ maxWidth: 500 }}
            >
              <div className="text-xs text-[var(--text-color-3)] leading-relaxed line-clamp-2">
                {tool.description || t('common.noData')}
              </div>
            </Tooltip>
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
    ...(!isBuiltIn ? [
      {
        name: 'enable_auth',
        type: 'custom',
        label: '',
        className: '-mt-3',
        component: (
          <div className="flex items-center gap-2 -mb-6">
            <Switch 
              size="small"
              checked={enableAuth}
              onChange={(checked) => {
                setEnableAuth(checked);
                form.setFieldsValue({ enable_auth: checked });
                if (!checked) {
                  form.setFieldsValue({ auth_token: '' });
                }
              }}
            />
            <span className="text-sm">Basic Auth 认证</span>
          </div>
        ),
      },
      ...(enableAuth ? [{
        name: 'auth_token',
        type: 'inputPwd',
        label: 'Token',
        placeholder: `${t('common.inputMsg')}Token`,
        rules: [{ required: true, message: `${t('common.inputMsg')}Token` }],
      }] : []),
    ] : []),
    {
      name: 'variables',
      type: 'custom',
      label: isBuiltIn ? t('tool.variables') : '',
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
        // 如果启用认证但未填写 token，手动提示错误
        if (enableAuth && !values.auth_token) {
          message.error(`${t('common.inputMsg')}Token`);
          return;
        }
        
        try {
          setConfirmLoading(true);
          const kwargs = (values.variables || []).map((variable: { key: string; type: string; isRequired: boolean }) => ({
            ...variable,
            value: '',
          }));
          const { enable_auth, auth_token, ...restValues } = values;
          const queryParams: ToolPayload = {
            ...restValues,
            name: values.name,
            icon: 'gongjuji',
            params: {
              name: values.name,
              url: values.url,
              kwargs,
              enable_auth: enable_auth || false,
              auth_token: auth_token || '',
            },
            tools: availableTools,
          };
          if (!selectedTool?.id) {
            await createTool(queryParams);
          } else {
            await updateTool(selectedTool.id, queryParams);
          }
          form.resetFields();
          setIsModalVisible(false);
          setAvailableTools([]);
          setEnableAuth(false);
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
    setEnableAuth(false);
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
    // 编辑时直接用 tool.tools 展示,不再请求
    if (tool && Array.isArray(tool.tools)) {
      setAvailableTools(tool.tools);
    } else {
      setAvailableTools([]);
    }
    Promise.resolve().then(() => {
      const enableAuthValue = tool?.params?.enable_auth || false;
      setEnableAuth(enableAuthValue);
      form.setFieldsValue({
        ...tool,
        url: tool?.params?.url,
        team: tool ? tool.team : [selectedGroup?.id],
        variables: tool?.params?.kwargs,
        enable_auth: enableAuthValue,
        auth_token: tool?.params?.auth_token || '',
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
        bodyStyle={{ height: '600px', overflow: 'hidden' }}
      >
        <div className="flex gap-4 h-full">
          <div className="flex-1 overflow-y-auto pr-2">
            <DynamicForm
              form={form}
              fields={formFields}
              initialValues={{ team: selectedTool?.team || [] }}
            />
          </div>
          <div className="w-96 border-l border-[var(--color-border)] pl-4 flex flex-col h-full">
            <div className="mb-3 flex items-center justify-between">
              <span className="font-semibold text-base">{t('tool.availableTools')}</span>
              {availableTools.length > 0 && (
                <span className="text-xs text-gray-500 bg-[var(--color-fill-1)] px-2 py-1 rounded">
                  {t('tool.total')} {availableTools.length} {t('tool.items')}
                </span>
              )}
            </div>
            <div className="flex-1 max-h-full overflow-y-auto space-y-3">
              {fetchingTools ? (
                <>
                  {[1, 2, 3].map((i) => (
                    <div key={i} className="p-3 bg-[var(--color-fill-1)] border border-[var(--color-border)] rounded-lg animate-pulse">
                      <div className="flex items-start gap-3">
                        <div className="flex-shrink-0 w-8 h-8 bg-[var(--color-fill-3)] rounded-lg"></div>
                        <div className="flex-1 space-y-2">
                          <div className="h-4 bg-[var(--color-fill-3)] rounded w-3/4"></div>
                          <div className="h-3 bg-[var(--color-fill-3)] rounded w-full"></div>
                          <div className="h-3 bg-[var(--color-fill-3)] rounded w-5/6"></div>
                        </div>
                      </div>
                    </div>
                  ))}
                </>
              ) : availableTools.length > 0 ? (
                renderToolsList(availableTools)
              ) : (
                <div className="flex flex-col items-center justify-center h-40 text-gray-400">
                  <Icon type="gongjuxiang" className="text-4xl mb-2 opacity-50" />
                  <span className="text-sm">{t('tool.noToolsAvailable')}</span>
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
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-[var(--text-color-1)]">{t('tool.description')}</h3>
              </div>
              <div className="p-3 bg-gradient-to-br from-[var(--color-fill-1)] to-[var(--color-primary-bg-active)] rounded-lg">
                <div className="text-sm text-[var(--text-color-3)] leading-relaxed whitespace-pre-wrap">
                  {selectedToolForDetail.description || t('common.noData')}
                </div>
              </div>
            </div>
            
            {selectedToolForDetail.tools && selectedToolForDetail.tools.length > 0 && (
              <div>
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-[var(--text-color-1)]">{t('tool.availableTools')}</h3>
                  <span className="text-xs text-gray-500 bg-[var(--color-fill-1)] px-2 py-1 rounded">
                    {t('tool.total')} {selectedToolForDetail.tools.length} {t('tool.items')}
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
