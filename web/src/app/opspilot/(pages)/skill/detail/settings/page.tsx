'use client';

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Form, Input, Select, Switch, Button, InputNumber, message, Modal, Checkbox } from 'antd';
import { PlusOutlined, DeleteOutlined, SendOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useSearchParams } from 'next/navigation';
import CustomChatSSE from '@/app/opspilot/components/custom-chat-sse';
import CompactEmptyState from '@/components/compact-empty-state';
import SearchActionBar from '@/components/search-action-bar';
import PermissionWrapper from '@/components/permission';
import GroupTreeSelect from '@/components/group-tree-select';
import { SkillPackage, SkillPackageParam } from '@/app/opspilot/types/skill';
import { SelectTool } from '@/app/opspilot/types/tool';
import ToolSelector from '@/app/opspilot/components/skill/toolSelector';
import SkillPackageParamsModal, {
  countFilledParams,
  listMissingRequiredParams,
  mergeDeclaredParams,
  resolvePackageVariables,
  withResolvedVariables,
} from '@/app/opspilot/components/skill/skillPackageParamsModal';
import EditablePasswordField from '@/components/dynamic-form/editPasswordField';
import { useSkillApi } from '@/app/opspilot/api/skill';
import { useWikiApi } from '@/app/opspilot/api/wiki';
import { WikiKnowledgeBase } from '@/app/opspilot/types/wiki';
import { useSkill } from '@/app/opspilot/context/skillContext';
import { notifyWebchatAppsChanged } from '@/app/(core)/components/global-webchat/apps-changed';
import { getModelOptionText, renderModelOptionLabel } from '@/app/opspilot/utils/modelOption';
import {
  buildSkillSaveTools,
  buildStudioRuntimeTools,
  normalizeMonitorToolConfigs,
} from '@/app/opspilot/utils/monitorToolConfig';
import Icon from '@/components/icon';
import SkillTemperatureField from './SkillTemperatureField';
import OpsPilotStudioWorkbenchSkeleton from '@/app/opspilot/components/opspilot-studio-workbench-skeleton';

const { Option } = Select;
const { TextArea } = Input;

const getPackageKey = (pkg: SkillPackage) => String(pkg.id || `${pkg.package_id}:${pkg.version}`);

const getPackageRequiredTools = (pkg: SkillPackage) => pkg.required_tools || [];

const SkillSettingsPage: React.FC = () => {
  const [form] = Form.useForm();
  const { t } = useTranslation();
  const { fetchSkillDetail, fetchLlmModels, fetchSkillPackages, saveSkillDetail } = useSkillApi();
  const { fetchKnowledgeBases } = useWikiApi();
  const { refreshSkillInfo } = useSkill();
  const searchParams = useSearchParams();
  const id = searchParams ? searchParams.get('id') : null;
  // 管理组织（group 字段）当前值：自动并入使用组织、且在使用组织里锁定不可删
  const manageGroup: number[] = Form.useWatch('group', form) || [];
  const selectedModelId = Form.useWatch('llmModel', form);

  const [temperature, setTemperature] = useState(0.7);
  const [initialMessages] = useState<any[]>([]); // 稳定的空数组引用

  const [chatHistoryEnabled, setChatHistoryEnabled] = useState(true);
  const [llmModels, setLlmModels] = useState<{ id: number, name: string, enabled: boolean, llm_model_type: string, vendor_name?: string }[]>([]);
  const [pageLoading, setPageLoading] = useState({
    llmModelsLoading: true,
    formDataLoading: true,
  });
  const [saveLoading, setSaveLoading] = useState(false);
  const [quantity, setQuantity] = useState<number>(10);
  const [selectedTools, setSelectedTools] = useState<SelectTool[]>([]);
  const [skillPermissions, setSkillPermissions] = useState<string[]>([]);
  const [guideValue, setGuideValue] = useState<string>('');
  const [hasInvalidParamKeys, setHasInvalidParamKeys] = useState(false);
  const [wikiKbs, setWikiKbs] = useState<WikiKnowledgeBase[]>([]);
  const [availableSkillAssets, setAvailableSkillAssets] = useState<SkillPackage[]>([]);
  const [selectedSkillAssetKeys, setSelectedSkillAssetKeys] = useState<string[]>([]);
  const [isSkillPickerOpen, setIsSkillPickerOpen] = useState(false);
  const [skillPickerKeyword, setSkillPickerKeyword] = useState('');
  const [draftSkillAssetKeys, setDraftSkillAssetKeys] = useState<string[]>([]);
  const [skillPackageParams, setSkillPackageParams] = useState<Record<string, SkillPackageParam[]>>({});
  const [editingSkillPackage, setEditingSkillPackage] = useState<SkillPackage | null>(null);
  const [pendingRemoveAsset, setPendingRemoveAsset] = useState<SkillPackage | null>(null);

  const currentModelName = useMemo(() => {
    if (!selectedModelId) return '';
    const m = llmModels.find((item) => item.id === selectedModelId);
    return m ? m.name : '';
  }, [selectedModelId, llmModels]);

  const syncSkillParamsFromPrompt = useCallback((promptText: string) => {
    const validRegex = /\{\{([a-zA-Z][a-zA-Z0-9_]*)\}\}/g;
    const allBracketRegex = /\{\{(.+?)\}\}/g;
    const keysInPrompt: string[] = [];
    let match;
    while ((match = validRegex.exec(promptText)) !== null) {
      if (!keysInPrompt.includes(match[1])) {
        keysInPrompt.push(match[1]);
      }
    }
    // Detect invalid keys (e.g. Chinese characters)
    const allKeys: string[] = [];
    while ((match = allBracketRegex.exec(promptText)) !== null) {
      allKeys.push(match[1]);
    }
    setHasInvalidParamKeys(allKeys.some((k) => !/^[a-zA-Z][a-zA-Z0-9_]*$/.test(k)));

    const currentParams: { key: string; value: string; type: string }[] =
      form.getFieldValue('skill_params') || [];
    const existingMap = new Map(currentParams.map((p) => [p.key, p]));
    const newParams = keysInPrompt.map((k) =>
      existingMap.get(k) || { key: k, value: '', type: 'text' }
    );
    form.setFieldValue('skill_params', newParams);
  }, [form]);

  useEffect(() => {
    const fetchFormData = async () => {
      try {
        const data = await fetchSkillDetail(id);
        const initialGuide = '您好，请问有什么可以帮助您的吗？可以点击如下问题进行快速提问。\n[问题1]\n[问题2]';
        form.setFieldsValue({
          name: data.name,
          group: data.team,
          // 空数组不能用 ?? 回退；保证管理组织至少进入使用组织
          usage_team: (Array.isArray(data.usage_team) && data.usage_team.length > 0)
            ? data.usage_team
            : (data.team || []),
          introduction: data.introduction,
          llmModel: data.llm_model,
          prompt: data.skill_prompt,
          guide: data.guide || initialGuide,
          temperature: data.temperature ?? 0.7,
          show_think: data.show_think ?? true,
          enable_suggest: data.enable_suggest,
          enable_query_rewrite: data.enable_query_rewrite,
          wiki_knowledge_bases: data.wiki_knowledge_bases || [],
          skill_params: data.skill_params || [],
        });
        setGuideValue(data.guide || initialGuide);
        setTemperature(data.temperature ?? 0.7);
        setChatHistoryEnabled(data.enable_conversation_history ?? true);
        setQuantity(data.conversation_window_size ?? 10);
        setSelectedTools(normalizeMonitorToolConfigs((data.tools || []) as SelectTool[]));
        const packages = (data.skill_packages || []) as SkillPackage[];
        setSelectedSkillAssetKeys(packages.map(getPackageKey));
        setSkillPackageParams(data.skill_package_params || {});
        setSkillPermissions(data.permissions || []);
      } catch (error) {
        console.error(t('common.fetchFailed'), error);
      } finally {
        setPageLoading(prev => ({ ...prev, formDataLoading: false }));
      }
    };

    const fetchInitialData = async () => {
      if (!id) return;
      try {
        const [llmModelsData, skillPackageData] = await Promise.all([
          fetchLlmModels(),
          fetchSkillPackages({ is_enabled: 1 }),
        ]);
        setLlmModels(llmModelsData as { id: number; name: string; enabled: boolean; llm_model_type: string; vendor_name?: string; }[]);
        setAvailableSkillAssets((skillPackageData.items || []).map(withResolvedVariables));
        fetchKnowledgeBases()
          .then(setWikiKbs)
          .catch(() => undefined);
        fetchFormData();
      } catch (error) {
        console.error(t('common.fetchFailed'), error);
      } finally {
        setPageLoading(prev => ({ ...prev, llmModelsLoading: false }));
      }
    };

    fetchInitialData();
  }, [id]);

  const allLoading = Object.values(pageLoading).some(loading => loading);

  useEffect(() => {
    const current = (form.getFieldValue('usage_team') || []).map(Number).filter((n: number) => !Number.isNaN(n));
    const manage = (manageGroup || []).map(Number).filter((n: number) => !Number.isNaN(n));
    const merged = Array.from(new Set([...manage, ...current]));
    if (JSON.stringify(merged) !== JSON.stringify(current)) {
      form.setFieldsValue({ usage_team: merged });
    }
  }, [JSON.stringify(manageGroup)]);

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      const payload = {
        name: values.name,
        team: values.group,
        usage_team: values.usage_team,
        introduction: values.introduction,
        llm_model: values.llmModel,
        skill_prompt: values.prompt,
        enable_conversation_history: chatHistoryEnabled,
        conversation_window_size: chatHistoryEnabled ? quantity : undefined,
        temperature: temperature,
        show_think: values.show_think,
        guide: values.guide,
        tools: buildSkillSaveTools(selectedTools),
        enable_suggest: values.enable_suggest,
        enable_query_rewrite: values.enable_query_rewrite,
        skill_params: (values.skill_params || []).filter((p: any) => p && p.key),
        wiki_knowledge_bases: values.wiki_knowledge_bases || [],
        skill_package_params: skillPackageParams,
        skill_packages: effectiveSkillCapabilityProfiles.map((pkg) => ({
          id: pkg.id,
          package_id: pkg.package_id,
          name: pkg.name,
          version: pkg.version,
          description: pkg.description,
          category: pkg.category,
          required_tools: pkg.required_tools || [],
          triggers: pkg.triggers || [],
        })),
      };
      setSaveLoading(true);
      await saveSkillDetail(id, payload);
      const missingOnSave = effectiveSkillCapabilityProfiles.flatMap((pkg) =>
        listMissingRequiredParams(pkg, skillPackageParams[pkg.package_id]).map((name) => `${pkg.name} / ${name}`)
      );
      if (missingOnSave.length > 0) {
        message.warning(t('skill.skillPackageParams.saveWarning', '以下技能包缺少必填变量，运行时将不可用：{names}', { names: missingOnSave.join('；') }));
      } else {
        message.success(t('common.saveSuccess'));
      }
      refreshSkillInfo();
      notifyWebchatAppsChanged();
    } catch (error) {
      console.error(t('common.saveFailed'), error);
    } finally {
      setSaveLoading(false);
    }
  };

  const handleSendMessage = async (userMessage: string, currentMessages: any[] = [], userMessageObj?: any): Promise<{
    url: string;
    payload: any;
    interruptRequest?: {
      enabled: boolean;
      url: string;
      reason?: string;
    };
  } | null> => {
    try {
      const values = await form.validateFields();

      const chatHistory = chatHistoryEnabled && quantity
        ? currentMessages.slice(-quantity).map(msg => ({
          message: msg.content,
          event: msg.role
        }))
        : [];

      // Build user_message array with images and text
      let userMessageArray: any[];
      if (userMessageObj?.images && userMessageObj.images.length > 0) {
        // Format: [{"type": "image_url", "image_url": "..."}, ..., {"type": "message", "message": "..."}]
        userMessageArray = [
          ...userMessageObj.images.map((img: any) => ({
            type: 'image_url',
            image_url: img.url
          })),
          {
            type: 'message',
            message: userMessage
          }
        ];
      } else {
        // No images, just text message
        userMessageArray = [{
          type: 'message',
          message: userMessage
        }];
      }

      const payload: any = {
        user_message: userMessageArray,
        llm_model: values.llmModel,
        skill_prompt: values.prompt,
        skill_name: values.name,
        skill_id: id,
        enable_suggest: values.enable_suggest,
        enable_query_rewrite: values.enable_query_rewrite,
        skill_params: (values.skill_params || []).filter((p: any) => p && p.key),
        skill_package_params: skillPackageParams,
        skill_packages: effectiveSkillCapabilityProfiles.map((pkg) => ({
          id: pkg.id,
          package_id: pkg.package_id,
          name: pkg.name,
          version: pkg.version,
          description: pkg.description,
          category: pkg.category,
          required_tools: pkg.required_tools || [],
          triggers: pkg.triggers || [],
        })),
        chat_history: chatHistory,
        conversation_window_size: chatHistoryEnabled ? quantity : undefined,
        temperature: temperature,
        show_think: values.show_think,
        tools: buildStudioRuntimeTools(selectedTools),
        skill_type: 1,
        group: values.group?.[0],
      };

      return {
        url: '/api/proxy/opspilot/model_provider_mgmt/llm/execute_agui/',
        payload,
        interruptRequest: {
          enabled: true,
          url: '/api/proxy/opspilot/bot_mgmt/interrupt_chat_flow_execution/',
          reason: 'user_manual'
        }
      };
    } catch (error) {
      // Display first error message when form validation fails
      if (error && typeof error === 'object' && 'errorFields' in error) {
        const errorFields = (error as any).errorFields;
        if (errorFields && errorFields.length > 0) {
          const firstError = errorFields[0];
          message.error(firstError.errors[0]);
        }
      } else {
        message.error(t('skill.formValidationFailed'));
      }
      return null;
    }
  };

  const handleTemperatureChange = (value: number) => {
    setTemperature(value);
    form.setFieldsValue({ temperature: value });
  };

  const effectiveSkillCapabilityProfiles = useMemo(() => {
    return selectedSkillAssetKeys
      .map((key) => availableSkillAssets.find((pkg) => getPackageKey(pkg) === key))
      .filter((asset): asset is SkillPackage => !!asset);
  }, [availableSkillAssets, selectedSkillAssetKeys]);

  const filteredAvailableSkillAssets = useMemo(() => {
    const keyword = skillPickerKeyword.trim().toLowerCase();
    if (!keyword) return availableSkillAssets;

    return availableSkillAssets.filter((asset) => [
      asset.name,
      asset.category,
      asset.description,
      asset.package_id,
      ...(asset.triggers || []),
      ...getPackageRequiredTools(asset),
    ].join(' ').toLowerCase().includes(keyword));
  }, [availableSkillAssets, skillPickerKeyword]);

  const openSkillPicker = () => {
    setDraftSkillAssetKeys(selectedSkillAssetKeys);
    setSkillPickerKeyword('');
    setIsSkillPickerOpen(true);
  };

  const handleConfirmSkillPicker = () => {
    setSelectedSkillAssetKeys(draftSkillAssetKeys);
    // 新挂载的包立刻按声明预填空行，避免打开弹窗时看起来像「0 个内置参数」
    setSkillPackageParams((prev) => {
      const next = { ...prev };
      for (const key of draftSkillAssetKeys) {
        const pkg = availableSkillAssets.find((item) => getPackageKey(item) === key);
        if (!pkg?.package_id) continue;
        const existing = next[pkg.package_id];
        if (existing && existing.length > 0) continue;
        const declared = resolvePackageVariables(pkg);
        if (!declared.length) continue;
        next[pkg.package_id] = mergeDeclaredParams(withResolvedVariables(pkg), existing || []);
      }
      return next;
    });
    setIsSkillPickerOpen(false);
  };

  const handleRemoveSkillAsset = (asset: SkillPackage) => {
    if (countFilledParams(skillPackageParams[asset.package_id]) === 0) {
      setSelectedSkillAssetKeys((prev) => prev.filter((key) => key !== getPackageKey(asset)));
      if (asset.package_id) {
        setSkillPackageParams((prev) => {
          if (!(asset.package_id in prev)) return prev;
          const next = { ...prev };
          delete next[asset.package_id];
          return next;
        });
      }
      return;
    }
    setPendingRemoveAsset(asset);
  };

  const confirmRemoveSkillAsset = (dropParams: boolean) => {
    if (!pendingRemoveAsset) return;
    const assetKey = getPackageKey(pendingRemoveAsset);
    const packageId = pendingRemoveAsset.package_id;
    setSelectedSkillAssetKeys((prev) => prev.filter((key) => key !== assetKey));
    if (dropParams && packageId) {
      setSkillPackageParams((prev) => {
        const next = { ...prev };
        delete next[packageId];
        return next;
      });
    }
    setPendingRemoveAsset(null);
  };

  const toggleDraftSkillAsset = (assetKey: string, checked: boolean) => {
    setDraftSkillAssetKeys((prev) => {
      if (checked) {
        return Array.from(new Set([...prev, assetKey]));
      }
      return prev.filter((key) => key !== assetKey);
    });
  };

  const renderSkillPackageSelector = () => (
    <div className="py-2.5 border-b border-[var(--color-fill-2)]/60">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <span className="text-[13px] font-medium text-[var(--color-text-1)]">技能包</span>
          {effectiveSkillCapabilityProfiles.length > 0 && (
            <span className="inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-[var(--color-count-bg)] px-1.5 text-[11px] font-medium tabular-nums leading-none text-[var(--color-count)]">
              {effectiveSkillCapabilityProfiles.length}
            </span>
          )}
        </div>
        <Button size="small" type="link" icon={<PlusOutlined />} onClick={openSkillPicker} className="px-0 text-xs">
          添加技能包
        </Button>
      </div>
      <p className="text-xs text-[var(--color-text-3)] mb-2.5 mt-0">挂载场景技能包，注入专业运维处理逻辑与提示规则</p>
      {effectiveSkillCapabilityProfiles.length === 0 ? (
        <div className="text-xs text-[var(--color-text-4)] py-1">
          暂未挂载技能包，可点击右上角「添加技能包」进行挂载
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 pt-1">
          {effectiveSkillCapabilityProfiles.map((asset) => {
            const resolvedAsset = withResolvedVariables(asset);
            const assetKey = getPackageKey(resolvedAsset);
            const params = skillPackageParams[resolvedAsset.package_id] || [];
            const missing = listMissingRequiredParams(resolvedAsset, params);
            const filled = countFilledParams(params);
            const declaredCount = resolvePackageVariables(resolvedAsset).length;
            const hasIssue = missing.length > 0;
            const hint = declaredCount > 0
              ? t('skill.skillPackageParams.buttonHint', '技能包声明 {declared} 项，已配置 {filled} 项', { declared: declaredCount, filled })
              : t('skill.skillPackageParams.buttonHintCustom', '自定义变量 {filled} 项', { filled });
            return (
              <div
                key={assetKey}
                className={`flex flex-col rounded-lg p-2.5 transition-all ${
                  hasIssue
                    ? 'border border-orange-300 bg-orange-50/40 dark:border-orange-800 dark:bg-orange-950/20'
                    : 'bg-[var(--color-fill-1)]/70 hover:bg-[var(--color-fill-2)]'
                }`}
              >
                <div className="flex w-full items-center justify-between">
                  <div className="flex min-w-0 items-center gap-1.5">
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-[var(--color-bg)] text-[var(--color-primary)] shadow-2xs">
                      <Icon type="jinengpeixun" className="text-xs" />
                    </span>
                    <span className="truncate text-xs font-medium text-[var(--color-text-1)]" title={resolvedAsset.name}>
                      {resolvedAsset.name}
                    </span>
                  </div>
                  <div className="ml-2 flex shrink-0 items-center gap-1">
                    <Button
                      type={hasIssue ? 'primary' : 'link'}
                      danger={hasIssue}
                      size="small"
                      className="h-6 px-1 text-[11px]"
                      title={hasIssue ? t('skill.skillPackageParams.missingRequired', '缺少必填变量：{names}', { names: missing.join('、') }) : hint}
                      onClick={() => setEditingSkillPackage(resolvedAsset)}
                    >
                      {hasIssue
                        ? t('skill.skillPackageParams.buttonMissing', '缺 {count} 项', { count: missing.length })
                        : t('skill.skillPackageParams.button', '变量 {count}', { count: filled })}
                    </Button>
                    <DeleteOutlined
                      className="cursor-pointer p-1 text-xs text-[var(--color-text-4)] transition-colors hover:text-red-500"
                      onClick={() => handleRemoveSkillAsset(asset)}
                    />
                  </div>
                </div>
                {hasIssue && (
                  <div className="mt-1 text-[11px] text-orange-600 dark:text-orange-400 truncate" title={missing.join('、')}>
                    {t('skill.skillPackageParams.missingRequired', '缺少必填变量：{names}', { names: missing.join('、') })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );

  const renderSkillPickerModal = () => (
    <Modal
      title="选择技能包"
      open={isSkillPickerOpen}
      onOk={handleConfirmSkillPicker}
      onCancel={() => setIsSkillPickerOpen(false)}
      okText="确认选择"
      cancelText="取消"
      width={640}
    >
      <SearchActionBar
        spacing="flush"
        className="mb-3"
        searchProps={{
          allowClear: true,
          placeholder: '搜索技能包',
          value: skillPickerKeyword,
          onChange: (event) => setSkillPickerKeyword(event.target.value),
        }}
      />
      <div className="grid max-h-[420px] grid-cols-1 gap-3 overflow-y-auto pr-1 lg:grid-cols-2">
        {filteredAvailableSkillAssets.length === 0 ? (
          <div className="col-span-full">
            <CompactEmptyState description="没有匹配的技能包" />
          </div>
        ) : (
          filteredAvailableSkillAssets.map((asset) => {
            const assetKey = getPackageKey(asset);
            const checked = draftSkillAssetKeys.includes(assetKey);
            return (
              <label
                key={assetKey}
                className={`block min-h-[132px] cursor-pointer rounded-lg border p-4 transition ${
                  checked
                    ? 'border-[var(--color-primary)] bg-[var(--color-primary-bg-active)]'
                    : 'border-[var(--color-border-1)] bg-[var(--color-bg)] hover:border-[var(--color-primary-border)]'
                }`}
              >
                <div className="flex h-full items-start gap-3">
                  <Checkbox
                    checked={checked}
                    className="mt-0.5"
                    onChange={(event) => toggleDraftSkillAsset(assetKey, event.target.checked)}
                  />
                  <Icon type="jinengpeixun" className="shrink-0 text-3xl text-[var(--color-primary)]" />
                  <div className="flex min-w-0 flex-1 flex-col">
                    <div className="flex min-w-0 items-center gap-2">
                      <div className="truncate font-medium text-[var(--color-text-1)]">{asset.name}</div>
                    </div>
                    <p className="mt-1.5 line-clamp-2 min-h-10 text-xs leading-5 text-[var(--color-text-3)]">
                      {asset.description || '暂无描述'}
                    </p>
                    {asset.category && (
                      <div className="mt-auto pt-2 text-[11px] text-[var(--color-text-4)]">{asset.category}</div>
                    )}
                  </div>
                </div>
              </label>
            );
          })
        )}
      </div>
    </Modal>
  );

  return (
    <div className="relative h-full min-h-0 overflow-hidden">
      {renderSkillPickerModal()}
      <SkillPackageParamsModal
        open={!!editingSkillPackage}
        pkg={editingSkillPackage}
        items={editingSkillPackage ? (skillPackageParams[editingSkillPackage.package_id] || []) : []}
        onCancel={() => setEditingSkillPackage(null)}
        onOk={(nextItems) => {
          if (editingSkillPackage?.package_id) {
            setSkillPackageParams((prev) => ({
              ...prev,
              [editingSkillPackage.package_id]: nextItems,
            }));
          }
          setEditingSkillPackage(null);
        }}
      />
      <Modal
        title={t('skill.skillPackageParams.removeTitle')}
        open={!!pendingRemoveAsset}
        onCancel={() => setPendingRemoveAsset(null)}
        footer={[
          <Button key="cancel" onClick={() => setPendingRemoveAsset(null)}>
            {t('common.cancel')}
          </Button>,
          <Button key="keep" onClick={() => confirmRemoveSkillAsset(false)}>
            {t('skill.skillPackageParams.removeKeep')}
          </Button>,
          <Button key="drop" type="primary" danger onClick={() => confirmRemoveSkillAsset(true)}>
            {t('skill.skillPackageParams.removeDrop')}
          </Button>,
        ]}
      >
        {pendingRemoveAsset && (
          <p>
            {t(
              'skill.skillPackageParams.removeContent',
              '确认从本智能体移除 {name}？该技能包下已配置 {count} 个变量。',
              {
                name: pendingRemoveAsset.name,
                count: countFilledParams(skillPackageParams[pendingRemoveAsset.package_id]),
              },
            )}
          </p>
        )}
      </Modal>

      {allLoading ? (
        <OpsPilotStudioWorkbenchSkeleton />
      ) : (
        <div className="flex h-full min-h-0 gap-3.5">
          {/* 左栏：配置面板 */}
          <div className="flex w-1/2 min-h-0 flex-col h-full overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] shadow-2xs">
            {/* 配置面板 Header */}
            <div className="flex h-11 shrink-0 items-center justify-between border-b border-[var(--color-border-1)] px-4 bg-[var(--color-fill-1)]/60">
              <div className="flex items-center gap-2">
                <Icon type="shezhi" className="text-sm text-[var(--color-primary)]" />
                <span className="text-[13px] font-semibold text-[var(--color-text-1)]">{t('skill.settings.menu')}</span>
              </div>
              {id && (
                <span className="rounded bg-[var(--color-bg)] border border-[var(--color-border-1)] px-2 py-0.5 text-xs text-[var(--color-text-3)] font-mono">
                  ID: {id}
                </span>
              )}
            </div>

            {/* 配置面板表单滚动区 */}
            <div className="flex-1 min-h-0 overflow-y-auto px-5 py-4">
              <Form
                form={form}
                layout="horizontal"
                labelCol={{ flex: '0 0 96px' }}
                wrapperCol={{ flex: 1 }}
                colon={false}
                className="[&_.ant-form-item]:mb-3.5 [&_.ant-form-item-label]:pr-3 text-sm"
                initialValues={{ temperature: 0.7, show_think: true }}
              >
                {/* 1. 基本信息 */}
                <section className="mb-6">
                  <div className="mb-3.5 flex items-center gap-2">
                    <span className="h-3.5 w-1 rounded-full bg-[var(--color-primary)]" />
                    <span className="text-[13px] font-semibold text-[var(--color-text-1)]">
                      {t('skill.information')}
                    </span>
                  </div>

                  <Form.Item
                    label={t('common.name')}
                    name="name"
                    rules={[{ required: true, message: `${t('common.input')} ${t('common.name')}` }]}
                  >
                    <Input placeholder={t('common.name')} />
                  </Form.Item>

                  <Form.Item
                    label={t('skill.form.manageGroup')}
                    name="group"
                    rules={[{ required: true, message: `${t('common.selectMsg')}${t('skill.form.manageGroup')}` }]}
                  >
                    <GroupTreeSelect placeholder={`${t('common.selectMsg')}${t('skill.form.manageGroup')}`} />
                  </Form.Item>

                  <Form.Item
                    label={t('skill.form.usageGroup')}
                    name="usage_team"
                    tooltip={t('skill.form.usageGroupTip')}
                    rules={[{ required: true, message: `${t('common.selectMsg')}${t('skill.form.usageGroup')}` }]}
                  >
                    <GroupTreeSelect
                      placeholder={`${t('common.selectMsg')}${t('skill.form.usageGroup')}`}
                      lockedValues={manageGroup}
                    />
                  </Form.Item>

                  <Form.Item
                    label={t('skill.form.introduction')}
                    name="introduction"
                    rules={[{ required: true, message: `${t('common.input')} ${t('skill.form.introduction')}` }]}
                  >
                    <TextArea rows={3} placeholder={t('skill.form.introduction')} />
                  </Form.Item>
                </section>

                {/* 2. 模型与知识库 */}
                <section className="mb-6 border-t border-[var(--color-border-1)] pt-5">
                  <div className="mb-3.5 flex items-center gap-2">
                    <span className="h-3.5 w-1 rounded-full bg-[var(--color-primary)]" />
                    <span className="text-[13px] font-semibold text-[var(--color-text-1)]">
                      {t('skill.form.llmModel')}
                    </span>
                  </div>

                  <Form.Item
                    label={t('skill.form.llmModel')}
                    name="llmModel"
                    rules={[{ required: true, message: `${t('common.input')} ${t('skill.form.llmModel')}` }]}
                  >
                    <Select placeholder={`${t('common.selectMsg')}${t('skill.form.llmModel')}`}>
                      {llmModels.map(model => (
                        <Option key={model.id} value={model.id} disabled={!model.enabled} title={getModelOptionText(model)}>
                          {renderModelOptionLabel(model)}
                        </Option>
                      ))}
                    </Select>
                  </Form.Item>

                  <Form.Item label={t('wiki.title')} name="wiki_knowledge_bases">
                    <Select
                      mode="multiple"
                      allowClear
                      placeholder={t('wiki.title')}
                      options={wikiKbs.map((kb) => ({ value: kb.id, label: kb.name }))}
                    />
                  </Form.Item>

                  <Form.Item
                    label={t('skill.form.temperature')}
                    name="temperature"
                    tooltip={t('skill.form.temperatureTip')}
                  >
                    <SkillTemperatureField
                      value={temperature}
                      onChange={handleTemperatureChange}
                    />
                  </Form.Item>

                  {/* 规整无边框的 Setting Rows */}
                  <div className="divide-y divide-[var(--color-fill-2)]/60 pt-1">
                    <div className="flex items-center justify-between py-2.5">
                      <div>
                        <div className="text-[13px] font-medium text-[var(--color-text-1)]">{t('skill.form.showThought')}</div>
                        <div className="text-xs text-[var(--color-text-3)]">在回答中显示模型的推理思考过程</div>
                      </div>
                      <Form.Item name="show_think" valuePropName="checked" className="!mb-0" noStyle>
                        <Switch size="small" />
                      </Form.Item>
                    </div>
                    <div className="flex items-center justify-between py-2.5">
                      <div>
                        <div className="text-[13px] font-medium text-[var(--color-text-1)]">{t('skill.form.enableSuggest')}</div>
                        <div className="text-xs text-[var(--color-text-3)]">根据当前回答推荐用户可能感兴趣的后续提问</div>
                      </div>
                      <Form.Item name="enable_suggest" valuePropName="checked" className="!mb-0" noStyle>
                        <Switch size="small" />
                      </Form.Item>
                    </div>
                    <div className="flex items-center justify-between py-2.5">
                      <div>
                        <div className="text-[13px] font-medium text-[var(--color-text-1)]">{t('skill.form.problemOptimization')}</div>
                        <div className="text-xs text-[var(--color-text-3)]">{t('skill.form.problemOptimizationTip')}</div>
                      </div>
                      <Form.Item name="enable_query_rewrite" valuePropName="checked" className="!mb-0" noStyle>
                        <Switch size="small" />
                      </Form.Item>
                    </div>
                  </div>
                </section>

                {/* 3. 提示词与参数 */}
                <section className="mb-6 border-t border-[var(--color-border-1)] pt-5">
                  <div className="mb-3.5 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="h-3.5 w-1 rounded-full bg-[var(--color-primary)]" />
                      <span className="text-[13px] font-semibold text-[var(--color-text-1)]">{t('skill.form.prompt')}</span>
                    </div>
                    <span className="text-xs text-[var(--color-text-3)]">
                      支持 <code className="font-mono text-[var(--color-primary)]">{'{{param}}'}</code> 声明参数
                    </span>
                  </div>

                  <Form.Item
                    name="prompt"
                    tooltip={t('skill.form.promptTip')}
                    extra={hasInvalidParamKeys ? <span className="text-orange-500 text-xs">{t('skill.skillParams.invalidKeyWarning')}</span> : undefined}
                    rules={[{ required: true, message: `${t('common.input')} ${t('skill.form.prompt')}` }]}
                    className="!mb-3"
                  >
                    <TextArea
                      rows={5}
                      className="font-mono text-xs"
                      placeholder="定义智能体的身份角色、任务指引与执行规范..."
                      onChange={(e) => syncSkillParamsFromPrompt(e.target.value)}
                    />
                  </Form.Item>

                  <Form.Item label={t('skill.skillParams.title')} tooltip={t('skill.skillParams.tip')} className="!mb-0">
                    <Form.List name="skill_params">
                      {(fields) => (
                        <>
                          {fields.length === 0 ? (
                            <div className="py-2 text-xs text-[var(--color-text-4)]">
                              {t('skill.skillParams.emptyHint')}（{t('skill.skillParams.emptyExample')}）
                            </div>
                          ) : (
                            <div className="space-y-2 pt-1">
                              {fields.map(({ key, name, ...restField }) => (
                                <div key={key} className="flex items-center gap-2 rounded-lg bg-[var(--color-fill-1)]/50 p-2">
                                  <Form.Item
                                    {...restField}
                                    name={[name, 'key']}
                                    className="!mb-0 w-32 shrink-0"
                                    rules={[{ required: true, message: t('skill.skillParams.paramNamePlaceholder') }]}
                                  >
                                    <Input placeholder={t('skill.skillParams.paramNamePlaceholder')} disabled className="text-xs font-mono" />
                                  </Form.Item>
                                  <Form.Item
                                    noStyle
                                    shouldUpdate={(prev, cur) =>
                                      prev?.skill_params?.[name]?.type !== cur?.skill_params?.[name]?.type
                                    }
                                  >
                                    {() => {
                                      const paramType = form.getFieldValue(['skill_params', name, 'type']) || 'text';
                                      return (
                                        <Form.Item
                                          {...restField}
                                          name={[name, 'value']}
                                          className="!mb-0 flex-1"
                                        >
                                          {paramType === 'password' ? (
                                            <EditablePasswordField
                                              size="middle"
                                              placeholder={t('skill.skillParams.paramValuePlaceholder')}
                                            />
                                          ) : (
                                            <Input placeholder={t('skill.skillParams.paramValuePlaceholder')} className="text-xs" />
                                          )}
                                        </Form.Item>
                                      );
                                    }}
                                  </Form.Item>
                                  <Form.Item
                                    {...restField}
                                    name={[name, 'type']}
                                    className="!mb-0 w-24 shrink-0"
                                    initialValue="text"
                                  >
                                    <Select
                                      size="middle"
                                      onChange={() => {
                                        form.setFieldValue(['skill_params', name, 'value'], '');
                                      }}
                                    >
                                      <Option value="text">{t('skill.skillParams.text')}</Option>
                                      <Option value="password">{t('skill.skillParams.password')}</Option>
                                    </Select>
                                  </Form.Item>
                                </div>
                              ))}
                            </div>
                          )}
                        </>
                      )}
                    </Form.List>
                  </Form.Item>
                </section>

                {/* 4. 能力扩展（聊天历史、技能包、工具） */}
                <section className="mb-6 border-t border-[var(--color-border-1)] pt-5">
                  <div className="mb-3.5 flex items-center gap-2">
                    <span className="h-3.5 w-1 rounded-full bg-[var(--color-primary)]" />
                    <span className="text-[13px] font-semibold text-[var(--color-text-1)]">
                      {t('skill.chatEnhancement')}
                    </span>
                  </div>

                  {/* 聊天历史 */}
                  <div className="flex items-center justify-between py-2.5 border-b border-[var(--color-fill-2)]/60">
                    <div>
                      <div className="text-[13px] font-medium text-[var(--color-text-1)]">{t('skill.chatHistory')}</div>
                      <div className="text-xs text-[var(--color-text-3)]">{t('skill.chatHistoryTip')}</div>
                    </div>
                    <div className="flex items-center gap-2">
                      {chatHistoryEnabled && (
                        <div className="flex items-center gap-1.5 mr-2">
                          <InputNumber
                            min={1}
                            max={100}
                            size="small"
                            className="w-16"
                            value={quantity}
                            onChange={(value) => setQuantity(value ?? 1)}
                          />
                          <span className="text-xs text-[var(--color-text-3)]">轮</span>
                        </div>
                      )}
                      <Switch
                        size="small"
                        checked={chatHistoryEnabled}
                        onChange={setChatHistoryEnabled}
                      />
                    </div>
                  </div>

                  {/* 技能包 */}
                  {renderSkillPackageSelector()}

                  {/* 工具：有选中即启用，空列表即关闭；payload 仍走 selectedTools */}
                  <div className="py-2.5">
                    <ToolSelector defaultTools={selectedTools} onChange={setSelectedTools} />
                  </div>
                </section>

                {/* 5. 引导语 */}
                <section className="border-t border-[var(--color-border-1)] pt-5">
                  <div className="mb-3.5 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="h-3.5 w-1 rounded-full bg-[var(--color-primary)]" />
                      <span className="text-[13px] font-semibold text-[var(--color-text-1)]">{t('skill.form.guide')}</span>
                    </div>
                    <span className="text-xs text-[var(--color-text-3)]">支持 Markdown 与 [快捷提问] 语法</span>
                  </div>
                  <Form.Item
                    name="guide"
                    tooltip={
                      <>
                        <div className="text-red-500 text-xs mt-1">{t('skill.form.guideNotSupportedInExternalApp')}</div>
                        <div>{t('skill.form.guideTip')}</div>
                      </>
                    }
                    className="!mb-0"
                  >
                    <TextArea
                      rows={3}
                      className="text-xs font-mono"
                      placeholder={'您好，请问有什么可以帮助您的吗？可以点击如下问题进行快速提问。\n[问题1]\n[问题2]'}
                      onChange={(e) => setGuideValue(e.target.value)}
                    />
                  </Form.Item>
                </section>
              </Form>
            </div>

            {/* 配置面板底部 Sticky Action Bar */}
            <div className="flex h-12 shrink-0 items-center justify-between border-t border-[var(--color-border-1)] bg-[var(--color-bg)] px-5">
              <span className="text-xs text-[var(--color-text-4)]">
                保存后即时在右侧生效
              </span>
              <PermissionWrapper requiredPermissions={['Edit']} instPermissions={skillPermissions}>
                <Button type="primary" onClick={handleSave} loading={saveLoading}>
                  {t('common.save')}
                </Button>
              </PermissionWrapper>
            </div>
          </div>

          {/* 右栏：调试与预览面板 */}
          <div className="flex w-1/2 min-h-0 flex-col h-full overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] shadow-2xs">
            {/* 调试面板 Header */}
            <div className="flex h-11 shrink-0 items-center justify-between border-b border-[var(--color-border-1)] px-4 bg-[var(--color-fill-1)]/60">
              <div className="flex items-center gap-2">
                <span className="flex h-5 w-5 items-center justify-center rounded bg-[var(--color-primary)] text-white shadow-2xs">
                  <SendOutlined className="text-[10px]" />
                </span>
                <span className="text-[13px] font-semibold text-[var(--color-text-1)]">{t('chat.test')}</span>
                {currentModelName && (
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--color-bg)] px-2.5 py-0.5 text-xs text-[var(--color-text-2)] font-mono border border-[var(--color-border-1)] shadow-2xs">
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                    {currentModelName}
                  </span>
                )}
              </div>
              <span className="rounded bg-[var(--color-bg)] border border-[var(--color-border-1)] px-2 py-0.5 text-[11px] text-[var(--color-text-3)]">
                实时测试环境
              </span>
            </div>

            {/* 调试面板 Chat 内容区 */}
            <div className="flex-1 min-h-0 overflow-hidden bg-[var(--color-bg)]">
              <CustomChatSSE
                showHeader={false}
                handleSendMessage={handleSendMessage}
                guide={guideValue}
                useAGUIProtocol={true}
                initialMessages={initialMessages}
                removePendingBotMessageOnCancel={true}
                conversationHistoryEnabled={chatHistoryEnabled}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default SkillSettingsPage;
