'use client';

import React, {useEffect, useState} from 'react';
import {useSearchParams} from 'next/navigation';
import {useTranslation} from '@/utils/i18n';
import {Memory, useMemoryApi} from '@/app/opspilot/api/memory';
import {useSkillApi} from '@/app/opspilot/api/skill';
import {Button, Form, Input, message, Select, Spin} from 'antd';
import PermissionWrapper from '@/components/permission';
import GroupTreeSelect from '@/components/group-tree-select';

const { TextArea } = Input;

export default function MemoryConfigPage() {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const { fetchMemorySpace, updateMemorySpace, fetchMemories, testMemoryWrite } = useMemoryApi();
  const { fetchLlmModels } = useSkillApi();
  const [form] = Form.useForm();
  
  const idStr = searchParams.get('id');
  const id = idStr ? parseInt(idStr, 10) : 0;

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [models, setModels] = useState<any[]>([]);
  const [memories, setMemories] = useState<Memory[]>([]);

  // Test states
  const [testInput, setTestInput] = useState('');
  const [testRefId, setTestRefId] = useState<number | undefined>(undefined);
  const [testResult, setTestResult] = useState<{ result: string } | null>(null);
  const [testing, setTesting] = useState(false);
  const [activeTab, setActiveTab] = useState<'reference' | 'result'>('result');

  useEffect(() => {
    if (id) {
      setLoading(true);
      fetchMemorySpace(id).then(res => {
        const formData = {
          ...res,
          default_model: res.default_model ? Number(res.default_model) : undefined
        };
        form.setFieldsValue(formData);
      }).catch(e => {
        console.error(e);
      }).finally(() => {
        setLoading(false);
      });

      fetchMemories(id).then(res => {
        setMemories(res);
      }).catch(console.error);
    }
  }, [id, form]);

  useEffect(() => {
    fetchLlmModels().then(data => {
      setModels(data || []);
    }).catch(console.error);
  }, []);

  const onFinish = async (values: any) => {
    if (!id) return;
    setSaving(true);
    try {
      await updateMemorySpace(id, values);
      message.success(t('memory.saveSuccess'));
    } catch (e) {
      console.error(e);
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    if (!testInput.trim()) {
      message.warning(t('memory.testInputRequired'));
      return;
    }
    const writeRule = form.getFieldValue('write_rule');
    const modelId = form.getFieldValue('default_model');
    if (!writeRule || !modelId) {
      message.warning(t('memory.testConfigRequired'));
      return;
    }
    setTesting(true);
    try {
      const res = await testMemoryWrite({
        input: testInput,
        write_rule: writeRule,
        model_id: modelId,
        reference_memory_id: testRefId,
      });
      setTestResult(res);
      if (testRefId) setActiveTab('result');
    } catch (e) {
      console.error(e);
      message.error('Test failed');
    } finally {
      setTesting(false);
    }
  };

  const handleRefChange = (val: any) => {
    setTestRefId(val);
    if (val) setActiveTab('reference');
    else setActiveTab('result');
    setTestResult(null);
  };

  const referenceMemory = memories.find(m => m.id === testRefId);

  const cardClassName = 'overflow-hidden rounded-[10px] border border-[var(--color-border-2)] bg-[var(--color-bg-1)]';
  const cardHeadClassName = 'flex h-10 items-center border-b border-[var(--color-border-2)] bg-[var(--color-fill-2)] px-3.5 text-[13px] font-bold text-[var(--color-text-1)]';
  const cardBodyClassName = 'flex flex-col gap-3 p-3.5';
  const labelClassName = 'text-[13px] font-semibold text-[var(--color-text-2)]';
  const hintClassName = 'mt-1.5 text-[11px] leading-relaxed text-[var(--color-text-3)]';

  return (
    /* 小屏让出自然高度,触发 sub-layout .sectionContext overflow-auto 出滚动条;
       lg 及以上撑满。`relative` 是给 loading overlay 用的 absolute 锚点,
       任何宽度都要保留。 */
    <div className="relative lg:h-full">
      {loading && (
        <div className="absolute inset-0 min-h-[500px] bg-opacity-50 z-50 flex items-center justify-center">
          <Spin spinning={loading} />
        </div>
      )}
      {!loading && (
        <Form
          form={form}
          onFinish={onFinish}
          layout="horizontal"
          // 小屏让出自然高度(触发 sub-layout .sectionContext overflow-auto 出滚动条),
          // lg 及以上才撑满,让 write rule / test result 卡片 flex:1 拿到更多 textarea 高度。
          className="lg:h-full"
        >
          {/* 响应式:小屏单列堆叠,lg(≥1024px)及以上恢复 6:4 双列。
              用 grid + lg:col-span 替代 flex-[6]/flex-[4],避免小屏两列硬挤
              (label 92px + input 在 6/10 宽度下被压到 60~80px,无法阅读);
              grid-cols-1 默认让每列拿到全宽,form label 横向不被挤,纵向滚动
              由 sub-layout 的 .sectionContext overflow-auto 兜底。 */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-10 lg:h-full">
            {/* Left: Config Form - 6/10 on large screens */}
            <div className="flex flex-col gap-3 min-w-0 lg:col-span-6">
              {/* Basic Info Card */}
              <div className={cardClassName}>
                <div className={cardHeadClassName}>{t('memory.basicInfo')}</div>
                <div className={cardBodyClassName}>
                  <Form.Item
                    label={t('memory.name')}
                    name="name"
                    rules={[{ required: true, message: `${t('common.inputMsg')}${t('memory.name')}` }]}
                    labelCol={{ style: { width: '92px', textAlign: 'right' } }}
                    wrapperCol={{ flex: 1 }}
                    className="mb-3"
                  >
                    <Input />
                  </Form.Item>
                  <Form.Item
                    label={t('memory.scope')}
                    name="scope"
                    rules={[{ required: true }]}
                    labelCol={{ style: { width: '92px', textAlign: 'right' } }}
                    wrapperCol={{ flex: 1 }}
                    className="mb-3"
                  >
                    <Select disabled>
                      <Select.Option value="personal">{t('memory.personal')}</Select.Option>
                      <Select.Option value="team">{t('memory.team')}</Select.Option>
                    </Select>
                  </Form.Item>
                  <Form.Item
                    label={t('memory.organization')}
                    name="team"
                    rules={[{ required: true, message: `${t('common.selectMsg')}${t('memory.organization')}` }]}
                    labelCol={{ style: { width: '92px', textAlign: 'right' } }}
                    wrapperCol={{ flex: 1 }}
                    className="mb-3"
                  >
                    <GroupTreeSelect multiple />
                  </Form.Item>
                  <Form.Item
                    label={t('memory.introduction')}
                    name="introduction"
                    labelCol={{ style: { width: '92px', textAlign: 'right' } }}
                    wrapperCol={{ flex: 1 }}
                    className="mb-0"
                  >
                    <TextArea rows={3} className="min-h-24" />
                  </Form.Item>
                </div>
              </div>

              {/* Write Rule Card */}
              <div className={`${cardClassName} flex min-h-0 flex-1 flex-col`}>
                <div className={cardHeadClassName}>{t('memory.writeRuleTitle')}</div>
                <div className={`${cardBodyClassName} min-h-0 flex-1`}>
                  <Form.Item
                    name="write_rule"
                    rules={[{ required: true, message: `${t('common.inputMsg')}${t('memory.writeRule')}` }]}
                    label={<span className={labelClassName}>{t('memory.writeRule')}</span>}
                    extra={<span className="text-[11px] text-[var(--color-text-3)]">{t('memory.writeRuleHint')}</span>}
                    className="mb-4 flex min-h-0 flex-1 flex-col"
                  >
                    <TextArea className="min-h-[120px] flex-1 resize-y" />
                  </Form.Item>

                  <Form.Item
                    name="default_model"
                    rules={[{ required: true, message: `${t('common.selectMsg')}${t('memory.defaultModel')}` }]}
                    label={<span className={labelClassName}>{t('memory.defaultModel')}</span>}
                    extra={<span className="text-[11px] text-[var(--color-text-3)]">{t('memory.defaultModelHint')}</span>}
                    className="mb-0"
                  >
                    <Select
                      placeholder="e.g. DeepSeek-V3.1"
                      showSearch
                      optionFilterProp="children"
                    >
                      {models.map((model: any) => (
                        <Select.Option key={model.id} value={model.id}>{model.name}</Select.Option>
                      ))}
                    </Select>
                  </Form.Item>
                </div>
              </div>

              {/* Save Button */}
              <div className="flex justify-end">
                <PermissionWrapper requiredPermissions={['Edit']}>
                  <Button
                    type="primary"
                    htmlType="submit"
                    loading={saving}
                    className="h-8 rounded-lg px-3 text-xs font-semibold"
                  >
                    {t('common.save')}
                  </Button>
                </PermissionWrapper>
              </div>
            </div>

            {/* Right: Test Panel - 4/10 on large screens */}
            <div className="flex flex-col gap-3 min-w-0 lg:col-span-4">
              {/* Test Input Card */}
              <div className={cardClassName}>
                <div className={cardHeadClassName}>{t('memory.testTitle')}</div>
                <div className={cardBodyClassName}>
                  <div>
                    <div className={`${labelClassName} mb-2`}>{t('memory.testInputTitle')}</div>
                    <p className={`${hintClassName} mb-2 mt-0`}>{t('memory.testInputDesc')}</p>
                    <TextArea 
                      rows={5}
                      value={testInput} 
                      onChange={e => setTestInput(e.target.value)}
                      className="min-h-[120px]"
                    />
                  </div>
                  <div className="mt-2 flex items-center gap-2">
                    <span className="text-[13px] text-[var(--color-text-2)]">{t('memory.testReferenceLabel')}</span>
                    <Select 
                      className="w-48"
                      value={testRefId}
                      onChange={handleRefChange}
                      allowClear
                      placeholder={t('memory.testNoReference')}
                    >
                      {memories.map(m => (
                        <Select.Option key={m.id} value={m.id}>{m.owner_username} / {m.id}</Select.Option>
                      ))}
                    </Select>
                    <Button 
                      type="primary" 
                      loading={testing} 
                      onClick={handleTest} 
                      className="ml-auto h-8 rounded-lg px-3 text-xs font-semibold"
                    >
                      {t('memory.testButton')}
                    </Button>
                  </div>
                </div>
              </div>

              {/* Test Result Card */}
              <div className={`${cardClassName} flex min-h-0 flex-1 flex-col`}>
                <div className={`${cardHeadClassName} justify-between`}>
                  <span>{t('memory.testResultTitle')}</span>
                  {testRefId && (
                    <div className="flex bg-[var(--color-fill-2)] p-1 rounded gap-1">
                      <button 
                        type="button"
                        className={`border-0 h-7 px-3 rounded text-xs cursor-pointer transition-all ${activeTab === 'reference' ? 'bg-[var(--color-bg-1)] font-semibold shadow-sm' : 'bg-transparent text-[var(--color-text-3)]'}`}
                        onClick={() => setActiveTab('reference')}
                      >
                        {t('memory.referenceMemory')}
                      </button>
                      <button 
                        type="button"
                        className={`border-0 h-7 px-3 rounded text-xs cursor-pointer transition-all ${activeTab === 'result' ? 'bg-[var(--color-bg-1)] font-semibold shadow-sm' : 'bg-transparent text-[var(--color-text-3)]'}`}
                        onClick={() => setActiveTab('result')}
                      >
                        {t('memory.updatedMemory')}
                      </button>
                    </div>
                  )}
                </div>
                <div className={`${cardBodyClassName} min-h-0 flex-1`}>
                  {!testResult && activeTab === 'result' ? (
                    <div className="flex flex-1 flex-col items-center justify-center rounded-lg border border-[var(--color-border-2)] bg-[var(--color-fill-1)] p-6">
                      <div className="mb-1 text-[13px] font-medium text-[var(--color-text-2)]">
                        {t('memory.testWaiting')}
                      </div>
                      <div className={hintClassName}>{t('memory.testWaitingHint')}</div>
                    </div>
                  ) : activeTab === 'reference' && referenceMemory ? (
                    <div className="flex-1 overflow-auto whitespace-pre-wrap rounded-lg border border-[var(--color-border-2)] bg-[var(--color-fill-1)] p-3 font-mono text-[13px] leading-relaxed">
                      {referenceMemory.content}
                    </div>
                  ) : (
                    <div className="flex-1 overflow-auto whitespace-pre-wrap rounded-lg border border-[var(--color-border-2)] bg-[var(--color-fill-1)] p-3 font-mono text-[13px] leading-relaxed">
                      {testResult?.result || ''}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </Form>
      )}
    </div>
  );
}
