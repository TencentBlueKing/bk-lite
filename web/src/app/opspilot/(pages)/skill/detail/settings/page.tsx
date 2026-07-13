'use client';

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Form, Input, Select, Switch, Button, InputNumber, Slider, Spin, message, Modal, Checkbox, Empty } from 'antd';
import { useTranslation } from '@/utils/i18n';
import useGroups from '@/app/opspilot/hooks/useGroups';
import styles from './index.module.scss';
import { useSearchParams } from 'next/navigation';
import CustomChatSSE from '@/app/opspilot/components/custom-chat-sse';
import PermissionWrapper from '@/components/permission';
import { SkillPackage } from '@/app/opspilot/types/skill';
import { SelectTool } from '@/app/opspilot/types/tool';
import ToolSelector from '@/app/opspilot/components/skill/toolSelector';
import EditablePasswordField from '@/components/dynamic-form/editPasswordField';
import { useSkillApi } from '@/app/opspilot/api/skill';
import { useWikiApi } from '@/app/opspilot/api/wiki';
import { WikiKnowledgeBase } from '@/app/opspilot/types/wiki';
import { useSkill } from '@/app/opspilot/context/skillContext';
import { getModelOptionText, renderModelOptionLabel } from '@/app/opspilot/utils/modelOption';
import { DeleteOutlined } from '@ant-design/icons';
import Icon from '@/components/icon';

const { Option } = Select;
const { TextArea } = Input;

const getPackageKey = (pkg: SkillPackage) => String(pkg.id || `${pkg.package_id}:${pkg.version}`);

const getPackageRequiredTools = (pkg: SkillPackage) => pkg.required_tools || [];

const SkillSettingsPage: React.FC = () => {
  const [form] = Form.useForm();
  const { groups, loading: groupsLoading } = useGroups();
  const { t } = useTranslation();
  const { fetchSkillDetail, fetchLlmModels, fetchSkillPackages, saveSkillDetail } = useSkillApi();
  const { fetchKnowledgeBases } = useWikiApi();
  const { refreshSkillInfo } = useSkill();
  const searchParams = useSearchParams();
  const id = searchParams ? searchParams.get('id') : null;

  const [temperature, setTemperature] = useState(0.7);
  const [initialMessages] = useState<any[]>([]); // 稳定的空数组引用

  const [chatHistoryEnabled, setChatHistoryEnabled] = useState(true);
  const [showToolEnabled, setToolEnabled] = useState(false);
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
        const initialGuide = '您好，请问有什么可以帮助您的吗？可以点击如下问题进行快速提问。\n[问题1]\n[问题2]'
        form.setFieldsValue({
          name: data.name,
          group: data.team,
          introduction: data.introduction,
          llmModel: data.llm_model,
          temperature: data.temperature || 0.7,
          prompt: data.skill_prompt,
          skill_params: data.skill_params || [],
          guide: data.guide || initialGuide,
          show_think: data.show_think,
          enable_suggest: data.enable_suggest,
          enable_query_rewrite: data.enable_query_rewrite,
          wiki_knowledge_bases: data.wiki_knowledge_bases || [],
        });
        setGuideValue(data.guide || initialGuide);
        setChatHistoryEnabled(data.enable_conversation_history);

        setTemperature(data.temperature || 0.7);

        setQuantity(data.conversation_window_size !== undefined ? data.conversation_window_size : 10);

        setSelectedTools(data.tools as SelectTool[]);
        setToolEnabled(!!data.tools.length);
        setSelectedSkillAssetKeys((data.skill_packages || []).map((pkg: SkillPackage) => getPackageKey(pkg)));

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
        setAvailableSkillAssets(skillPackageData.items || []);
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

  const allLoading = Object.values(pageLoading).some(loading => loading) || groupsLoading;

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      if (showToolEnabled && selectedTools.length === 0) {
        message.error(t('skill.ragToolRequired'));
        return;
      }
      const payload = {
        name: values.name,
        team: values.group,
        introduction: values.introduction,
        llm_model: values.llmModel,
        skill_prompt: values.prompt,
        enable_conversation_history: chatHistoryEnabled,
        conversation_window_size: chatHistoryEnabled ? quantity : undefined,
        temperature: temperature,
        show_think: values.show_think,
        guide: values.guide,
        tools: selectedTools.map((tool: any) => ({
          id: tool.id,
          name: tool.rawName || tool.name,
          icon: tool.icon,
          kwargs: tool.kwargs.filter((kwarg: any) => kwarg.key),
        })),
        enable_suggest: values.enable_suggest,
        enable_query_rewrite: values.enable_query_rewrite,
        skill_params: (values.skill_params || []).filter((p: any) => p && p.key),
        wiki_knowledge_bases: values.wiki_knowledge_bases || [],
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
      message.success(t('common.saveSuccess'));
      refreshSkillInfo();
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

      // Check if tool is selected when tool functionality is enabled
      if (showToolEnabled && selectedTools.length === 0) {
        message.error(t('skill.ragToolRequired'));
        return null;
      }

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
        chat_history: chatHistory,
        conversation_window_size: chatHistoryEnabled ? quantity : undefined,
        temperature: temperature,
        show_think: values.show_think,
        tools: selectedTools,
        skill_type: 1,
        group: values.group?.[0],
        skill_name: values.name,
        skill_id: id,
        enable_suggest: values.enable_suggest,
        enable_query_rewrite: values.enable_query_rewrite,
        skill_params: (values.skill_params || []).filter((p: any) => p && p.key),
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
        tools: selectedTools,
        skill_type: 1,
        group: values.group?.[0],
        skill_name: values.name,
        skill_id: id,
        enable_suggest: values.enable_suggest,
        enable_query_rewrite: values.enable_query_rewrite,
        skill_params: (values.skill_params || []).filter((p: any) => p && p.key),
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

  const handleTemperatureChange = (value: number | null) => {
    const newValue = value === null ? 0 : value;
    setTemperature(newValue);
    form.setFieldsValue({ temperature: newValue });
  };

  const changeToolEnable = (checked: boolean) => {
    setToolEnabled(checked);
    !checked && setSelectedTools([])
  }

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
    setIsSkillPickerOpen(false);
  };

  const handleRemoveSkillAsset = (assetKey: string) => {
    setSelectedSkillAssetKeys((prev) => prev.filter((key) => key !== assetKey));
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
    <div className={`p-4 rounded-md pb-4 ${styles.contentWrapper}`}>
      <div className="flex justify-between">
        <h3 className="font-medium text-sm mb-4">技能包</h3>
        <Button onClick={openSkillPicker}>+ 添加</Button>
      </div>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {effectiveSkillCapabilityProfiles.length === 0 ? (
          <span className="col-span-full text-xs text-[var(--color-text-4)]">未选择</span>
        ) : (
          effectiveSkillCapabilityProfiles.map((asset) => {
            const assetKey = getPackageKey(asset);
            return (
              <div
                key={assetKey}
                className="flex w-full items-center justify-between rounded-md border border-[var(--color-border)] bg-[var(--color-bg-1)] px-4 py-2"
              >
                <div className="flex min-w-0 items-center">
                  <Icon type="jinengpeixun" className="mr-1 shrink-0 text-xl" />
                  <span className="truncate text-sm font-medium text-[var(--color-text-1)]">{asset.name}</span>
                </div>
                <DeleteOutlined
                  className="ml-3 cursor-pointer text-[var(--color-text-3)] transition-colors hover:text-[var(--color-primary)]"
                  onClick={() => handleRemoveSkillAsset(assetKey)}
                />
              </div>
            );
          })
        )}
      </div>
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
      <Input.Search
        allowClear
        className="mb-3"
        placeholder="搜索技能包"
        value={skillPickerKeyword}
        onChange={(event) => setSkillPickerKeyword(event.target.value)}
      />
      <div className="grid max-h-[420px] grid-cols-1 gap-3 overflow-y-auto pr-1 lg:grid-cols-2">
        {filteredAvailableSkillAssets.length === 0 ? (
          <div className="col-span-full">
            <Empty description="没有匹配的技能包" />
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
                    ? 'border-[var(--color-primary)] bg-[var(--color-primary-bg)]'
                    : 'border-[var(--color-border)] bg-[var(--color-bg-1)] hover:border-[var(--color-primary-border)]'
                }`}
              >
                <div className="flex h-full items-start gap-3">
                  <Checkbox
                    checked={checked}
                    className="mt-0.5"
                    onChange={(event) => toggleDraftSkillAsset(assetKey, event.target.checked)}
                  />
                  <Icon type="jinengpeixun" className="shrink-0 text-4xl" />
                  <div className="flex min-w-0 flex-1 flex-col">
                    <div className="flex min-w-0 items-center gap-2">
                      <div className="truncate font-medium text-[var(--color-text-1)]">{asset.name}</div>
                    </div>
                    <p className="mt-2 line-clamp-2 min-h-10 text-xs leading-5 text-[var(--color-text-3)]">
                      {asset.description || '暂无描述'}
                    </p>
                    {asset.category && (
                      <div className="mt-auto pt-2 text-xs text-[var(--color-text-4)]">{asset.category}</div>
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
    <div className="relative">
      {renderSkillPickerModal()}
      {allLoading && (
        <div className="absolute inset-0 min-h-[500px] bg-opacity-50 z-50 flex items-center justify-center">
          <Spin spinning={allLoading} />
        </div>
      )}
      {!allLoading && (
        <div className="flex justify-between space-x-4" style={{ height: 'calc(100vh - 220px)' }}>
          <div className='w-1/2 space-y-4 flex flex-col h-full'>
            <section className={`flex-1 ${styles.llmSection}`}>
              <div className={`border rounded-md mb-5 ${styles.llmContainer}`}>
                <h2 className="font-semibold mb-3 text-base rounded-tl-md rounded-tr-md">{t('skill.information')}</h2>
                <div className="px-4">
                  <Form
                    form={form}
                    labelCol={{ flex: '0 0 128px' }}
                    wrapperCol={{ flex: '1' }}
                    initialValues={{ temperature: 0.7, show_think: true }}
                  >
                    <Form.Item label={t('common.name')} name="name" rules={[{ required: true, message: `${t('common.input')} ${t('common.name')}` }]}>
                      <Input />
                    </Form.Item>
                    <Form.Item label={t('common.organization')} name="group" rules={[{ required: true, message: `${t('common.input')} ${t('common.organization')}` }]}>
                      <Select mode="multiple">
                        {groups.map(group => (
                          <Option key={group.id} value={group.id}>{group.name}</Option>
                        ))}
                      </Select>
                    </Form.Item>
                    <Form.Item label={t('skill.form.introduction')} name="introduction" rules={[{ required: true, message: `${t('common.input')} ${t('skill.form.introduction')}` }]}>
                      <TextArea rows={4} />
                    </Form.Item>
                    <Form.Item
                      label={t('skill.form.llmModel')}
                      name="llmModel"
                      rules={[{ required: true, message: `${t('common.input')} ${t('skill.form.llmModel')}` }]}
                    >
                      <Select
                        onChange={(value: number) => {
                          const selected = llmModels.find(model => model.id === value);
                          form.setFieldsValue({ show_think: selected && selected.llm_model_type === 'deep-seek' ? false : true });
                        }}
                      >
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
                      label={t('skill.form.showThought')}
                      name="show_think"
                      valuePropName="checked">
                      <Switch size="small" />
                    </Form.Item>
                    <Form.Item
                      label={t('skill.form.enableSuggest')}
                      name="enable_suggest"
                      valuePropName="checked">
                      <Switch size="small" />
                    </Form.Item>
                    <Form.Item
                      label={t('skill.form.problemOptimization')}
                      name="enable_query_rewrite"
                      tooltip={t('skill.form.problemOptimizationTip')}
                      valuePropName="checked">
                      <Switch size="small" />
                    </Form.Item>
                    <Form.Item
                      label={t('skill.form.temperature')}
                      name="temperature"
                      tooltip={t('skill.form.temperatureTip')}
                    >
                      <div className="flex gap-4">
                        <Slider
                          className="flex-1"
                          min={0}
                          max={1}
                          step={0.01}
                          value={temperature}
                          onChange={handleTemperatureChange}
                        />
                        <InputNumber
                          min={0}
                          max={1}
                          step={0.01}
                          value={temperature}
                          onChange={handleTemperatureChange}
                        />
                      </div>
                    </Form.Item>
                    <Form.Item
                      label={t('skill.form.prompt')}
                      name="prompt"
                      tooltip={t('skill.form.promptTip')}
                      extra={hasInvalidParamKeys ? <span className="text-orange-500">{t('skill.skillParams.invalidKeyWarning')}</span> : undefined}
                      rules={[{ required: true, message: `${t('common.input')} ${t('skill.form.prompt')}` }]}>
                      <TextArea rows={4} onChange={(e) => syncSkillParamsFromPrompt(e.target.value)} />
                    </Form.Item>
                    <Form.Item label={t('skill.skillParams.title')} tooltip={t('skill.skillParams.tip')}>
                      <Form.List name="skill_params">
                        {(fields) => (
                          <>
                            {fields.length === 0 ? (
                              <div className="rounded-xl border border-slate-200 bg-slate-50/80 px-5 py-5 text-center">
                                <div className="text-[13px] font-medium leading-5 text-slate-700">
                                  {t('skill.skillParams.emptyHint')}
                                </div>
                                <div className="mt-1 text-[13px] leading-5 text-slate-700">
                                  {t('skill.skillParams.emptySubHint')}
                                </div>
                                <div className="mt-3 inline-flex max-w-full items-center rounded-md border border-slate-200 bg-white px-3 py-1.5 text-[13px] leading-5 text-slate-600 shadow-sm">
                                  {t('skill.skillParams.emptyExample')}
                                </div>
                              </div>
                            ) : (
                              fields.map(({ key, name, ...restField }) => (
                              <div key={key} className="flex items-center gap-2 mb-2">
                                <Form.Item
                                  {...restField}
                                  name={[name, 'key']}
                                  className="mb-0 flex-1"
                                  rules={[
                                    { required: true, message: t('skill.skillParams.paramNamePlaceholder') },
                                  ]}
                                >
                                  <Input placeholder={t('skill.skillParams.paramNamePlaceholder')} disabled />
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
                                        className="mb-0 flex-1"
                                      >
                                        {paramType === 'password' ? (
                                          <EditablePasswordField
                                            size="middle"
                                            placeholder={t('skill.skillParams.paramValuePlaceholder')}
                                          />
                                        ) : (
                                          <Input placeholder={t('skill.skillParams.paramValuePlaceholder')} />
                                        )}
                                      </Form.Item>
                                    );
                                  }}
                                </Form.Item>
                                <Form.Item
                                  {...restField}
                                  name={[name, 'type']}
                                  className="mb-0"
                                  initialValue="text"
                                >
                                  <Select
                                    style={{ width: 100 }}
                                    onChange={() => {
                                      form.setFieldValue(['skill_params', name, 'value'], '');
                                    }}
                                  >
                                    <Option value="text">{t('skill.skillParams.text')}</Option>
                                    <Option value="password">{t('skill.skillParams.password')}</Option>
                                  </Select>
                                </Form.Item>
                              </div>
                              ))
                            )}
                          </>
                        )}
                      </Form.List>
                    </Form.Item>
                    <Form.Item
                      label={t('skill.form.guide')}
                      name="guide"
                      tooltip={
                        <>
                          <div className="text-red-500 text-xs mt-1">{t('skill.form.guideNotSupportedInExternalApp')}</div>
                          <div>{t('skill.form.guideTip')}</div>
                        </>
                      }>
                      <TextArea
                        rows={4}
                        onChange={(e) => setGuideValue(e.target.value)}
                      />
                    </Form.Item>
                  </Form>
                </div>
              </div>
              <div className={`border rounded-md ${styles.llmContainer}`}>
                <h2 className="font-semibold mb-3 text-base rounded-tl-md rounded-tr-md">{t('skill.chatEnhancement')}</h2>
                <div className={`p-4 rounded-md pb-0 ${styles.contentWrapper}`}>
                  <Form labelCol={{flex: '0 0 80px'}} wrapperCol={{flex: '1'}}>
                    <div className="flex justify-between">
                      <h3 className="font-medium text-sm mb-4">{t('skill.chatHistory')}</h3>
                      <Switch
                        size="small"
                        className="ml-2"
                        checked={chatHistoryEnabled}
                        onChange={setChatHistoryEnabled}/>
                    </div>
                    <p className="pb-4 text-xs text-[var(--color-text-4)]">{t('skill.chatHistoryTip')}</p>
                    {chatHistoryEnabled && (
                      <div className="pb-4">
                        <Form.Item label={t('skill.quantity')}>
                          <InputNumber
                            min={1}
                            max={100}
                            className="w-full" value={quantity}
                            onChange={(value) => setQuantity(value ?? 1)} />
                        </Form.Item>
                      </div>
                    )}
                  </Form>
                </div>
                {renderSkillPackageSelector()}
                <div className={`p-4 rounded-md pb-0 ${styles.contentWrapper}`}>
                  <Form labelCol={{flex: '0 0 135px'}} wrapperCol={{flex: '1'}}>
                    <div className="flex justify-between">
                      <h3 className="font-medium text-sm mb-4">{t('skill.tool')}</h3>
                      <Switch size="small" className="ml-2" checked={showToolEnabled} onChange={changeToolEnable} />
                    </div>
                    <p className="pb-4 text-xs text-[var(--color-text-4)]">{t('skill.toolTip')}</p>
                    {showToolEnabled && (
                      <ToolSelector
                        defaultTools={selectedTools}
                        onChange={(selected: SelectTool[]) => setSelectedTools(selected)}
                      />
                    )}
                  </Form>
                </div>
              </div>
            </section>
            <div>
              <PermissionWrapper
                requiredPermissions={['Edit']}
                instPermissions={skillPermissions}>
                <Button type="primary" onClick={handleSave} loading={saveLoading}>
                  {t('common.save')}
                </Button>
              </PermissionWrapper>
            </div>
          </div>
          <div className="w-1/2 space-y-4">
            <CustomChatSSE
              handleSendMessage={handleSendMessage}
              guide={guideValue}
              useAGUIProtocol={true}
              initialMessages={initialMessages}
              removePendingBotMessageOnCancel={true}
            />
          </div>
        </div>
      )}
    </div>
  );
};

export default SkillSettingsPage;
