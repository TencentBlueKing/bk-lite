'use client';
import React, { useState, useEffect, useMemo } from 'react';
import { Form, message, Button, Menu, Modal, Drawer, Switch, Tooltip, Segmented, Upload, Input, Tag, Select } from 'antd';
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
import { Tool, ToolPayload } from '@/app/opspilot/types/tool';
import PermissionWrapper from "@/components/permission";
import styles from '@/app/opspilot/styles/common.module.scss';
import { useToolApi } from '@/app/opspilot/api/tool';
import { useSkillApi } from '@/app/opspilot/api/skill';
import type { SkillPackage } from '@/app/opspilot/types/skill';
import VariableList from '@/app/opspilot/components/tool/variableList';
import UrlInputWithButton from '@/app/opspilot/components/tool/urlInputWithButton';
import SkillPackageDetailDrawer from '@/app/opspilot/components/tool/SkillPackageDetailDrawer';
import AssetTagFilterBar from '@/app/opspilot/components/tool/assetTagFilterBar';
import Icon from '@/components/icon';
import UnifiedOpsCard from '@/app/opspilot/components/unified-ops-card';
import ListPageHeader from '@/components/list-page-header';
import CardGridSkeleton from '@/components/card-grid-skeleton';
import { collectTagChips, filterTaggedAssets, normalizeUserTags } from '@/app/opspilot/utils/assetTagFilter';

const ToolListPage: React.FC = () => {
  const { useForm } = Form;
  const { t } = useTranslation();
  const { selectedGroup } = useUserInfoContext();
  const { fetchTools, createTool, updateTool, deleteTool, fetchAvailableTools } = useToolApi();
  const { fetchSkillPackages, importSkillPackageZip, deleteSkillPackage, updateSkillPackage } = useSkillApi();
  const [loading, setLoading] = useState<boolean>(false);
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
  const [isModalVisible, setIsModalVisible] = useState<boolean>(false);
  const [selectedTool, setSelectedTool] = useState<Tool | null>(null);
  const [toolData, setToolData] = useState<Tool[]>([]);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
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
  const [editingSkillAsset, setEditingSkillAsset] = useState<SkillPackage | null>(null);
  const [isImportSkillModalVisible, setIsImportSkillModalVisible] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [skillPackageFileList, setSkillPackageFileList] = useState<UploadFile[]>([]);

  const iconTypes = ['yinliugongju-biaotiyouhua', 'yinliugongju-biaotifenxi', 'yinliugongju-dijiayinliu', 'gongjuqu', 'gongjuxiang', 'gongju1'];

  const getRandomIcon = () => {
    return iconTypes[Math.floor(Math.random() * iconTypes.length)];
  };

  const [form] = useForm();
  const [skillForm] = useForm();

  const labelForTag = (value: string, kind: 'system' | 'user') => {
    if (kind === 'system') return t(`tool.systemTags.${value}`, value);
    const legacy: Record<string, string> = {
      search: t('common.search'),
      general: t('tool.general'),
      maintenance: t('tool.maintenance'),
      media: t('tool.media'),
      collaboration: t('tool.collaboration'),
      other: t('tool.other'),
    };
    return legacy[value] || value;
  };

  const userTagOptions = (tools: Tool[]) => {
    const words = new Set<string>();
    tools.forEach((tool) => (tool.user_tags || []).forEach((tag) => words.add(tag)));
    return Array.from(words).map((tag) => ({ value: tag, label: labelForTag(tag, 'user') }));
  };

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
    ...(isBuiltIn ? [{
      name: 'system_tags_view',
      type: 'custom',
      label: t('tool.systemTagsReadonly'),
      component: (
        <div className="flex flex-wrap gap-2">
          {(selectedTool?.system_tags || []).length
            ? (selectedTool?.system_tags || []).map((tag) => (
              <Tag key={tag}>{labelForTag(tag, 'system')}</Tag>
            ))
            : <span className="text-xs text-[var(--color-text-4)]">{t('common.noData')}</span>}
        </div>
      ),
    }] : []),
    {
      name: 'user_tags',
      type: 'select',
      label: isBuiltIn ? t('tool.userTags') : t('tool.label'),
      placeholder: `${t('common.inputMsg')}${t('tool.label')}`,
      options: userTagOptions(toolData.filter((tool) => Boolean(tool.is_build_in) === isBuiltIn)),
      mode: 'tags',
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
            <span className="text-sm">{t('tool.basicAuth')}</span>
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
      message.error(t('tool.loadFailed'));
    } finally {
      setSkillAssetsLoading(false);
    }
  };

  const fetchData = async () => {
    setLoading(true);
    try {
      const data = await fetchTools();
      const tools = data.map((tool: any) => ({
        ...tool,
        display_name: tool.display_name || tool.name,
        description: tool.description_tr,
        icon: tool.icon || 'gongjuji',
        system_tags: tool.system_tags || [],
        user_tags: tool.user_tags || [],
        tags: [...(tool.system_tags || []), ...(tool.user_tags || [])],
        tagList: [
          ...(tool.system_tags || []).map((key: string) => labelForTag(key, 'system')),
          ...(tool.user_tags || []).map((key: string) => labelForTag(key, 'user')),
        ],
      }));

      setToolData(tools);
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
          const { enable_auth, auth_token, transport, user_tags, ...restValues } = values;
          const normalizedUserTags = normalizeUserTags(user_tags || []);
          if (selectedTool?.is_build_in) {
            await updateTool(selectedTool.id, {
              name: selectedTool.name,
              description: selectedTool.description,
              team: values.team,
              user_tags: normalizedUserTags,
              system_tags: selectedTool.system_tags || [],
            });
          } else {
            const queryParams: ToolPayload = {
              ...restValues,
              name: values.name,
              icon: 'gongjuji',
              user_tags: normalizedUserTags,
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
        user_tags: tool?.user_tags || [],
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

  const switchAssetView = (value: 'builtin' | 'mcp' | 'skills') => {
    setAssetView(value);
    setSelectedTags([]);
    setToolSearchKeyword('');
    setSkillSearchKeyword('');
  };

  const handleCardClick = (tool: Tool) => {
    setSelectedToolForDetail(tool);
  };

  const currentToolItems = assetView === 'builtin'
    ? toolData.filter((tool) => tool.is_build_in)
    : toolData.filter((tool) => !tool.is_build_in);

  const toolChips = collectTagChips(
    currentToolItems.map((tool) => ({ systemTags: tool.system_tags || [], userTags: tool.user_tags || [] })),
    labelForTag,
  );

  const skillChips = collectTagChips(
    skillAssets.map((asset) => ({ systemTags: asset.system_tags || [], userTags: asset.user_tags || [] })),
    labelForTag,
  );

  const filteredSkillAssets = filterTaggedAssets(skillAssets, {
    selectedTags,
    keyword: skillSearchKeyword,
    chips: skillChips,
    systemTags: (asset) => asset.system_tags || [],
    userTags: (asset) => asset.user_tags || [],
    name: (asset) => asset.display_name || asset.name,
    description: (asset) => asset.description_tr || asset.description || '',
    extraKeyword: (asset) => [
      asset.name,
      asset.package_id,
      asset.category || '',
      (asset.required_tools || []).join(' '),
      (asset.triggers || []).join(' '),
    ].join(' '),
  }).sort((left, right) => Number(Boolean(right.is_build_in) || right.source_type === 'builtin') - Number(Boolean(left.is_build_in) || left.source_type === 'builtin'));

  const handleImportSkillOk = async () => {
    const file = (skillPackageFileList[0]?.originFileObj || skillPackageFileList[0]) as File | undefined;
    if (!file) {
      message.warning(t('tool.requireSkillMd'));
      return;
    }
    setIsImporting(true);
    try {
      await importSkillPackageZip(file);
      await fetchSkillPackageData();
      setSkillPackageFileList([]);
      setIsImportSkillModalVisible(false);
      message.success(t('tool.importedSuccess'));
    } finally {
      setIsImporting(false);
    }
  };

  const handleDeleteSkillAsset = (asset: SkillPackage) => {
    const title = asset.display_name || asset.name;
    Modal.confirm({
      title: t('tool.deleteTitle', '删除技能包「{name}」？', { name: title }),
      content: t('tool.deleteContent'),
      onOk: async () => {
        await deleteSkillPackage(asset.id);
        await fetchSkillPackageData();
        message.success(t('tool.deletedSuccess'));
      },
    });
  };

  const renderAssetSwitcher = () => (
    <Segmented
      className="self-start"
      value={assetView}
      onChange={(value) => switchAssetView(value as 'builtin' | 'mcp' | 'skills')}
      options={[
        { label: t('tool.categoryBuiltin'), value: 'builtin' },
        { label: t('tool.categorySkills'), value: 'skills' },
        { label: 'MCP', value: 'mcp' },
      ]}
    />
  );

  const displayedTools = useMemo(() => {
    return filterTaggedAssets(currentToolItems, {
      selectedTags,
      keyword: toolSearchKeyword,
      chips: toolChips,
      systemTags: (tool) => tool.system_tags || [],
      userTags: (tool) => tool.user_tags || [],
      name: (tool) => tool.display_name || tool.name || '',
      description: (tool) => tool.description || '',
    });
  }, [currentToolItems, selectedTags, toolSearchKeyword, toolChips]);

  const headerSearch = (
    <Input.Search
      allowClear
      enterButton
      className="w-60"
      placeholder={
        assetView === 'skills'
          ? t('tool.searchPlaceholder')
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
          {t('tool.importPackage')}
        </Button>
      ) : null}
    </>
  );

  const renderSkillAssetView = () => (
    <div className="w-full" aria-label={t('tool.assetsLabel')}>
      <div className="mb-4 flex flex-col gap-3">
        {renderAssetSwitcher()}
        <AssetTagFilterBar chips={skillChips} selected={selectedTags} onChange={setSelectedTags} />
      </div>
      {skillAssetsLoading ? (
        <CardGridSkeleton count={6} />
      ) : filteredSkillAssets.length ? (
        <div className="grid w-full grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-6">
          {filteredSkillAssets.map((asset) => {
            const skillAssetKey = `${asset.package_id}:${asset.version}`;
            const canDeleteSkillAsset = !asset.is_build_in && asset.source_type !== 'builtin';
            const displayName = asset.display_name || asset.name;
            const displayDescription = asset.description_tr || asset.description || '';
            const skillMenu = (
              <Menu>
                <Menu.Item key="edit">
                  <PermissionWrapper requiredPermissions={['Edit']} instPermissions={asset.permissions}>
                    <span
                      className="block w-full"
                      onClick={() => {
                        setEditingSkillAsset(asset);
                        Promise.resolve().then(() => {
                          skillForm.setFieldsValue({
                            team: asset.team || [],
                            user_tags: asset.user_tags || [],
                          });
                        });
                      }}
                    >
                      {t('common.edit')}
                    </span>
                  </PermissionWrapper>
                </Menu.Item>
                {canDeleteSkillAsset ? (
                  <Menu.Item key="delete" danger>
                    <span className="block" onClick={() => handleDeleteSkillAsset(asset)}>
                      {t('common.delete')}
                    </span>
                  </Menu.Item>
                ) : null}
              </Menu>
            );

            return (
              <UnifiedOpsCard
                key={skillAssetKey}
                name={displayName}
                description={displayDescription}
                icon="jinengpeixun"
                meta={[
                  asset.is_build_in || asset.source_type === 'builtin' ? t('common.builtin') : null,
                  ...(asset.system_tags || []).map((tag) => labelForTag(tag, 'system')),
                  ...(asset.user_tags || []).map((tag) => labelForTag(tag, 'user')),
                  asset.category,
                  asset.version,
                ].filter(Boolean) as string[]}
                footer="none"
                menuOverlay={skillMenu}
                onClick={() => setSelectedSkillAssetForDetail(asset)}
              />
            );
          })}
        </div>
      ) : (
        <CompactEmptyState description={t('tool.noMatch')} />
      )}
    </div>
  );

  return (
    <div className="w-full h-full">
      <ListPageHeader
        title={t('tool.pageTitle')}
        description={t('tool.pageDescription')}
        actions={headerActions}
      />
      {assetView === 'skills' ? renderSkillAssetView() : (
        <>
          <div className="mb-4 flex flex-col gap-3">
            {renderAssetSwitcher()}
            <AssetTagFilterBar chips={toolChips} selected={selectedTags} onChange={setSelectedTags} />
          </div>
          <EntityList<Tool>
            data={displayedTools}
            nameField="display_name"
            showBuiltinTag={false}
            loading={loading}
            loadingContent={<CardGridSkeleton />}
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
              const meta = [...(tool.tagList || [])].filter(Boolean);
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
                    <div key={i} className="p-3 bg-[var(--color-fill-1)] border border-[var(--color-border)] rounded-lg animate-neutral-pulse">
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
        title={t('tool.importPackage')}
        open={isImportSkillModalVisible}
        onOk={handleImportSkillOk}
        onCancel={() => {
          setIsImportSkillModalVisible(false);
          setSkillPackageFileList([]);
        }}
        okText={t('tool.confirmImport')}
        cancelText={t('common.cancel')}
        confirmLoading={isImporting}
        width={760}
      >
        <div>
          <div className="mb-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-fill-1)] px-4 py-3 text-sm leading-6 text-[var(--color-text-2)]">
            {t('tool.uploadIntroBefore')}
            <code>SKILL.md</code>
            {t('tool.uploadIntroMiddle')}
            <code>skill.yaml</code>
            {t('tool.uploadIntroFiles')}
            <code>references/</code>
            {t('tool.uploadIntroFiles')}
            <code>templates/</code>
            {t('tool.uploadIntroAfter')}
            <code>skill.yaml</code>
            {t('tool.uploadIntroTail')}
            <code>SKILL.md</code>
            {t('tool.uploadIntroEnd')}
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
            <p className="ant-upload-text">{t('tool.uploadDropzone')}</p>
            <p className="ant-upload-hint">{t('tool.uploadHint')}</p>
          </Upload.Dragger>
        </div>
      </Modal>
      <Modal
        title={t('common.edit')}
        open={!!editingSkillAsset}
        onCancel={() => setEditingSkillAsset(null)}
        onOk={async () => {
          if (!editingSkillAsset) return;
          const values = await skillForm.validateFields();
          await updateSkillPackage(editingSkillAsset.id, {
            package_id: editingSkillAsset.package_id,
            name: editingSkillAsset.name,
            version: editingSkillAsset.version,
            description: editingSkillAsset.description,
            team: values.team,
            user_tags: normalizeUserTags(values.user_tags || []),
            system_tags: editingSkillAsset.system_tags || [],
          });
          await fetchSkillPackageData();
          setEditingSkillAsset(null);
          message.success(t('common.saveSuccess'));
        }}
        okText={t('common.save')}
        cancelText={t('common.cancel')}
      >
        <Form form={skillForm} layout="vertical">
          {editingSkillAsset?.is_build_in || editingSkillAsset?.source_type === 'builtin' ? (
            <Form.Item label={t('tool.systemTagsReadonly')}>
              <div className="flex flex-wrap gap-2">
                {(editingSkillAsset.system_tags || []).length
                  ? (editingSkillAsset.system_tags || []).map((tag) => (
                    <Tag key={tag}>{labelForTag(tag, 'system')}</Tag>
                  ))
                  : <span className="text-xs text-[var(--color-text-4)]">{t('common.noData')}</span>}
              </div>
            </Form.Item>
          ) : null}
          <Form.Item name="user_tags" label={editingSkillAsset?.is_build_in ? t('tool.userTags') : t('tool.label')}>
            <Select
              mode="tags"
              options={Array.from(new Set(skillAssets.flatMap((asset) => asset.user_tags || []))).map((tag) => ({
                value: tag,
                label: labelForTag(tag, 'user'),
              }))}
            />
          </Form.Item>
          <Form.Item name="team" label={t('common.group')} rules={[{ required: true, message: `${t('common.selectMsg')}${t('common.group')}` }]}>
            <GroupTreeSelect multiple placeholder={`${t('common.selectMsg')}${t('common.group')}`} />
          </Form.Item>
        </Form>
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
