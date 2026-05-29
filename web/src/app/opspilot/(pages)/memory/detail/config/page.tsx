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

  // Prototype-based styles
  const cardStyle: React.CSSProperties = {
    border: '1px solid var(--color-border-2, #dde5f0)',
    borderRadius: '10px',
    background: 'var(--color-bg-1, #fff)',
    overflow: 'hidden',
  };

  const cardHeadStyle: React.CSSProperties = {
    height: '40px',
    borderBottom: '1px solid var(--color-border-2, #e7edf6)',
    padding: '0 14px',
    display: 'flex',
    alignItems: 'center',
    background: 'var(--color-fill-2, #f7f9fc)',
    color: 'var(--color-text-1, #314660)',
    fontSize: '13px',
    fontWeight: 700,
  };

  const cardBodyStyle: React.CSSProperties = {
    padding: '14px',
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
  };

  const labelStyle: React.CSSProperties = {
    fontSize: '13px',
    color: 'var(--color-text-2, #5c6d84)',
    fontWeight: 600,
  };

  const hintStyle: React.CSSProperties = {
    marginTop: '6px',
    fontSize: '11px',
    lineHeight: 1.6,
    color: 'var(--color-text-3, #8494ab)',
  };

  return (
    <div className="relative h-full">
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
          className="h-full"
        >
          <div className="flex gap-4 h-full">
            {/* Left: Config Form - flex-[6] for 6:4 ratio */}
            <div className="flex-[6] flex flex-col gap-3 min-w-0">
              {/* Basic Info Card */}
              <div style={cardStyle}>
                <div style={cardHeadStyle}>{t('memory.basicInfo')}</div>
                <div style={cardBodyStyle}>
                  <Form.Item 
                    label={t('memory.name')} 
                    name="name" 
                    rules={[{ required: true, message: `${t('common.inputMsg')}${t('memory.name')}` }]}
                    labelCol={{ style: { width: '92px', textAlign: 'right' } }}
                    wrapperCol={{ flex: 1 }}
                    style={{ marginBottom: '12px' }}
                  >
                    <Input />
                  </Form.Item>
                  <Form.Item 
                    label={t('memory.scope')} 
                    name="scope" 
                    rules={[{ required: true }]}
                    labelCol={{ style: { width: '92px', textAlign: 'right' } }}
                    wrapperCol={{ flex: 1 }}
                    style={{ marginBottom: '12px' }}
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
                    style={{ marginBottom: '12px' }}
                  >
                    <GroupTreeSelect multiple />
                  </Form.Item>
                  <Form.Item 
                    label={t('memory.introduction')} 
                    name="introduction"
                    labelCol={{ style: { width: '92px', textAlign: 'right' } }}
                    wrapperCol={{ flex: 1 }}
                    style={{ marginBottom: 0 }}
                  >
                    <TextArea rows={3} style={{ minHeight: '96px' }} />
                  </Form.Item>
                </div>
              </div>

              {/* Write Rule Card */}
              <div style={{ ...cardStyle, flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
                <div style={cardHeadStyle}>{t('memory.writeRuleTitle')}</div>
                <div style={{ ...cardBodyStyle, flex: 1, minHeight: 0 }}>
                  <Form.Item 
                    name="write_rule" 
                    rules={[{ required: true, message: `${t('common.inputMsg')}${t('memory.writeRule')}` }]}
                    label={<span style={labelStyle}>{t('memory.writeRule')}</span>}
                    extra={<span style={{ fontSize: '11px', color: 'var(--color-text-3, #8494ab)' }}>{t('memory.writeRuleHint')}</span>}
                    style={{ flex: 1, marginBottom: '16px', display: 'flex', flexDirection: 'column', minHeight: 0 }}
                    className="flex-1-form-item"
                  >
                    <TextArea style={{ flex: 1, minHeight: '120px', resize: 'vertical' }} />
                  </Form.Item>
                  
                  <Form.Item 
                    name="default_model" 
                    rules={[{ required: true, message: `${t('common.selectMsg')}${t('memory.defaultModel')}` }]}
                    label={<span style={labelStyle}>{t('memory.defaultModel')}</span>}
                    extra={<span style={{ fontSize: '11px', color: 'var(--color-text-3, #8494ab)' }}>{t('memory.defaultModelHint')}</span>}
                    style={{ marginBottom: 0 }}
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
                    style={{ height: '32px', borderRadius: '8px', padding: '0 12px', fontSize: '12px', fontWeight: 600 }}
                  >
                    {t('common.save')}
                  </Button>
                </PermissionWrapper>
              </div>
            </div>

            {/* Right: Test Panel - flex-[4] for 6:4 ratio */}
            <div className="flex-[4] flex flex-col gap-3 min-w-0">
              {/* Test Input Card */}
              <div style={cardStyle}>
                <div style={cardHeadStyle}>{t('memory.testTitle')}</div>
                <div style={cardBodyStyle}>
                  <div>
                    <div style={labelStyle} className="mb-2">{t('memory.testInputTitle')}</div>
                    <p style={hintStyle} className="mb-2 mt-0">{t('memory.testInputDesc')}</p>
                    <TextArea 
                      rows={5}
                      value={testInput} 
                      onChange={e => setTestInput(e.target.value)}
                      style={{ minHeight: '120px' }}
                    />
                  </div>
                  <div className="flex items-center gap-2 mt-2">
                    <span style={{ fontSize: '13px', color: 'var(--color-text-2, #5c6d84)' }}>{t('memory.testReferenceLabel')}</span>
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
                      className="ml-auto"
                      style={{ height: '32px', borderRadius: '8px', padding: '0 12px', fontSize: '12px', fontWeight: 600 }}
                    >
                      {t('memory.testButton')}
                    </Button>
                  </div>
                </div>
              </div>

              {/* Test Result Card */}
              <div style={{ ...cardStyle, flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
                <div style={{ ...cardHeadStyle, justifyContent: 'space-between' }}>
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
                <div style={{ ...cardBodyStyle, flex: 1, minHeight: 0 }}>
                  {!testResult && activeTab === 'result' ? (
                    <div 
                      className="flex-1 flex flex-col justify-center items-center"
                      style={{ 
                        border: '1px solid var(--color-border-2, #dde5f0)', 
                        borderRadius: '8px', 
                        background: 'var(--color-fill-1, #f7f9fc)',
                        padding: '24px',
                      }}
                    >
                      <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--color-text-2, #5c6d84)', marginBottom: '4px' }}>
                        {t('memory.testWaiting')}
                      </div>
                      <div style={hintStyle}>{t('memory.testWaitingHint')}</div>
                    </div>
                  ) : activeTab === 'reference' && referenceMemory ? (
                    <div 
                      className="flex-1 overflow-auto"
                      style={{ 
                        padding: '12px', 
                        background: 'var(--color-fill-1, #f7f9fc)', 
                        borderRadius: '8px', 
                        border: '1px solid var(--color-border-2, #dde5f0)', 
                        fontSize: '13px', 
                        lineHeight: 1.6, 
                        fontFamily: 'monospace',
                        whiteSpace: 'pre-wrap',
                      }}
                    >
                      {referenceMemory.content}
                    </div>
                  ) : (
                    <div 
                      className="flex-1 overflow-auto"
                      style={{ 
                        padding: '12px', 
                        background: 'var(--color-fill-1, #f7f9fc)', 
                        borderRadius: '8px', 
                        border: '1px solid var(--color-border-2, #dde5f0)', 
                        fontSize: '13px', 
                        lineHeight: 1.6, 
                        fontFamily: 'monospace',
                        whiteSpace: 'pre-wrap',
                      }}
                    >
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
