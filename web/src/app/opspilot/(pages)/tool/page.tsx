'use client';
import React, { useState, useEffect } from 'react';
import { Form, message, Button, Menu, Modal, Drawer, Switch, Tooltip, Segmented, Tag, Input, Select, Empty, Dropdown, Upload } from 'antd';
import type { UploadFile } from 'antd/es/upload/interface';
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
import { useSkillApi } from '@/app/opspilot/api/skill';
import type { SkillPackage } from '@/app/opspilot/types/skill';
import VariableList from '@/app/opspilot/components/tool/variableList';
import UrlInputWithButton from '@/app/opspilot/components/tool/urlInputWithButton';
import Icon from '@/components/icon';

const ToolListPage: React.FC = () => {
  const { useForm } = Form;
  const { TextArea } = Input;
  const { t } = useTranslation();
  const { selectedGroup } = useUserInfoContext();
  const { fetchTools, createTool, updateTool, deleteTool, fetchAvailableTools } = useToolApi();
  const { fetchSkillPackages, importSkillPackageZip, updateSkillPackage, deleteSkillPackage } = useSkillApi();
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
  const [assetView, setAssetView] = useState<'tools' | 'skills'>('tools');
  const [skillAssets, setSkillAssets] = useState<SkillPackage[]>([]);
  const [skillSearchKeyword, setSkillSearchKeyword] = useState('');
  const [selectedSkillCategory, setSelectedSkillCategory] = useState<string>('all');
  const [isAddSkillModalVisible, setIsAddSkillModalVisible] = useState(false);
  const [isImportSkillModalVisible, setIsImportSkillModalVisible] = useState(false);
  const [editingSkillAsset, setEditingSkillAsset] = useState<SkillPackage | null>(null);
  const [skillPackageFileList, setSkillPackageFileList] = useState<UploadFile[]>([]);

  const iconTypes = ['yinliugongju-biaotiyouhua', 'yinliugongju-biaotifenxi', 'yinliugongju-dijiayinliu', 'gongjuqu', 'gongjuxiang', 'gongju1'];
  
  const getRandomIcon = () => {
    return iconTypes[Math.floor(Math.random() * iconTypes.length)];
  };

  const [form] = useForm();
  const [addSkillForm] = useForm();

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
      const transport = form.getFieldValue('transport') || 'streamable_http';
      const tools = await fetchAvailableTools(url, enable_auth, auth_token, transport);
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
      label: t('common.name'),
      placeholder: `${t('common.inputMsg')}${t('common.name')}`,
      rules: [{ required: true, message: `${t('common.inputMsg')}${t('common.name')}` }],
      disabled: isBuiltIn,
    },
    {
      name: 'tags',
      type: 'select',
      label: t('tool.label'),
      placeholder: `${t('common.selectMsg')}${t('tool.label')}`,
      options: [
        { value: 'search', label: `${t('common.search')} ${t('tool.title')}` },
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
      name: 'transport',
      type: 'select',
      label: t('tool.transport'),
      placeholder: `${t('common.selectMsg')}${t('tool.transport')}`,
      options: [
        { value: 'streamable_http', label: 'Streamable' },
        { value: 'sse', label: 'SSE' },
      ],
      rules: [{ required: true, message: `${t('common.selectMsg')}${t('tool.transport')}` }],
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
    fetchSkillPackageData();
  }, []);

  const fetchSkillPackageData = async () => {
    try {
      const data = await fetchSkillPackages({ is_enabled: 1 });
      setSkillAssets(data.items || []);
    } catch (error) {
      console.error(t('common.fetchFailed'), error);
      message.error('技能包加载失败');
    }
  };

  const fetchData = async () => {
    setLoading(true);
    try {
      const data = await fetchTools();
      const uniqueTags = Array.from(new Set(data.flatMap((tool: any) => tool.tags))) as string[];
      setAllTags(uniqueTags.map((tag: string) => ({ value: tag, label: t(`tool.${tag}`) })));

      const tools = data.map((tool: any) => ({
        ...tool,
        // 内置工具的 name 是 ID 式名称，展示用翻译后的 display_name（自定义工具回退为 name）
        display_name: tool.display_name || tool.name,
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
          const { enable_auth, auth_token, transport, ...restValues } = values;
          const queryParams: ToolPayload = {
            ...restValues,
            name: values.name,
            icon: 'gongjuji',
            params: {
              name: values.name,
              url: values.url,
              transport: transport || 'streamable_http',
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
      // 编辑时：如果 params 存在，transport 默认为 sse（兼容旧数据）
      // 新增时：transport 默认为 streamable_http
      const transportValue = tool?.params 
        ? (tool.params.transport || 'sse') 
        : 'streamable_http';
      form.setFieldsValue({
        ...tool,
        url: tool?.params?.url,
        transport: transportValue,
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

  const skillCategoryOptions = Array.from(new Set(skillAssets.map((asset) => asset.category).filter(Boolean))) as string[];
  const filteredSkillAssets = skillAssets.filter((asset) => {
    const keyword = skillSearchKeyword.trim().toLowerCase();
    const matchesCategory = selectedSkillCategory === 'all' || asset.category === selectedSkillCategory;
    const matchesKeyword = !keyword || [
      asset.name,
      asset.package_id,
      asset.category || '',
      asset.description || '',
      (asset.required_tools || []).join(' '),
      (asset.triggers || []).join(' '),
    ].some((value) => value.toLowerCase().includes(keyword));
    return matchesCategory && matchesKeyword;
  });

  const splitInput = (value?: string) => (value || '')
    .split(/[,，\n]/)
    .map((item) => item.trim())
    .filter(Boolean);

  const handleAddSkillOk = async () => {
    const values = await addSkillForm.validateFields();
    if (!editingSkillAsset) return;
    await updateSkillPackage(editingSkillAsset.id, {
      name: values.name,
      category: values.category,
      description: values.description,
      required_tools: splitInput(values.recommendedTools),
      triggers: splitInput(values.triggers),
      is_enabled: values.is_enabled,
    });
    await fetchSkillPackageData();
    addSkillForm.resetFields();
    setEditingSkillAsset(null);
    setIsAddSkillModalVisible(false);
    message.success('技能包已更新');
  };

  const handleImportSkillOk = async () => {
    const file = (skillPackageFileList[0]?.originFileObj || skillPackageFileList[0]) as File | undefined;
    if (!file) {
      message.warning('请选择包含 skill.yaml 和 SKILL.md 的 ZIP 技能包');
      return;
    }
    await importSkillPackageZip(file);
    await fetchSkillPackageData();
    setSkillPackageFileList([]);
    setIsImportSkillModalVisible(false);
    message.success('技能包已导入');
  };

  const handleEditSkillAsset = (asset: SkillPackage) => {
    setEditingSkillAsset(asset);
    setIsAddSkillModalVisible(true);
    Promise.resolve().then(() => {
      addSkillForm.setFieldsValue({
        name: asset.name,
        category: asset.category,
        recommendedTools: (asset.required_tools || []).join(', '),
        description: asset.description,
        triggers: (asset.triggers || []).join('\n'),
        is_enabled: asset.is_enabled !== false,
      });
    });
  };

  const handleDeleteSkillAsset = (asset: SkillPackage) => {
    Modal.confirm({
      title: `删除技能包「${asset.name}」？`,
      content: '删除后不会再出现在技能包列表和智能体技能选择中。',
      onOk: async () => {
        await deleteSkillPackage(asset.id);
        await fetchSkillPackageData();
        message.success('技能包已删除');
      },
    });
  };

  const renderSkillCardMenu = (asset: SkillPackage) => (
    <Menu className={`${styles.menuContainer}`}>
      <Menu.Item key="edit">
        <span className="block w-full" onClick={() => handleEditSkillAsset(asset)}>编辑</span>
      </Menu.Item>
      <Menu.Item key="delete">
        <span className="block w-full text-red-500" onClick={() => handleDeleteSkillAsset(asset)}>删除</span>
      </Menu.Item>
    </Menu>
  );

  const renderAssetSwitcher = () => (
    <Segmented
      value={assetView}
      onChange={(value) => setAssetView(value as 'tools' | 'skills')}
      options={[
        { label: '工具列表', value: 'tools' },
        { label: '技能列表', value: 'skills' },
      ]}
    />
  );

  const renderSkillAssetControls = () => (
    <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
      <Select
        value={selectedSkillCategory}
        className="w-40"
        onChange={setSelectedSkillCategory}
        options={[
          { value: 'all', label: '技能类型' },
          ...skillCategoryOptions.map((category) => ({ value: category, label: category })),
        ]}
      />
      <Input.Search
        value={skillSearchKeyword}
        onChange={(event) => setSkillSearchKeyword(event.target.value)}
        placeholder="搜索技能名称或说明"
        allowClear
        className="w-64"
      />
      <Button onClick={() => setIsImportSkillModalVisible(true)}>导入技能包</Button>
      <Button
        type="primary"
        onClick={() => {
          setSkillPackageFileList([]);
          setIsImportSkillModalVisible(true);
        }}
      >
        新增技能包
      </Button>
    </div>
  );

  const renderSkillAssetToolbar = () => (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
      <div className="flex min-w-0 items-center gap-2">
        {renderAssetSwitcher()}
      </div>
      {renderSkillAssetControls()}
    </div>
  );

  const renderSkillAssetView = () => (
    <div className="mx-auto max-w-[1440px]" aria-label="技能资产">
      {renderSkillAssetToolbar()}
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-5">
        {filteredSkillAssets.length ? (
          <div className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-3 xl:grid-cols-4">
            {filteredSkillAssets.map((asset, index) => (
              <div
                key={`${asset.package_id}:${asset.version}`}
                className={`min-h-[172px] rounded-lg border p-4 transition-colors hover:border-[var(--color-primary)] ${index === 0 ? 'border-[var(--color-primary)] bg-[var(--color-primary-bg)]' : 'border-[var(--color-border)] bg-[var(--color-bg-1)]'}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex min-w-0 items-start gap-2.5">
                    <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-[var(--color-primary)] bg-[var(--color-bg-1)] text-base font-semibold text-[var(--color-primary)]">
                      {asset.name.slice(0, 1)}
                    </span>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="text-sm font-semibold text-[var(--color-text-1)]">{asset.name}</span>
                      </div>
                      <div className="mt-1 text-xs text-[var(--color-text-3)]">{asset.category}</div>
                    </div>
                  </div>
                  <Dropdown overlay={renderSkillCardMenu(asset) as React.ReactElement} trigger={['click']} placement="bottomRight">
                    <span className="cursor-pointer text-xl leading-none text-[var(--color-text-3)]">⋮</span>
                  </Dropdown>
                </div>
                <p className="mt-3 line-clamp-2 min-h-12 text-sm leading-6 text-[var(--color-text-2)]">{asset.description}</p>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  <Tag color={asset.source_type === 'builtin' ? 'blue' : 'default'}>{asset.source_type === 'builtin' ? '内置' : '导入'}</Tag>
                  {asset.triggers?.slice(0, 2).map((tag) => (
                    <Tag key={tag} color="green">{tag}</Tag>
                  ))}
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-1.5 text-xs leading-6 text-[var(--color-text-3)]">
                  <span className="font-medium">工具</span>
                  {(asset.required_tools || []).slice(0, 2).map((toolName) => (
                    <Tag key={toolName} color="green">{toolName}</Tag>
                  ))}
                  {(asset.required_tools || []).length > 2 && <Tag>+{(asset.required_tools || []).length - 2}</Tag>}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <Empty description="没有匹配的技能" />
        )}
      </div>
    </div>
  );

  return (
    <div className="w-full h-full">
      {assetView === 'skills' ? renderSkillAssetView() : (
        <EntityList<Tool>
          data={filteredToolData}
          nameField="display_name"
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
          toolbarPrefix={renderAssetSwitcher()}
          changeFilter={changeFilter}
          onCardClick={handleCardClick}
        />
      )}
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
                  {t('common.total')} {availableTools.length} {t('tool.items')}
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
      <Modal
        title="编辑技能包"
        open={isAddSkillModalVisible}
        onOk={handleAddSkillOk}
        onCancel={() => {
          setIsAddSkillModalVisible(false);
          setEditingSkillAsset(null);
          addSkillForm.resetFields();
        }}
        okText="保存修改"
        cancelText="取消"
        width={720}
      >
        <Form
          form={addSkillForm}
          layout="vertical"
          initialValues={{ is_enabled: true }}
        >
          <Form.Item name="name" label="技能名称" rules={[{ required: true, message: '请输入技能名称' }]}>
            <Input placeholder="例如：RCA 复盘" />
          </Form.Item>
          <Form.Item name="category" label="技能类型" rules={[{ required: true, message: '请输入技能类型' }]}>
            <Input placeholder="例如：Kubernetes / 异常诊断" />
          </Form.Item>
          <Form.Item name="recommendedTools" label="推荐工具" rules={[{ required: true, message: '请输入推荐工具' }]}>
            <Input placeholder="多个工具用逗号分隔，例如：kubernetes, 日志查询工具" />
          </Form.Item>
          <Form.Item name="description" label="技能简介" rules={[{ required: true, message: '请输入技能简介' }]}>
            <TextArea rows={3} placeholder="说明这个技能解决什么问题、适合什么场景" />
          </Form.Item>
          <Form.Item name="triggers" label="触发词">
            <TextArea rows={3} placeholder="每行一个触发词，例如：RCA、复盘、根因分析" />
          </Form.Item>
          <Form.Item name="is_enabled" valuePropName="checked">
            <Switch size="small" />
            <span className="ml-2 text-sm text-[var(--color-text-2)]">启用技能包</span>
          </Form.Item>
        </Form>
      </Modal>
      <Modal
        title="导入技能包"
        open={isImportSkillModalVisible}
        onOk={handleImportSkillOk}
        onCancel={() => {
          setIsImportSkillModalVisible(false);
          setSkillPackageFileList([]);
        }}
        okText="确认导入"
        cancelText="取消"
        width={760}
      >
        <div>
          <div className="mb-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-fill-1)] px-4 py-3 text-sm leading-6 text-[var(--color-text-2)]">
            上传 ZIP 技能包。包内必须包含 <code>skill.yaml</code> 和 <code>SKILL.md</code>，可选 <code>references/</code>、<code>templates/</code> 等目录。后端会校验路径穿越和危险执行配置，并保存到 server/.skill 运行时目录。
          </div>
          <Upload.Dragger
            accept=".zip"
            maxCount={1}
            fileList={skillPackageFileList}
            beforeUpload={(file) => {
              setSkillPackageFileList([file as UploadFile]);
              return false;
            }}
            onRemove={() => {
              setSkillPackageFileList([]);
            }}
          >
            <p className="ant-upload-text">点击或拖拽 ZIP 技能包到这里</p>
            <p className="ant-upload-hint">第一版支持本地 ZIP 上传；公开 Git 仓库导入后续接入同一导入器。</p>
          </Upload.Dragger>
        </div>
      </Modal>
      <Drawer
        title={selectedToolForDetail ? `${t('tool.title')} - ${selectedToolForDetail.display_name || selectedToolForDetail.name}` : t('common.viewDetails')}
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
                    {t('common.total')} {selectedToolForDetail.tools.length} {t('tool.items')}
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
