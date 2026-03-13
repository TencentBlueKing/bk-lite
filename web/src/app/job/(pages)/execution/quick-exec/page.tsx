'use client';

import React, { useState, useEffect, useCallback } from 'react';
import {
  Form,
  Input,
  Radio,
  Select,
  Segmented,
  Button,
  Divider,
  message,
  Alert,
  Modal,
} from 'antd';
import { PlusOutlined, ExclamationCircleOutlined } from '@ant-design/icons';
import { useSearchParams, useRouter } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import useJobApi from '@/app/job/api';
import { Script, Playbook, ScriptParam } from '@/app/job/types';
import HostSelectionModal, { HostItem, TargetSourceType } from '@/app/job/components/host-selection-modal';
import ScriptEditor from '@/app/job/components/script-editor';
import Password from '@/components/password';

type ContentSource = 'template' | 'manual';
type TemplateType = 'scriptLibrary' | 'playbook';
type ScriptLang = 'shell' | 'bat' | 'python' | 'powershell';

const DEFAULT_SCRIPT_CONTENT: Record<ScriptLang, string> = {
  shell: `#!/bin/bash

# 任务正常结束
job_success() {
    echo "[INFO] Job completed successfully"
    exit 0
}

# 任务异常结束
job_fail() {
    echo "[ERROR] Job failed"
    exit 1
}

# ---------- 在此处编写脚本逻辑 ----------



# ---------- 结束 ----------
job_success`,
  bat: `@echo off\nREM Enter your batch script here\n`,
  python: `#!/usr/bin/env python3\n# Enter your Python script here\n`,
  powershell: `# Enter your PowerShell script here\n`,
};

const QuickExecPage = () => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const router = useRouter();
  const { isLoading: isApiReady } = useApiClient();
  const { getScriptList, getScriptDetail, getPlaybookList, getPlaybookDetail, quickExecute, playbookExecute, getEnabledDangerousRules } = useJobApi();
  const [form] = Form.useForm();

  const [contentSource, setContentSource] = useState<ContentSource>('template');
  const [templateType, setTemplateType] = useState<TemplateType>('scriptLibrary');
  const [selectedTemplate, setSelectedTemplate] = useState<number | undefined>(undefined);
  const [targetSource, setTargetSource] = useState<TargetSourceType>('target_manager');

  const [hostModalOpen, setHostModalOpen] = useState(false);
  const [selectedHostKeys, setSelectedHostKeys] = useState<string[]>([]);
  const [selectedHosts, setSelectedHosts] = useState<HostItem[]>([]);

  // Template lists from API
  const [scriptList, setScriptList] = useState<Script[]>([]);
  const [playbookList, setPlaybookList] = useState<Playbook[]>([]);
  const [templateParams, setTemplateParams] = useState<ScriptParam[]>([]);
  const [initialized, setInitialized] = useState(false);
  const [scriptLang, setScriptLang] = useState<ScriptLang>('shell');

  const fetchScriptList = useCallback(async () => {
    try {
      const res = await getScriptList({ page: 1, page_size: 100 });
      setScriptList(res.items || []);
      return res.items || [];
    } catch {
      return [];
    }
  }, []);

  const fetchPlaybookList = useCallback(async () => {
    try {
      const res = await getPlaybookList({ page: 1, page_size: 100 });
      setPlaybookList(res.items || []);
      return res.items || [];
    } catch {
      return [];
    }
  }, []);

  const handleTemplateSelect = useCallback(async (id: number | undefined, type?: TemplateType) => {
    setSelectedTemplate(id);
    if (!id) {
      setTemplateParams([]);
      return;
    }
    const currentType = type ?? templateType;
    try {
      if (currentType === 'scriptLibrary') {
        const detail = await getScriptDetail(id);
        setTemplateParams(detail.params || []);
      } else {
        const detail = await getPlaybookDetail(id);
        setTemplateParams(detail.params || []);
      }
    } catch {
      setTemplateParams([]);
    }
  }, [templateType]);

  // Initialize: fetch lists and handle script_id from URL
  useEffect(() => {
    if (isApiReady || initialized) return;
    setInitialized(true);

    const init = async () => {
      const [scripts, playbooks] = await Promise.all([fetchScriptList(), fetchPlaybookList()]);
      const scriptIdParam = searchParams.get('script_id');
      const playbookIdParam = searchParams.get('playbook_id');
      if (scriptIdParam) {
        const scriptId = Number(scriptIdParam);
        const script = scripts.find((s: Script) => s.id === scriptId);
        if (script) {
          setContentSource('template');
          setTemplateType('scriptLibrary');
          setSelectedTemplate(scriptId);
          form.setFieldsValue({ jobName: script.name });
          try {
            const detail = await getScriptDetail(scriptId);
            setTemplateParams(detail.params || []);
          } catch {
            // ignore
          }
        }
      } else if (playbookIdParam) {
        const playbookId = Number(playbookIdParam);
        const playbook = playbooks.find((p: Playbook) => p.id === playbookId) || (await getPlaybookDetail(playbookId).catch(() => null));
        if (playbook) {
          setContentSource('template');
          setTemplateType('playbook');
          setSelectedTemplate(playbookId);
          form.setFieldsValue({ jobName: playbook.name });
          setTemplateParams(playbook.params || []);
        }
      }
    };
    init();
  }, [isApiReady]);

  const currentTemplateOptions =
    templateType === 'scriptLibrary'
      ? scriptList.map((s) => ({ label: s.name, value: s.id }))
      : playbookList.map((p) => ({ label: p.name, value: p.id }));

  const handleHostConfirm = (keys: string[], hosts: HostItem[]) => {
    setSelectedHostKeys(keys);
    setSelectedHosts(hosts);
    setHostModalOpen(false);
  };

  const handleContentSourceChange = (val: ContentSource) => {
    setContentSource(val);
    setSelectedTemplate(undefined);
    setTemplateParams([]);
  };

  const handleTemplateTypeChange = (val: string | number) => {
    if (targetSource === 'node_manager' && val === 'playbook') {
      return;
    }
    setTemplateType(val as TemplateType);
    setSelectedTemplate(undefined);
    setTemplateParams([]);
  };

  const handleTargetSourceChange = (val: TargetSourceType) => {
    setTargetSource(val);
    setSelectedHostKeys([]);
    setSelectedHosts([]);
    if (val === 'node_manager' && templateType === 'playbook') {
      setTemplateType('scriptLibrary');
      setSelectedTemplate(undefined);
      setTemplateParams([]);
    }
  };

  const [executeLoading, setExecuteLoading] = useState(false);

  // Check script content against dangerous rules
  const checkDangerousRules = async (scriptContent: string): Promise<{ canExecute: boolean; needConfirm: boolean; matchedRules: string[] }> => {
    try {
      const rules = await getEnabledDangerousRules();
      const matchedForbidden: string[] = [];
      const matchedConfirm: string[] = [];

      // Check forbidden rules
      for (const pattern of rules.forbidden || []) {
        if (scriptContent.includes(pattern)) {
          matchedForbidden.push(pattern);
        }
      }

      // Check confirm rules
      for (const pattern of rules.confirm || []) {
        if (scriptContent.includes(pattern)) {
          matchedConfirm.push(pattern);
        }
      }

      if (matchedForbidden.length > 0) {
        return { canExecute: false, needConfirm: false, matchedRules: matchedForbidden };
      }

      if (matchedConfirm.length > 0) {
        return { canExecute: true, needConfirm: true, matchedRules: matchedConfirm };
      }

      return { canExecute: true, needConfirm: false, matchedRules: [] };
    } catch {
      // If API fails, allow execution
      return { canExecute: true, needConfirm: false, matchedRules: [] };
    }
  };

  // Execute the actual job
  const doExecute = async (values: any, scriptContent?: string) => {
    const params: Record<string, unknown> = {};
    templateParams.forEach((param) => {
      const value = values[`param_${param.name}`];
      params[param.name] = value ?? '';
    });

    const timeout = values.timeout ? Number(values.timeout) : 600;
    
    // Convert to target_source + target_list format
    const target_source = targetSource === 'node_manager' ? 'node_mgmt' : 'manual';
    const target_list = selectedHosts.map((h) => ({
      ...(targetSource === 'node_manager' 
        ? { node_id: h.key } 
        : { target_id: Number(h.key) }),
      name: h.hostName,
      ip: h.ipAddress,
      os: h.osType?.toLowerCase() as 'linux' | 'windows',
    }));

    if (contentSource === 'template') {
      if (templateType === 'scriptLibrary') {
        await quickExecute({
          name: values.jobName,
          script_id: selectedTemplate,
          target_source,
          target_list,
          params,
          timeout,
        });
      } else {
        await playbookExecute({
          name: values.jobName,
          playbook_id: selectedTemplate!,
          target_source,
          target_list,
          params,
          timeout,
        });
      }
    } else {
      await quickExecute({
        name: values.jobName,
        script_type: scriptLang,
        script_content: scriptContent!,
        target_source,
        target_list,
        params,
        timeout,
      });
    }

    message.success(t('job.executeSuccess'));
    router.push('/job/execution/job-record');
  };

  const handleExecute = async () => {
    try {
      const values = await form.validateFields();
      
      if (selectedHosts.length === 0) {
        message.error(t('job.selectTargetHostRequired'));
        return;
      }

      setExecuteLoading(true);

      if (contentSource === 'template') {
        if (templateType === 'scriptLibrary') {
          if (!selectedTemplate) {
            message.error(t('job.selectTemplate'));
            setExecuteLoading(false);
            return;
          }
        } else {
          if (!selectedTemplate) {
            message.error(t('job.selectTemplate'));
            setExecuteLoading(false);
            return;
          }
        }
        // Template mode: execute directly without dangerous rule check
        await doExecute(values);
      } else {
        // Manual input mode: check dangerous rules first
        const scriptContentObj = values.scriptContent;
        if (!scriptContentObj || !scriptContentObj[scriptLang]) {
          message.error(t('job.scriptContentRequired'));
          setExecuteLoading(false);
          return;
        }

        const scriptContent = scriptContentObj[scriptLang];
        const checkResult = await checkDangerousRules(scriptContent);

        if (!checkResult.canExecute) {
          // Forbidden: show error and block execution
          Modal.error({
            title: t('job.dangerousCommandDetected'),
            content: (
              <div>
                <p>{t('job.forbiddenCommandMessage')}</p>
                <ul className="mt-2 list-disc pl-4">
                  {checkResult.matchedRules.map((rule, idx) => (
                    <li key={idx} className="text-red-500 font-mono">{rule}</li>
                  ))}
                </ul>
              </div>
            ),
            okText: t('common.confirm'),
          });
          setExecuteLoading(false);
          return;
        }

        if (checkResult.needConfirm) {
          // Confirm: show confirmation modal
          Modal.confirm({
            title: t('job.dangerousCommandWarning'),
            icon: <ExclamationCircleOutlined style={{ color: '#faad14' }} />,
            content: (
              <div>
                <p>{t('job.confirmCommandMessage')}</p>
                <ul className="mt-2 list-disc pl-4">
                  {checkResult.matchedRules.map((rule, idx) => (
                    <li key={idx} className="text-orange-500 font-mono">{rule}</li>
                  ))}
                </ul>
                <p className="mt-3 text-gray-500">{t('job.confirmExecuteQuestion')}</p>
              </div>
            ),
            okText: t('job.confirmExecute'),
            okButtonProps: { danger: true },
            cancelText: t('common.cancel'),
            onOk: async () => {
              try {
                await doExecute(values, scriptContent);
              } catch {
                // error handled by interceptor
              } finally {
                setExecuteLoading(false);
              }
            },
            onCancel: () => {
              setExecuteLoading(false);
            },
          });
          return;
        }

        // No dangerous commands: execute directly
        await doExecute(values, scriptContent);
      }
    } catch {
      // validation or API error
    } finally {
      setExecuteLoading(false);
    }
  };

  return (
    <div className="w-full h-full overflow-auto p-0">

      <div
        className="rounded-lg px-6 py-4 mb-4"
        style={{
          background: 'var(--color-bg-1)',
          border: '1px solid var(--color-border-1)',
        }}
      >
        <h2 className="text-base font-medium m-0 mb-1" style={{ color: 'var(--color-text-1)' }}>
          {t('job.quickExec')}
        </h2>
        <p className="text-sm m-0" style={{ color: 'var(--color-text-3)' }}>
          {t('job.quickExecDesc')}
        </p>
      </div>


      <div
        className="rounded-lg px-6 py-6"
        style={{
          background: 'var(--color-bg-1)',
          border: '1px solid var(--color-border-1)',
        }}
      >
        <Form
          form={form}
          layout="vertical"
          className="max-w-[720px]"
          initialValues={{ timeout: '600', scriptContent: DEFAULT_SCRIPT_CONTENT }}
        >

          <Form.Item
            label={t('job.jobName')}
            name="jobName"
            rules={[{ required: true, message: `${t('job.jobNamePlaceholder')}` }]}
          >
            <Input placeholder={t('job.jobNamePlaceholder')} />
          </Form.Item>


          <Form.Item label={t('job.targetSource')} required>
            <Radio.Group
              value={targetSource}
              onChange={(e) => handleTargetSourceChange(e.target.value)}
            >
              <Radio value="node_manager">{t('job.nodeManager')}</Radio>
              <Radio value="target_manager">{t('job.targetManager')}</Radio>
            </Radio.Group>
          </Form.Item>


          <Form.Item
            label={t('job.targetHost')}
            required
          >
            <div className="flex items-center gap-3">
              <Button
                type="dashed"
                icon={<PlusOutlined />}
                onClick={() => setHostModalOpen(true)}
              >
                {t('job.addTargetHost')}
              </Button>
              <span className="text-sm" style={{ color: 'var(--color-text-3)' }}>
                {t('job.selectedHosts').replace('{count}', String(selectedHosts.length))}
              </span>
            </div>
          </Form.Item>


          <Form.Item label={t('job.contentSource')} required>
            <Radio.Group
              value={contentSource}
              onChange={(e) => handleContentSourceChange(e.target.value)}
            >
              <Radio value="template">{t('job.jobTemplate')}</Radio>
              <Radio value="manual">{t('job.manualInput')}</Radio>
            </Radio.Group>
          </Form.Item>


          {contentSource === 'template' && (
            <>
              {targetSource === 'node_manager' && (
                <Alert
                  className="mb-4"
                  message={t('job.nodeManagerPlaybookNotSupported')}
                  type="warning"
                  showIcon
                />
              )}
              <Form.Item label={t('job.selectTemplate')} required>
                <div className="flex flex-col gap-3">
                  <Segmented
                    className="w-fit"
                    value={templateType}
                    onChange={handleTemplateTypeChange}
                    options={[
                      { label: t('job.scriptLibrary'), value: 'scriptLibrary' },
                      { label: 'Playbook', value: 'playbook', disabled: targetSource === 'node_manager' },
                    ]}
                  />
                  <Select
                    className="w-full"
                    placeholder={t('job.selectTemplate')}
                    value={selectedTemplate}
                    onChange={(val) => handleTemplateSelect(val)}
                    options={currentTemplateOptions}
                    allowClear
                    showSearch
                    filterOption={(input, option) =>
                      (option?.label as string)?.toLowerCase().includes(input.toLowerCase())
                    }
                  />
                </div>
              </Form.Item>


              {templateParams.length > 0 && (
                <>
                  <div className="text-sm font-medium mb-2" style={{ color: 'var(--color-text-2)' }}>
                    {t('job.execParams')}
                  </div>
                  {templateParams.map((param) => (
                    <Form.Item
                      key={param.name}
                      label={param.name}
                      name={`param_${param.name}`}
                      initialValue={param.default || undefined}
                      tooltip={param.description || undefined}
                      rules={[{ required: true, message: t('job.paramRequired', undefined, { name: param.name }) }]}
                    >
                      {param.is_encrypted ? (
                        <Password
                          placeholder={param.description || param.name}
                          clickToEdit={!!param.default}
                        />
                      ) : (
                        <Input
                          placeholder={param.description || param.name}
                        />
                      )}
                    </Form.Item>
                  ))}
                </>
              )}
            </>
          )}


          {contentSource === 'manual' && (
            <>
              <Form.Item 
                label={t('job.scriptContent')} 
                name="scriptContent"
                rules={[{ 
                  required: true, 
                  validator: (_, value) => {
                    if (!value || !value[scriptLang] || value[scriptLang].trim() === '') {
                      return Promise.reject(new Error(t('job.scriptContentRequired')));
                    }
                    return Promise.resolve();
                  }
                }]}
              >
                <ScriptEditor 
                  activeLang={scriptLang}
                  onLangChange={setScriptLang}
                />
              </Form.Item>

              <Form.Item label={t('job.execParams')} name="execParams">
                <Input.TextArea
                  rows={3}
                  placeholder={t('job.execParamsPlaceholder')}
                />
              </Form.Item>
            </>
          )}


          <Form.Item label={t('job.timeout')} name="timeout">
            <Input className="w-[200px]" />
          </Form.Item>
          <p className="text-xs -mt-4 mb-6" style={{ color: 'var(--color-text-3)' }}>
            {t('job.timeoutHint')}
          </p>

          <Divider />

          <Button type="primary" loading={executeLoading} onClick={handleExecute}>
            {t('job.executeNow')}
          </Button>
        </Form>
      </div>


      <HostSelectionModal
        open={hostModalOpen}
        selectedKeys={selectedHostKeys}
        source={targetSource}
        onConfirm={handleHostConfirm}
        onCancel={() => setHostModalOpen(false)}
      />
    </div>
  );
};

export default QuickExecPage;
