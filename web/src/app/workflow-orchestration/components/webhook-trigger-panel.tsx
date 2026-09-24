'use client';

import { CopyOutlined } from '@ant-design/icons';
import { App, Button, Segmented, Space, Tag, Tooltip } from 'antd';
import { useCallback, useState } from 'react';

import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';
import type { PaginatedResponse, WorkflowTriggerRecord } from '../lib/types';
import { useAutoRequest, useRequestCoordinator } from '../lib/use-request-coordinator';
import { WorkflowPermission } from './workflow-permission';

const API = '/workflow_orchestration/api';
const TEST_PATH = '/openapi/v1/workflow-orchestration/webhook-test';
const PRODUCTION_PATH = '/openapi/v1/workflow-orchestration/trigger';

export interface WebhookTestSession {
  token: string;
  timeout_seconds: number;
}

function absoluteUrl(path: string) {
  if (typeof window === 'undefined') return path;
  return `${window.location.origin}${path}`;
}

export function WebhookTriggerPanel({
  workflowId,
  nodeKey,
  currentVersion,
  testSession,
  testBusy,
  testError,
  onCancelTest,
}: {
  workflowId: number | null;
  nodeKey: string;
  currentVersion: number;
  testSession?: WebhookTestSession;
  testBusy: boolean;
  testError: string;
  onCancelTest: () => void;
}) {
  const { get } = useApiClient();
  const { message } = App.useApp();
  const { t } = useTranslation();
  const [entry, setEntry] = useState<'test' | 'production'>('test');
  const [runtimeTrigger, setRuntimeTrigger] = useState<WorkflowTriggerRecord>();
  const [loading, setLoading] = useState(false);
  const coordinator = useRequestCoordinator(setLoading);

  const loadRuntimeTrigger = useCallback(async () => {
    if (!workflowId || currentVersion <= 0) return;
    const ticket = coordinator.begin({ visible: true });
    if (!ticket) return;
    try {
      const response = await get<PaginatedResponse<WorkflowTriggerRecord>>(
        `${API}/triggers/?workflow_id=${workflowId}&page_size=100`,
        { signal: ticket.signal },
      );
      if (!coordinator.shouldApply(ticket)) return;
      setRuntimeTrigger((response?.items || []).find((item) => item.node_key === nodeKey && item.trigger_type === 'WEBHOOK'));
    } catch {
      if (coordinator.shouldApply(ticket)) setRuntimeTrigger(undefined);
    } finally {
      coordinator.finish(ticket);
    }
  }, [coordinator, currentVersion, get, nodeKey, workflowId]);

  useAutoRequest(
    workflowId && currentVersion > 0 ? `webhook-trigger-access:${workflowId}:${nodeKey}:${currentVersion}` : undefined,
    loadRuntimeTrigger,
  );

  const endpoint = entry === 'test' ? TEST_PATH : PRODUCTION_PATH;
  const payload = entry === 'test'
    ? {
      token: testSession?.token || '<点击“监听测试请求”后自动生成>',
      body: { example: '请替换为真实业务数据' },
    }
    : {
      trigger_id: runtimeTrigger?.id || '<发布后自动生成>',
      idempotency_key: '<请求唯一 ID，例如告警 ID 或 UUID>',
      inputs: { body: { example: '请替换为真实业务数据' } },
    };
  const payloadText = JSON.stringify(payload, null, 2);
  const parameterNotes = entry === 'test'
    ? [
      { name: 'Authorization', generated: false, owner: t('workflowOrchestration.editor.callerProvides', '调用方填写'), description: t('workflowOrchestration.editor.authorizationParameterHint', '请求头中携带 Bearer API Token') },
      { name: 'token', generated: true, owner: t('workflowOrchestration.editor.platformGenerates', '平台生成'), description: t('workflowOrchestration.editor.webhookTestTokenHint', '点击“监听测试请求”后自动生成，限时且只用于本次监听') },
      { name: 'body', generated: false, owner: t('workflowOrchestration.editor.callerProvides', '调用方填写'), description: t('workflowOrchestration.editor.webhookBodyHint', '本次 Webhook 的业务 JSON，捕获后作为流程输入') },
    ]
    : [
      { name: 'Authorization', generated: false, owner: t('workflowOrchestration.editor.callerProvides', '调用方填写'), description: t('workflowOrchestration.editor.authorizationParameterHint', '请求头中携带 Bearer API Token') },
      { name: 'trigger_id', generated: true, owner: t('workflowOrchestration.editor.platformGenerates', '平台生成'), description: t('workflowOrchestration.editor.webhookTriggerIdHint', '发布后自动绑定当前 Webhook 入口，复制示例即可') },
      { name: 'idempotency_key', generated: false, owner: t('workflowOrchestration.editor.callerProvides', '调用方填写'), description: t('workflowOrchestration.editor.webhookIdempotencyHint', '本次请求的唯一标识；重试时复用同一值，避免重复执行') },
      { name: 'inputs.body', generated: false, owner: t('workflowOrchestration.editor.callerProvides', '调用方填写'), description: t('workflowOrchestration.editor.webhookBodyHint', '本次 Webhook 的业务 JSON，捕获后作为流程输入') },
    ];
  const curlText = [
    `curl --request POST '${absoluteUrl(endpoint)}'`,
    `  --header 'Authorization: Bearer <API Token>'`,
    `  --header 'Content-Type: application/json'`,
    `  --data '${payloadText}'`,
  ].join(' \\\n');
  const unavailable = entry === 'test' ? !workflowId : !runtimeTrigger;
  const unavailableText = entry === 'test'
    ? t('workflowOrchestration.editor.webhookAvailableAfterSave', '首次保存流程后可监听测试请求')
    : currentVersion > 0
      ? loading ? t('workflowOrchestration.editor.loadingWebhookEntry', '正在获取正式入口') : t('workflowOrchestration.editor.webhookEntryUnavailable', '正式入口暂不可用')
      : t('workflowOrchestration.editor.webhookAvailableAfterPublish', '发布流程后自动生成正式触发器');
  const testInstruction = workflowId
    ? t('workflowOrchestration.editor.webhookTestInstruction', '点击“监听测试请求”，然后向临时入口发送一次真实请求。')
    : unavailableText;

  const copy = async (value: string, success: string) => {
    await navigator.clipboard.writeText(value);
    message.success(success);
  };

  return (
    <section className="rounded-lg border border-[var(--color-border-1)] bg-[var(--color-fill-1)] p-4" aria-label={t('workflowOrchestration.editor.webhookEndpoint', 'Webhook 接口')}>
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-[var(--color-text-1)]">{t('workflowOrchestration.editor.webhookEndpoint', 'Webhook 接口')}</div>
          <div className="mt-0.5 text-xs text-[var(--color-text-3)]">{t('workflowOrchestration.editor.webhookEndpointHint', '路径和身份由平台管理，请求正文作为流程输入')}</div>
        </div>
        <Segmented<'test' | 'production'>
          size="small"
          value={entry}
          options={[
            { label: t('common.test', '测试'), value: 'test' },
            { label: t('workflowOrchestration.form.productionEntry', '正式入口'), value: 'production' },
          ]}
          onChange={setEntry}
        />
      </div>

      <div className="mt-4 flex items-center gap-2">
        <Tag color="blue" className="m-0!">POST</Tag>
        <code className="min-w-0 flex-1 break-all text-xs text-[var(--color-text-2)]">{absoluteUrl(endpoint)}</code>
        <Tooltip title={unavailable ? unavailableText : t('workflowOrchestration.editor.copyWebhookUrl', '复制接口地址')}>
          <span><WorkflowPermission operation="View"><Button
            aria-label={t('workflowOrchestration.editor.copyWebhookUrl', '复制接口地址')}
            disabled={unavailable}
            icon={<CopyOutlined />}
            size="small"
            onClick={() => void copy(absoluteUrl(endpoint), t('workflowOrchestration.editor.webhookUrlCopied', 'Webhook 地址已复制'))}
          /></WorkflowPermission></span>
        </Tooltip>
      </div>

      <div className="mt-4 flex items-center justify-between gap-3">
        <span className="text-xs font-medium text-[var(--color-text-2)]">{t('workflowOrchestration.editor.requestExample', '请求示例')}</span>
        <Space size={4}>
          <WorkflowPermission operation="View"><Button
            aria-label={t('workflowOrchestration.editor.copyJson', '复制 JSON')}
            size="small"
            type="link"
            className="h-auto! p-0! text-xs!"
            icon={<CopyOutlined />}
            onClick={() => void copy(payloadText, t('workflowOrchestration.editor.requestCopied', '请求示例已复制'))}
          >{t('workflowOrchestration.editor.copyJson', '复制 JSON')}</Button></WorkflowPermission>
          <WorkflowPermission operation="View"><Button
            aria-label={t('workflowOrchestration.editor.copyCurl', '复制 curl')}
            size="small"
            type="link"
            className="h-auto! p-0! text-xs!"
            icon={<CopyOutlined />}
            onClick={() => void copy(curlText, t('workflowOrchestration.editor.curlCopied', 'curl 示例已复制'))}
          >{t('workflowOrchestration.editor.copyCurl', '复制 curl')}</Button></WorkflowPermission>
        </Space>
      </div>
      <div className="mt-2 grid gap-1.5 rounded-md border border-[var(--color-border-1)] bg-[var(--color-bg)] px-3 py-2">
        <div className="text-xs font-medium text-[var(--color-text-2)]">{t('workflowOrchestration.editor.parameterNotes', '参数说明')}</div>
        {parameterNotes.map((item) => <div key={item.name} className="grid grid-cols-[minmax(96px,auto)_auto_1fr] items-start gap-2 text-xs leading-5">
          <code className="break-all text-[var(--color-text-1)]">{item.name}</code>
          <Tag color={item.generated ? 'blue' : 'default'} className="m-0! mt-0.5!">{item.owner}</Tag>
          <span className="text-[var(--color-text-3)]">{item.description}</span>
        </div>)}
      </div>
      <pre className="mb-0 mt-2 max-h-52 overflow-auto whitespace-pre-wrap break-all rounded-md bg-[var(--color-bg)] px-3 py-2 text-xs leading-5 text-[var(--color-text-2)]">{payloadText}</pre>

      {entry === 'test' ? (
        <div className="mt-3 flex items-center justify-between gap-3">
          <div className="min-w-0 text-xs text-[var(--color-text-3)]">
            {testSession ? <Space size={6} wrap>
              <Tag color={testBusy ? 'processing' : testError ? 'error' : 'success'} className="m-0!">
                {testBusy ? t('workflowOrchestration.editor.waitingForWebhook', '等待请求') : testError ? t('workflowOrchestration.editor.listenFailed', '监听失败') : t('workflowOrchestration.editor.webhookCaptured', '已捕获请求')}
              </Tag>
              <span>{t('workflowOrchestration.editor.webhookTestExpires', '{seconds} 秒内有效', { seconds: testSession.timeout_seconds })}</span>
            </Space> : testInstruction}
            {testError ? <div className="mt-1 text-[var(--color-error)]">{testError}</div> : null}
          </div>
          {testBusy ? <WorkflowPermission operation="Execute"><Button size="small" danger onClick={onCancelTest}>{t('workflowOrchestration.editor.cancelListening', '取消监听')}</Button></WorkflowPermission> : null}
        </div>
      ) : (
        <div className="mt-3 text-xs text-[var(--color-text-3)]">{unavailable ? unavailableText : t('workflowOrchestration.editor.webhookProductionHint', '请通过 Postman、curl 或外部系统发送 POST 请求；草稿修改不影响正式入口。')}</div>
      )}
    </section>
  );
}
