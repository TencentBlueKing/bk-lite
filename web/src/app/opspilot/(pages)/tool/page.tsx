'use client';
import React, { useState, useEffect, useMemo } from 'react';
import { Form, message, Button, Menu, Modal, Drawer, Switch, Tooltip, Segmented, Upload, Input, Select } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import CompactEmptyState from '@/components/compact-empty-state';
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
import SkillPackageDetailDrawer from '@/app/opspilot/components/tool/SkillPackageDetailDrawer';
import Icon from '@/components/icon';
import UnifiedOpsCard from '@/app/opspilot/components/unified-ops-card';
import OpsPilotListPageHeader from '@/app/opspilot/components/opspilot-list-page-header';
import OpsPilotCardGridSkeleton from '@/app/opspilot/components/opspilot-card-grid-skeleton';
import { formatRelativeTime, pickEntityTimestamp } from '@/app/opspilot/utils/relativeTime';

const ToolListPage: React.FC = () => {
  const { useForm } = Form;
  const { t } = useTranslation();
  const { selectedGroup } = useUserInfoContext();
  const { fetchTools, createTool, updateTool, deleteTool, fetchAvailableTools } = useToolApi();
  const { fetchSkillPackages, importSkillPackageZip, deleteSkillPackage } = useSkillApi();
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
  const [assetView, setAssetView] = useState<'builtin' | 'mcp' | 'skills'>('builtin');
  const [skillAssets, setSkillAssets] = useState<SkillPackage[]>([]);
  const [skillAssetsLoading, setSkillAssetsLoading] = useState<boolean>(false);
  const [skillSearchKeyword, setSkillSearchKeyword] = useState('');
  const [toolSearchKeyword, setToolSearchKeyword] = useState('');
  const [selectedSkillAssetForDetail, setSelectedSkillAssetForDetail] = useState<SkillPackage | null>(null);
  const [isImportSkillModalVisible, setIsImportSkillModalVisible] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [skillPackageFileList, setSkillPackageFileList] = useState<UploadFile[]>([]);

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
    setSkillAssetsLoading(true);
    try {
      const data = await fetchSkillPackages({ is_enabled: 1 });
      setSkillAssets(data.items || []);
    } catch (error) {
      console.error(t('common.fetchFailed'), error);
      message.error('技能包加载失败');
    } finally {
      setSkillAssetsLoading(false);
    }
  };

  const fetchData = async () => {
    setLoading(true);
    try {
      const data = await fetchTools();
      const uniqueTags = Array.from(
        new Set(data.filter((tool: any) => !tool.is_build_in).flatMap((tool: any) => tool.tags))
      ) as string[];
      setAllTags(uniqueTags.map((tag: string) => ({ value: tag, label: t(`tool.${tag}`) })));

      const tools = data.map((tool: any) => ({
        ...tool,
        display_name: tool.display_name || tool.name,
        description: tool.description_tr,
        icon: tool.icon || 'gongjuji',
        tags: tool.tags,
        tagList: tool.tags.map((key: string) => t(`tool.${key}`))
      }));

      setToolData(tools);
      setFilteredToolData(tools.filter((tool: Tool) => !tool.is_build_in));
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
    const externalTools = toolData.filter((tool) => !tool.is_build_in);
    if (selectedTags.length === 0) {
      setFilteredToolData(externalTools);
    } else {
      const filteredData = externalTools.filter((tool) =>
        tool.tags.some((tag: string) => selectedTags.includes(tag))
      );
      setFilteredToolData(filteredData);
    }
  };

  const handleCardClick = (tool: Tool) => {
    setSelectedToolForDetail(tool);
  };

  const filteredSkillAssets = skillAssets
    .filter((asset) => {
      const keyword = skillSearchKeyword.trim().toLowerCase();
      const matchesKeyword = !keyword || [
        asset.name,
        asset.package_id,
        asset.category || '',
        asset.description || '',
        (asset.required_tools || []).join(' '),
        (asset.triggers || []).join(' '),
      ].some((value) => value.toLowerCase().includes(keyword));
      return matchesKeyword;
    })
    .sort((left, right) => Number(right.source_type === 'builtin') - Number(left.source_type === 'builtin'));

  const handleImportSkillOk = async () => {
    const file = (skillPackageFileList[0]?.originFileObj || skillPackageFileList[0]) as File | undefined;
    if (!file) {
      message.warning('请选择包含 SKILL.md 的 ZIP 技能包');
      return;
    }
    setIsImporting(true);
    try {
      await importSkillPackageZip(file);
      await fetchSkillPackageData();
      setSkillPackageFileList([]);
      setIsImportSkillModalVisible(false);
      message.success('技能包已导入');
    } finally {
      setIsImporting(false);
    }
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

  const renderAssetSwitcher = () => (
    <Segmented
      value={assetView}
      onChange={(value) => setAssetView(value as 'builtin' | 'mcp' | 'skills')}
      options={[
        { label: '工具', value: 'builtin' },
        { label: '技能', value: 'skills' },
        { label: 'MCP', value: 'mcp' },
      ]}
    />
  );

  const displayedTools = useMemo(() => {
    const base =
      assetView === 'builtin'
        ? toolData.filter((tool) => tool.is_build_in)
        : filteredToolData;
    const keyword = toolSearchKeyword.trim().toLowerCase();
    if (!keyword) return base;
    return base.filter((tool) =>
      (tool.display_name || tool.name || '').toLowerCase().includes(keyword)
      || (tool.description || '').toLowerCase().includes(keyword),
    );
  }, [assetView, toolData, filteredToolData, toolSearchKeyword]);

  const headerSearch = (
    <Input.Search
      allowClear
      enterButton
      className="w-60"
      placeholder={
        assetView === 'skills'
          ? '搜索技能名称或说明'
          : `${t('common.search')}...`
      }
      value={assetView === 'skills' ? skillSearchKeyword : toolSearchKeyword}
      onChange={(event) => {
        const value = event.target.value;
        if (assetView === 'skills') setSkillSearchKeyword(value);
        else setToolSearchKeyword(value);
      }}
      onSearch={(value) => {
        if (assetView === 'skills') setSkillSearchKeyword(value);
        else setToolSearchKeyword(value);
      }}
    />
  );

  const headerActions = (
    <>
      {headerSearch}
      {assetView === 'mcp' ? (
        <PermissionWrapper requiredPermissions={['Add']}>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => showModal(null)}>
            {t('common.new')}
          </Button>
        </PermissionWrapper>
      ) : null}
      {assetView === 'skills' ? (
        <Button type="primary" onClick={() => setIsImportSkillModalVisible(true)}>
          导入技能包
        </Button>
      ) : null}
    </>
  );

  const renderSkillAssetView = () => (
    <div className="w-full" aria-label="技能资产">
      <div className="mb-4">{renderAssetSwitcher()}</div>
      {skillAssetsLoading ? (
        <OpsPilotCardGridSkeleton count={6} />
      ) : filteredSkillAssets.length ? (
        <div className="grid w-full grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-6">
          {filteredSkillAssets.map((asset) => {
            const skillAssetKey = `${asset.package_id}:${asset.version}`;
            const canDeleteSkillAsset = asset.source_type !== 'builtin';
            const deleteMenu = canDeleteSkillAsset ? (
              <Menu>
                <Menu.Item key="delete" danger>
                  <span
                    className="block"
                    onClick={() => handleDeleteSkillAsset(asset)}
                  >
                    删除
                  </span>
                </Menu.Item>
              </Menu>
            ) : undefined;

            return (
              <UnifiedOpsCard
                key={skillAssetKey}
                name={asset.name}
                description={asset.description || ''}
                icon="jinengpeixun"
                updatedAt={formatRelativeTime(pickEntityTimestamp(asset), t) || undefined}
                meta={[asset.category, asset.version].filter(Boolean) as string[]}
                footer="none"
                menuOverlay={deleteMenu}
                onClick={() => setSelectedSkillAssetForDetail(asset)}
              />
            );
          })}
        </div>
      ) : (
        <CompactEmptyState description="没有匹配的技能" />
      )}
    </div>
  );

  return (
    <div className="w-full h-full">
      <OpsPilotListPageHeader
        title={t('tool.pageTitle')}
        description={t('tool.pageDescription')}
        actions={headerActions}
      />
      {assetView === 'skills' ? renderSkillAssetView() : (
        <>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            {renderAssetSwitcher()}
            {assetView === 'mcp' ? (
              <Select
                allowClear
                mode="multiple"
                maxTagCount="responsive"
                className="w-[170px]"
                placeholder={`${t('common.select')}...`}
                options={allTags}
                disabled={loading}
                loading={loading}
                onChange={changeFilter}
              />
            ) : null}
          </div>
          <EntityList<Tool>
            data={displayedTools}
            nameField="display_name"
            showBuiltinTag={false}
            loading={loading}
            loadingContent={<OpsPilotCardGridSkeleton />}
            search={false}
            hideToolbar
            menuActions={assetView === 'mcp' ? menuActions : undefined}
            singleActionType="button"
            singleAction={assetView === 'builtin' ? () => ({
              text: t('common.edit'),
              onClick: showModal,
            }) : undefined}
            onCardClick={handleCardClick}
            renderCard={(tool) => {
              const title = tool.display_name || tool.name;
              const meta = [
                ...(tool.tagList || []),
                tool.is_build_in ? t('common.builtin') : t('common.externalApp'),
              ].filter(Boolean);
              const menu =
                assetView === 'mcp'
                  ? menuActions(tool)
                  : assetView === 'builtin'
                    ? (
                      <Menu className={`${styles.menuContainer}`}>
                        <Menu.Item key="edit">
                          <PermissionWrapper
                            requiredPermissions={['Edit']}
                            instPermissions={tool.permissions}
                          >
                            <span className="block w-full" onClick={() => showModal(tool)}>
                              {t('common.edit')}
                            </span>
                          </PermissionWrapper>
                        </Menu.Item>
                      </Menu>
                    )
                    : undefined;

              return (
                <UnifiedOpsCard
                  name={title}
                  description={tool.description || ''}
                  icon={tool.icon || 'gongjuji'}
                  updatedAt={formatRelativeTime(pickEntityTimestamp(tool), t) || undefined}
                  meta={meta}
                  footer="none"
                  menuOverlay={menu}
                  onClick={() => handleCardClick(tool)}
                />
              );
            }}
          />
        </>
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
        title="导入技能包"
        open={isImportSkillModalVisible}
        onOk={handleImportSkillOk}
        onCancel={() => {
          setIsImportSkillModalVisible(false);
          setSkillPackageFileList([]);
        }}
        okText="确认导入"
        cancelText="取消"
        confirmLoading={isImporting}
        width={760}
      >
        <div>
          <div className="mb-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-fill-1)] px-4 py-3 text-sm leading-6 text-[var(--color-text-2)]">
            上传 ZIP 技能包。包内必须包含 <code>SKILL.md</code>，可选 <code>skill.yaml</code>、<code>references/</code>、<code>templates/</code> 等目录。没有 <code>skill.yaml</code> 时会读取 <code>SKILL.md</code> 顶部 YAML frontmatter，或从标题和目录名推导基础信息。
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
      <SkillPackageDetailDrawer
        asset={selectedSkillAssetForDetail}
        open={!!selectedSkillAssetForDetail}
        onClose={() => setSelectedSkillAssetForDetail(null)}
      />
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
