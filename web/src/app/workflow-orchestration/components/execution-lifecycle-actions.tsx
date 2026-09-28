'use client';

import { RedoOutlined, StopOutlined } from '@ant-design/icons';
import { App, Button, Input, Space } from 'antd';
import { useState } from 'react';

import OperateModal from '@/components/operate-modal';
import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';
import type { ExecutionRecord } from '../lib/types';
import { WorkflowPermission } from './workflow-permission';

const API = '/workflow_orchestration/api';
const TERMINAL = new Set(['SUCCEEDED', 'FAILED', 'TIMED_OUT', 'TERMINATED']);

interface ExecutionLifecycleActionsProps {
  execution: ExecutionRecord;
  presentation: 'row' | 'menu';
  onExecutionChanged?: (execution: ExecutionRecord) => void | Promise<void>;
  onRerun?: () => void;
}

export function ExecutionLifecycleActions({ execution, presentation, onExecutionChanged, onRerun }: ExecutionLifecycleActionsProps) {
  const { post } = useApiClient();
  const { message } = App.useApp();
  const { t } = useTranslation();
  const [terminateOpen, setTerminateOpen] = useState(false);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const canTerminate = ['QUEUED', 'RUNNING', 'WAITING_APPROVAL'].includes(execution.status);
  const canRerun = execution.workflow_enabled && !execution.workflow_deleted && execution.mode === 'PRODUCTION' && TERMINAL.has(execution.status) && !execution.parent_execution;

  const terminate = async () => {
    const normalizedReason = reason.trim();
    if (!normalizedReason) return;
    setBusy(true);
    try {
      const updated = await post<ExecutionRecord>(`${API}/executions/${execution.id}/terminate/`, { reason: normalizedReason });
      message.success(t('workflowOrchestration.execution.terminateSubmitted', '已提交终止请求'));
      setTerminateOpen(false);
      setReason('');
      await onExecutionChanged?.(updated);
    } finally {
      setBusy(false);
    }
  };

  if (!canTerminate && !canRerun) return null;

  return (
    <>
      <Space size="small">
        {canRerun ? <WorkflowPermission operation="Execute" area="executions" instancePermissions={execution.permission}><Button type={presentation === 'row' ? 'link' : 'default'} size="small" icon={<RedoOutlined />} onClick={onRerun}>{t('workflowOrchestration.execution.rerun', '重跑')}</Button></WorkflowPermission> : null}
        {canTerminate ? <WorkflowPermission operation="Execute" area="executions" instancePermissions={execution.permission}><Button type={presentation === 'row' ? 'link' : 'default'} size="small" danger icon={<StopOutlined />} onClick={() => setTerminateOpen(true)}>{t('workflowOrchestration.execution.terminate', '终止')}</Button></WorkflowPermission> : null}
      </Space>
      <OperateModal
        title={t('workflowOrchestration.execution.terminateTitle', '终止本次执行')}
        open={terminateOpen}
        okText={t('workflowOrchestration.execution.confirmTerminate', '确认终止')}
        cancelText={t('common.cancel', '取消')}
        okButtonProps={{ danger: true, disabled: !reason.trim(), loading: busy }}
        styles={{ footer: { marginTop: 20 } }}
        onOk={() => void terminate()}
        onCancel={() => { if (!busy) setTerminateOpen(false); }}
      >
        <p className="text-sm text-[var(--color-text-2)]">{t('workflowOrchestration.execution.terminateHint', '后续节点将停止，已发生的外部副作用不会自动回滚。终止原因会写入审计。')}</p>
        <Input.TextArea value={reason} onChange={(event) => setReason(event.target.value)} maxLength={500} showCount rows={3} placeholder={t('workflowOrchestration.execution.terminateReason', '请输入终止原因')} />
      </OperateModal>
    </>
  );
}
