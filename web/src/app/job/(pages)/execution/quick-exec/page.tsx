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
  Tooltip,
  Modal,
} from 'antd';
import { ExclamationCircleOutlined, InfoCircleOutlined } from '@ant-design/icons';
import { useSearchParams, useRouter } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import useJobApi from '@/app/job/api';
import { Script, Playbook, ScriptParam } from '@/app/job/types';
import HostSelectionModal, { HostItem, TargetSourceType } from '@/app/job/components/host-selection-modal';
import { AddTargetHostButton, TargetSourceSelector } from '@/app/job/components/target-selection-controls';
import ScriptEditor from '@/app/job/components/script-editor';
import Password from '@/components/password';

type ContentSource = 'template' | 'manual';
type TemplateType = 'scriptLibrary' | 'playbook';
type ScriptLang = 'shell' | 'bat' | 'python' | 'powershell';
const QUICK_EXEC_REPLAY_STORAGE_KEY = 'job.quick-exec.replay';

const extractExecutionId = (response: any): number | undefined => {
  const candidates = [
    response?.id,
    response?.execution_id,
    response?.job_id,
    response?.data?.id,
    response?.data?.execution_id,
    response?.data?.job_id,
  ];

  const matched = candidates.find((value) => typeof value === 'number' || (typeof value === 'string' && value.trim() !== ''));
  if (matched === undefined) return undefined;

  const numericId = Number(matched);
  return Number.isFinite(numericId) ? numericId : undefined;
};

interface QuickExecReplayDraft {
  jobName?: string;
  timeout?: string;
  targetSource?: TargetSourceType;
  selectedHosts?: HostItem[];
  templateType?: TemplateType;
  scriptId?: number;
  playbookId?: number;
  params?: Record<string, unknown> | Array<{ name?: string; value?: unknown }>;
  scriptType?: ScriptLang;
  scriptContent?: string;
}

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
  const [editedTemplateParams, setEditedTemplateParams] = useState<Record<string, boolean>>({});
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
      setEditedTemplateParams({});
      return;
    }
    setEditedTemplateParams({});
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

  const applyReplayDraft = useCallback(async (draft: QuickExecReplayDraft, scripts: Script[], playbooks: Playbook[]) => {
    const hosts = draft.selectedHosts || [];
    setTargetSource(draft.targetSource || 'target_manager');
    setSelectedHostKeys(hosts.map((host) => host.key));
    setSelectedHosts(hosts);

    if (draft.scriptContent) {
      const draftScriptType = draft.scriptType || 'shell';
      setContentSource('manual');
      setScriptLang(draftScriptType);
      form.setFieldsValue({
        jobName: draft.jobName,
        timeout: draft.timeout || '600',
        execParams: Array.isArray(draft.params) ? String(draft.params[0]?.value || '') : '',
        scriptContent: {
          ...DEFAULT_SCRIPT_CONTENT,
          [draftScriptType]: draft.scriptContent,
        },
      });
      return;
    }

    const resolvedTemplateType = draft.templateType || (draft.playbookId ? 'playbook' : 'scriptLibrary');
    setContentSource('template');
    setTemplateType(resolvedTemplateType);

    if (resolvedTemplateType === 'playbook' && draft.playbookId) {
      const playbookId = draft.playbookId;
      const playbook = playbooks.find((item) => item.id === playbookId) || (await getPlaybookDetail(playbookId).catch(() => null));
      if (playbook) {
        setSelectedTemplate(playbookId);
        setTemplateParams(playbook.params || []);
        form.setFieldsValue({
          jobName: draft.jobName || playbook.name,
          timeout: draft.timeout || '600',
        });
      }
    } else if (draft.scriptId) {
      const scriptId = draft.scriptId;
      const script = scripts.find((item) => item.id === scriptId) || (await getScriptDetail(scriptId).catch(() => null));
      if (script) {
        setSelectedTemplate(scriptId);
        setTemplateParams(script.params || []);
        form.setFieldsValue({
          jobName: draft.jobName || script.name,
          timeout: draft.timeout || '600',
        });
      }
    }

    if (draft.params) {
      const paramValues = Array.isArray(draft.params)
        ? draft.params.reduce<Record<string, unknown>>((acc, item) => {
          if (item.name) {
            acc[`param_${item.name}`] = item.value;
          }
          return acc;
        }, {})
        : Object.entries(draft.params).reduce<Record<string, unknown>>((acc, [key, value]) => {
          acc[`param_${key}`] = value;
          return acc;
        }, {});

      form.setFieldsValue(paramValues);
    }
  }, [form, getPlaybookDetail, getScriptDetail]);

  // Initialize: fetch lists and handle script_id from URL
  useEffect(() => {
    if (isApiReady || initialized) return;
    setInitialized(true);

    const init = async () => {
      const [scripts, playbooks] = await Promise.all([fetchScriptList(), fetchPlaybookList()]);
      const replayDraftRaw = typeof window !== 'undefined' ? window.sessionStorage.getItem(QUICK_EXEC_REPLAY_STORAGE_KEY) : null;
      if (replayDraftRaw) {
        window.sessionStorage.removeItem(QUICK_EXEC_REPLAY_STORAGE_KEY);
        try {
          const replayDraft = JSON.parse(replayDraftRaw) as QuickExecReplayDraft;
          await applyReplayDraft(replayDraft, scripts, playbooks);
          return;
        } catch {
          // ignore broken draft payload
        }
      }

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
  }, [applyReplayDraft, isApiReady]);

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
    setEditedTemplateParams({});
  };

  const handleTemplateTypeChange = (val: string | number) => {
    if (targetSource === 'node_manager' && val === 'playbook') {
      return;
    }
    setTemplateType(val as TemplateType);
    setSelectedTemplate(undefined);
    setTemplateParams([]);
    setEditedTemplateParams({});
  };

  const handleTargetSourceChange = (val: TargetSourceType) => {
    setTargetSource(val);
    setSelectedHostKeys([]);
    setSelectedHosts([]);
    if (val === 'node_manager' && templateType === 'playbook') {
      setTemplateType('scriptLibrary');
      setSelectedTemplate(undefined);
      setTemplateParams([]);
      setEditedTemplateParams({});
    }
  };

  const [executeLoading, setExecuteLoading] = useState(false);

  const normalizeScriptContent = (content: string) => content.trim();

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

  const validateScriptContent = async (_: unknown, value?: Record<ScriptLang, string>) => {
    const currentScriptContent = normalizeScriptContent(value?.[scriptLang] || '');
    if (!currentScriptContent) {
      throw new Error(t('job.scriptContentRequired'));
    }

    const checkResult = await checkDangerousRules(currentScriptContent);
    if (!checkResult.canExecute) {
      throw new Error(`${t('job.forbiddenCommandMessage')} ${checkResult.matchedRules.join('、')}`);
    }

    return Promise.resolve();
  };

  // Execute the actual job
  const doExecute = async (values: any, scriptContent?: string) => {
    const templateParamsPayload = templateParams.map((param) => {
      const currentValue = values[`param_${param.name}`] ?? '';
      const defaultValue = param.default ?? '';
      return {
        name: param.name,
        value: currentValue,
        is_modified: currentValue !== defaultValue || !!editedTemplateParams[param.name],
      };
    });
    let executionResult: any;

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
        executionResult = await quickExecute({
          name: values.jobName,
          script_id: selectedTemplate,
          target_source,
          target_list,
          params: templateParamsPayload,
          timeout,
        });
      } else {
        executionResult = await playbookExecute({
          name: values.jobName,
          playbook_id: selectedTemplate!,
          target_source,
          target_list,
          params: templateParamsPayload,
          timeout,
        });
      }
    } else {
      const execParamsText = String(values.execParams || '').trim();
      executionResult = await quickExecute({
        name: values.jobName,
        script_type: scriptLang,
        script_content: scriptContent!,
        target_source,
        target_list,
        params: execParamsText ? [{ value: execParamsText }] : [],
        timeout,
      });
    }

    message.success(t('job.executeSuccess'));
    const executionId = extractExecutionId(executionResult);
    router.replace(executionId ? `/job/execution/job-record?id=${executionId}` : '/job/execution/job-record');
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

        const scriptContent = normalizeScriptContent(scriptContentObj[scriptLang]);
        form.setFieldValue('scriptContent', {
          ...scriptContentObj,
          [scriptLang]: scriptContent,
        });
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
          className="w-full"
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
            <TargetSourceSelector
              value={targetSource}
              onChange={handleTargetSourceChange}
            />
          </Form.Item>


          <Form.Item
            label={t('job.targetHost')}
            required
          >
            <AddTargetHostButton
              count={selectedHosts.length}
              onClick={() => setHostModalOpen(true)}
            />
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
              <Form.Item label={t('job.selectTemplate')} required>
                <div className="flex flex-col gap-3">
                  <Segmented
                    className="w-fit"
                    value={templateType}
                    onChange={handleTemplateTypeChange}
                    options={[
                      { label: t('job.scriptLibrary'), value: 'scriptLibrary' },
                      {
                        label: (
                          <span
                            className="flex items-center gap-1.5"
                            style={{
                              color: targetSource === 'node_manager' ? 'var(--color-text-4)' : undefined,
                            }}
                          >
                            <span>Playbook</span>
                            {targetSource === 'node_manager' && (
                              <Tooltip title={t('job.nodeManagerPlaybookNotSupported')}>
                                <span
                                  className="inline-flex items-center text-[12px] text-[#faad14]"
                                  onClick={(event) => event.stopPropagation()}
                                >
                                  <InfoCircleOutlined />
                                </span>
                              </Tooltip>
                            )}
                          </span>
                        ),
                        value: 'playbook',
                      },
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
                          onReset={() =>
                            setEditedTemplateParams((prev) => ({
                              ...prev,
                              [param.name]: true,
                            }))
                          }
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
                validateTrigger="onBlur"
                rules={[{ validator: validateScriptContent }]}
              >
                <ScriptEditor
                  activeLang={scriptLang}
                  onLangChange={setScriptLang}
                  onBlur={() => {
                    void form.validateFields(['scriptContent']);
                  }}
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
            <Input className="w-full" />
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
