'use client';

import React, { useState, useEffect } from 'react';
import { Form, Input, Select, Switch, Button, InputNumber, Slider, Spin, message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import useGroups from '@/app/opspilot/hooks/useGroups';
import styles from './index.module.scss';
import { useSearchParams } from 'next/navigation';
import CustomChatSSE from '@/app/opspilot/components/custom-chat-sse';
import PermissionWrapper from '@/components/permission';
import KnowledgeBaseSelector from '@/app/opspilot/components/skill/knowledgeBaseSelector';
import { KnowledgeBase, RagScoreThresholdItem, KnowledgeBaseRagSource } from '@/app/opspilot/types/skill';
import { SelectTool } from '@/app/opspilot/types/tool';
import ToolSelector from '@/app/opspilot/components/skill/toolSelector';
import { useSkillApi } from '@/app/opspilot/api/skill';

const { Option } = Select;
const { TextArea } = Input;

const SkillSettingsPage: React.FC = () => {
  const [form] = Form.useForm();
  const { groups, loading: groupsLoading } = useGroups();
  const { t } = useTranslation();
  const { fetchSkillDetail, fetchKnowledgeBases, fetchLlmModels, saveSkillDetail } = useSkillApi();
  const searchParams = useSearchParams();
  const id = searchParams ? searchParams.get('id') : null;

  const [temperature, setTemperature] = useState(0.7);

  const [chatHistoryEnabled, setChatHistoryEnabled] = useState(true);
  const [ragEnabled, setRagEnabled] = useState(true);
  const [showRagSource, setRagSourceStatus] = useState(false);
  const [showToolEnabled, setToolEnabled] = useState(false);
  const [ragStrictMode, setRagStrictMode] = useState(false);
  const [ragSources, setRagSources] = useState<KnowledgeBaseRagSource[]>([]);
  const [selectedKnowledgeBases, setSelectedKnowledgeBases] = useState<number[]>([]);
  const [llmModels, setLlmModels] = useState<{ id: number, name: string, enabled: boolean, llm_model_type: string }[]>([]);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [pageLoading, setPageLoading] = useState({
    llmModelsLoading: true,
    knowledgeBasesLoading: true,
    formDataLoading: true,
  });
  const [saveLoading, setSaveLoading] = useState(false);
  const [quantity, setQuantity] = useState<number>(10);
  const [selectedTools, setSelectedTools] = useState<SelectTool[]>([]);
  const [skillType, setSkillType] = useState<number | null>(null);
  const [skillPermissions, setSkillPermissions] = useState<string[]>([]);
  const [enableKmRoute, setEnableKmRoute] = useState(true);
  const [kmLlmModel, setKmLlmModel] = useState<number | null>(null);
  const [guideValue, setGuideValue] = useState<string>('');

  useEffect(() => {
    const fetchFormData = async (knowledgeBases: KnowledgeBase[]) => {
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
          guide: data.guide || initialGuide,
          show_think: data.show_think,
          enable_suggest: data.enable_suggest,
          enable_query_rewrite: data.enable_query_rewrite,
        });
        setGuideValue(data.guide || initialGuide);
        setChatHistoryEnabled(data.enable_conversation_history);
        setRagEnabled(data.enable_rag);
        setRagStrictMode(data.enable_rag_strict_mode);
        setRagSourceStatus(data.enable_rag_knowledge_source);

        setTemperature(data.temperature || 0.7);

        const initialRagSources = data.rag_score_threshold.map((item: RagScoreThresholdItem) => {
          const base = knowledgeBases.find((base) => base.id === Number(item.knowledge_base));
          return base ? { id: base.id, name: base.name, introduction: base.introduction || '', score: item.score } : null;
        }).filter(Boolean) as KnowledgeBaseRagSource[];
        setRagSources(initialRagSources);
        setQuantity(data.conversation_window_size !== undefined ? data.conversation_window_size : 10);

        const initialSelectedKnowledgeBases = data.rag_score_threshold.map((item: RagScoreThresholdItem) => Number(item.knowledge_base));
        setSelectedKnowledgeBases(initialSelectedKnowledgeBases);
        setSelectedTools(data.tools);
        setToolEnabled(!!data.tools.length);

        setSkillType(data.skill_type);
        setSkillPermissions(data.permissions || []);
        
        setEnableKmRoute(data.enable_km_route !== undefined ? data.enable_km_route : true);
        setKmLlmModel(data.km_llm_model || data.llm_model);
      } catch (error) {
        console.error(t('common.fetchFailed'), error);
      } finally {
        setPageLoading(prev => ({ ...prev, formDataLoading: false }));
      }
    };

    const fetchInitialData = async () => {
      if (!id) return;
      try {
        const [llmModelsData, knowledgeBasesData] = await Promise.all([
          fetchLlmModels(),
          fetchKnowledgeBases()
        ]);
        setLlmModels(llmModelsData);
        setKnowledgeBases(knowledgeBasesData);
        fetchFormData(knowledgeBasesData);
      } catch (error) {
        console.error(t('common.fetchFailed'), error);
      } finally {
        setPageLoading(prev => ({ ...prev, llmModelsLoading: false, knowledgeBasesLoading: false }));
      }
    };

    fetchInitialData();
  }, [id]);

  const allLoading = Object.values(pageLoading).some(loading => loading) || groupsLoading;

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      if (ragEnabled && ragSources.length === 0) {
        message.error(t('skill.ragKnowledgeBaseRequired'));
        return;
      }
      if (showToolEnabled && selectedTools.length === 0) { 
        message.error(t('skill.ragToolRequired'));
        return;
      }
      const ragScoreThreshold = ragSources.map((source) => ({
        knowledge_base: knowledgeBases.find(base => base.name === source.name)?.id,
        score: source.score
      }));
      const payload = {
        name: values.name,
        team: values.group,
        introduction: values.introduction,
        llm_model: values.llmModel,
        skill_prompt: values.prompt,
        enable_conversation_history: chatHistoryEnabled,
        enable_rag: ragEnabled,
        enable_rag_knowledge_source: showRagSource,
        enable_rag_strict_mode: ragStrictMode,
        rag_score_threshold: ragScoreThreshold,
        conversation_window_size: chatHistoryEnabled ? quantity : undefined,
        temperature: temperature,
        show_think: values.show_think,
        enable_km_route: enableKmRoute,
        km_llm_model: enableKmRoute ? kmLlmModel : undefined,
        guide: values.guide,
        tools: selectedTools.map((tool: any) => ({
          id: tool.id,
          name: tool.name,
          icon: tool.icon,
          kwargs: tool.kwargs.filter((kwarg: any) => kwarg.key),
        })),
        enable_suggest: values.enable_suggest,
        enable_query_rewrite: values.enable_query_rewrite,
      };
      setSaveLoading(true);
      await saveSkillDetail(id, payload);
      message.success(t('common.saveSuccess'));
    } catch (error) {
      console.error(t('common.saveFailed'), error);
    } finally {
      setSaveLoading(false);
    }
  };

  const handleSendMessage = async (userMessage: string, currentMessages: any[] = []): Promise<{ url: string; payload: any } | null> => {
    try {
      const values = await form.validateFields();
      
      // Check if knowledge base is selected when RAG is enabled
      if (ragEnabled && ragSources.length === 0) {
        message.error(t('skill.ragKnowledgeBaseRequired'));
        return null;
      }
      
      // Check if tool is selected when tool functionality is enabled
      if (showToolEnabled && selectedTools.length === 0) { 
        message.error(t('skill.ragToolRequired'));
        return null;
      }
      
      const ragScoreThreshold = selectedKnowledgeBases.map(id => ({
        knowledge_base: id,
        score: ragSources.find(base => base.id === id)?.score || 0.7,
      }));

      const chatHistory = chatHistoryEnabled && quantity 
        ? currentMessages.slice(-quantity).map(msg => ({ 
          message: msg.content, 
          event: msg.role 
        }))
        : [];

      const payload = {
        user_message: userMessage,
        llm_model: values.llmModel,
        skill_prompt: values.prompt,
        enable_rag: ragEnabled,
        enable_rag_knowledge_source: showRagSource,
        enable_rag_strict_mode: ragStrictMode,
        rag_score_threshold: ragScoreThreshold,
        chat_history: chatHistory,
        conversation_window_size: chatHistoryEnabled ? quantity : undefined,
        temperature: temperature,
        show_think: values.show_think,
        tools: selectedTools,
        skill_type: skillType,
        group: values.group?.[0],
        skill_name: values.name,
        skill_id: id,
        enable_km_route: enableKmRoute,
        km_llm_model: enableKmRoute ? kmLlmModel : undefined,
        enable_suggest: values.enable_suggest,
        enable_query_rewrite: values.enable_query_rewrite,
      };

      return {
        url: '/api/proxy/opspilot/model_provider_mgmt/llm/execute/?stream=1',
        payload
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

  const handleKmRouteChange = (checked: boolean) => {
    setEnableKmRoute(checked);
    if (checked && !kmLlmModel) {
      const currentLlmModel = form.getFieldValue('llmModel');
      if (currentLlmModel) {
        setKmLlmModel(currentLlmModel);
      }
    }
  }

  return (
    <div className="relative">
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
                    <Form.Item label={t('skill.form.name')} name="name" rules={[{ required: true, message: `${t('common.input')} ${t('skill.form.name')}` }]}>
                      <Input />
                    </Form.Item>
                    <Form.Item label={t('skill.form.group')} name="group" rules={[{ required: true, message: `${t('common.input')} ${t('skill.form.group')}` }]}>
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
                          <Option key={model.id} value={model.id} disabled={!model.enabled}>{model.name}</Option>
                        ))}
                      </Select>
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
                      rules={[{ required: true, message: `${t('common.input')} ${t('skill.form.prompt')}` }]}>
                      <TextArea rows={4} />
                    </Form.Item>
                    <Form.Item
                      label={t('skill.form.guide')}
                      name="guide"
                      tooltip={t('skill.form.guideTip')}>
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
                <div className={`p-4 rounded-md pb-0 ${styles.contentWrapper}`}>
                  <Form labelCol={{flex: '0 0 135px'}} wrapperCol={{flex: '1'}}>
                    <div className="flex justify-between">
                      <h3 className="font-medium text-sm mb-4">{t('skill.rag')}</h3>
                      <Switch size="small" className="ml-2" checked={ragEnabled} onChange={setRagEnabled}/>
                    </div>
                    <p className="pb-4 text-xs text-[var(--color-text-4)]">{t('skill.ragTip')}</p>
                    {ragEnabled && (
                      <div className="pb-2">
                        <Form.Item
                          label={t('skill.ragSource')}
                          tooltip={t('skill.ragSourceTip')}>
                          <Switch size="small" className="ml-2" checked={showRagSource} onChange={setRagSourceStatus}/>
                        </Form.Item>
                        <Form.Item
                          label={t('skill.ragStrictMode')}
                          tooltip={t('skill.ragStrictModeTip')}>
                          <Switch size="small" className="ml-2" checked={ragStrictMode} onChange={setRagStrictMode}/>
                        </Form.Item>
                        <Form.Item
                          label={t('skill.knowledgeRoute')}
                          tooltip={t('skill.knowledgeRouteTip')}>
                          <Switch size="small" className="ml-2" checked={enableKmRoute} onChange={handleKmRouteChange}/>
                        </Form.Item>
                        {enableKmRoute && (
                          <Form.Item
                            label={t('skill.kmLlmModel')}>
                            <Select
                              value={kmLlmModel}
                              onChange={(value: number) => setKmLlmModel(value)}
                              placeholder={t('common.select')}
                            >
                              {llmModels.map(model => (
                                <Option key={model.id} value={model.id} disabled={!model.enabled}>{model.name}</Option>
                              ))}
                            </Select>
                          </Form.Item>
                        )}
                        <Form.Item label={t('skill.knowledgeBase')} tooltip={t('skill.knowledgeBaseTip')}>
                          <KnowledgeBaseSelector
                            ragSources={ragSources}
                            setRagSources={setRagSources}
                            knowledgeBases={knowledgeBases}
                            selectedKnowledgeBases={selectedKnowledgeBases}
                            setSelectedKnowledgeBases={setSelectedKnowledgeBases}
                          />
                        </Form.Item>
                      </div>
                    )}
                  </Form>
                </div>
                {skillType !== 2 && (
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
                )}
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
            />
          </div>
        </div>
      )}
    </div>
  );
};

export default SkillSettingsPage;
