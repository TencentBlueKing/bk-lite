'use client';

import React, { useState, useEffect } from 'react';
import { Form, Input, Select, Switch, Button, InputNumber, Slider, Spin, message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { v4 as uuidv4 } from 'uuid';
import useGroups from '@/app/opspilot/hooks/useGroups';
import styles from './index.module.scss';
import { useSearchParams } from 'next/navigation';
import { CustomChatMessage } from '@/app/opspilot/types/global';
import CustomChat from '@/app/opspilot/components/custom-chat';
import PermissionWrapper from '@/components/permission';
import KnowledgeBaseSelector from '@/app/opspilot/components/skill/knowledgeBaseSelector';
import { KnowledgeBase, RagScoreThresholdItem, KnowledgeBaseRagSource } from '@/app/opspilot/types/skill';
import ToolSelector from '@/app/opspilot/components/skill/toolSelector';
import { useSkillApi } from '@/app/opspilot/api/skill';

const { Option } = Select;
const { TextArea } = Input;

const SkillSettingsPage: React.FC = () => {
  const [form] = Form.useForm();
  const [isDeepSeek, setIsDeepSeek] = useState(false);
  const { groups, loading: groupsLoading } = useGroups();
  const { t } = useTranslation();
  const { fetchSkillDetail, fetchKnowledgeBases, fetchLlmModels, saveSkillDetail, executeLlm } = useSkillApi();
  const searchParams = useSearchParams();
  const id = searchParams ? searchParams.get('id') : null;

  const [temperature, setTemperature] = useState(0.7);

  const [chatHistoryEnabled, setChatHistoryEnabled] = useState(true);
  const [ragEnabled, setRagEnabled] = useState(true);
  const [showRagSource, setRagSourceStatus] = useState(false);
  const [showToolEnabled, setToolEnabled] = useState(false);
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
  const [selectedTools, setSelectedTools] = useState<number[]>([]);
  const [skillType, setSkillType] = useState<number | null>(null);

  useEffect(() => {
    const fetchInitialData = async () => {
      try {
        const [llmModelsData, knowledgeBasesData] = await Promise.all([
          fetchLlmModels(),
          fetchKnowledgeBases()
        ]);
        setLlmModels(llmModelsData);
        setKnowledgeBases(knowledgeBasesData);
      } catch (error) {
        console.error(t('common.fetchFailed'), error);
      } finally {
        setPageLoading(prev => ({ ...prev, llmModelsLoading: false, knowledgeBasesLoading: false }));
      }
    };

    fetchInitialData();
  }, []);

  useEffect(() => {
    const fetchFormData = async () => {
      if (id) {
        try {
          const data = await fetchSkillDetail(id);
          form.setFieldsValue({
            name: data.name,
            group: data.team,
            introduction: data.introduction,
            llmModel: data.llm_model,
            temperature: data.temperature || 0.7,
            prompt: data.skill_prompt,
            show_think: data.show_think,
          });
          const selected = llmModels.find(model => model.id === data.llm_model);
          setIsDeepSeek(selected?.llm_model_type === 'deep-seek');
          setChatHistoryEnabled(data.enable_conversation_history);
          setRagEnabled(data.enable_rag);
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
        } catch (error) {
          console.error(t('common.fetchFailed'), error);
        } finally {
          setPageLoading(prev => ({ ...prev, formDataLoading: false }));
        }
      }
    };

    fetchFormData();
  }, [id, knowledgeBases]);

  const allLoading = Object.values(pageLoading).some(loading => loading) || groupsLoading;

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
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
        rag_score_threshold: ragScoreThreshold,
        conversation_window_size: chatHistoryEnabled ? quantity : undefined,
        temperature: temperature,
        show_think: values.show_think,
        tools: selectedTools
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

  const handleSendMessage = async (newMessage: CustomChatMessage[], lastUserMessage?: CustomChatMessage): Promise<CustomChatMessage[]> => {
    return new Promise(async (resolve) => {
      const message = lastUserMessage || [...newMessage].reverse().find(message => message.role === 'user');
      if (!message) {
        resolve(newMessage);
        return;
      }
      try {
        const values = await form.validateFields();
        const ragScoreThreshold = selectedKnowledgeBases.map(id => ({
          knowledge_base: id,
          score: ragSources.find(base => base.id === id)?.score || 0.7,
        }));
        const payload = {
          user_message: message?.content || '',
          llm_model: values.llmModel,
          skill_prompt: values.prompt,
          enable_rag: ragEnabled,
          enable_rag_knowledge_source: showRagSource,
          rag_score_threshold: ragScoreThreshold,
          chat_history: quantity ? newMessage.slice(0, quantity).map(msg => ({ message: msg.content, event: msg.role })) : [],
          conversation_window_size: chatHistoryEnabled ? quantity : undefined,
          temperature: temperature,
          show_think: values.show_think,
          tools: selectedTools,
          skill_type: skillType,
        };
        const reply = await executeLlm(payload);
        const botMessage: CustomChatMessage = {
          id: uuidv4(),
          content: reply.content,
          role: 'bot',
          createAt: new Date().toISOString(),
          updateAt: new Date().toISOString(),
          knowledgeBase: reply.citing_knowledge || null,
        };
        resolve([...newMessage, botMessage]);
      } catch (error) {
        console.error(t('common.fetchFailed'), error);
        resolve(newMessage);
      }
    });
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
                          setIsDeepSeek(selected?.llm_model_type === 'deep-seek');
                          form.setFieldsValue({ show_think: selected && selected.llm_model_type === 'deep-seek' ? false : true });
                        }}
                      >
                        {llmModels.map(model => (
                          <Option key={model.id} value={model.id} disabled={!model.enabled}>{model.name}</Option>
                        ))}
                      </Select>
                    </Form.Item>
                    {isDeepSeek && (
                      <Form.Item
                        label={t('skill.form.showThought')}
                        name="show_think"
                        valuePropName="checked">
                        <Switch size="small" />
                      </Form.Item>
                    )}
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
                        <Form.Item label={t('skill.ragSource')}>
                          <Switch size="small" className="ml-2" checked={showRagSource} onChange={setRagSourceStatus}/>
                        </Form.Item>
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
                {skillType === 1 && (
                  <div className={`p-4 rounded-md pb-0 ${styles.contentWrapper}`}>
                    <Form labelCol={{flex: '0 0 135px'}} wrapperCol={{flex: '1'}}>
                      <div className="flex justify-between">
                        <h3 className="font-medium text-sm mb-4">{t('skill.tool')}</h3>
                        <Switch size="small" className="ml-2" checked={showToolEnabled} onChange={changeToolEnable} />
                      </div>
                      <p className="pb-4 text-xs text-[var(--color-text-4)]">{t('skill.toolTip')}</p>
                      {showToolEnabled && (<ToolSelector selectedToolIds={selectedTools} onChange={setSelectedTools} />)}
                    </Form>
                  </div>
                )}
              </div>
            </section>
            <div>
              <PermissionWrapper
                requiredPermissions={['Edit']}>
                <Button type="primary" onClick={handleSave} loading={saveLoading}>
                  {t('common.save')}
                </Button>
              </PermissionWrapper>
            </div>
          </div>
          <div className="w-1/2 space-y-4">
            <CustomChat handleSendMessage={handleSendMessage} />
          </div>
        </div>
      )}
    </div>
  );
};

export default SkillSettingsPage;
