'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Button, Input, message as antMessage } from 'antd';
import { CheckCircleOutlined, CloseCircleOutlined, ClockCircleOutlined, ExclamationCircleOutlined } from '@ant-design/icons';
import { useChatContentHost, useTranslation } from './host';
import { ApprovalRequest } from './types';

interface ApprovalCardProps {
  request: ApprovalRequest;
  token?: string;
  onDecision: (toolCallId: string, decision: 'approved' | 'rejected') => void;
  readOnly?: boolean;
}

const ApprovalCard: React.FC<ApprovalCardProps> = ({ request, onDecision, readOnly = false }) => {
  const { t } = useTranslation();
  const { submitApproval } = useChatContentHost();
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [remainingSeconds, setRemainingSeconds] = useState(() => {
    const elapsed = (Date.now() - request.received_at) / 1000;
    return Math.max(0, Math.floor(request.timeout_seconds - elapsed));
  });

  useEffect(() => {
    if (request.status !== 'pending' || request.timeout_seconds <= 0 || readOnly) return;
    const timer = setInterval(() => {
      const elapsed = (Date.now() - request.received_at) / 1000;
      const remaining = Math.max(0, Math.floor(request.timeout_seconds - elapsed));
      setRemainingSeconds(remaining);
      if (remaining <= 0) {
        clearInterval(timer);
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [request.received_at, request.timeout_seconds, request.status, readOnly]);

  const handleSubmit = useCallback(async (decision: 'approved' | 'rejected') => {
    if (readOnly || submitting || request.status !== 'pending' || (request.timeout_seconds > 0 && remainingSeconds <= 0)) return;
    setSubmitting(true);
    // 后端 API 要求 'approve' / 'reject'（不带 -d/-ed 后缀）
    const apiDecision = decision === 'approved' ? 'approve' : 'reject';
    try {
      if (!submitApproval) throw new Error('Approval transport unavailable');
      await submitApproval({
        execution_id: request.execution_id, node_id: request.node_id,
        tool_call_id: request.tool_call_id, decision: apiDecision, reason: reason || undefined,
      });
      onDecision(request.tool_call_id, decision);
    } catch {
      antMessage.error(t('chat.approvalSubmitFailed'));
    } finally {
      setSubmitting(false);
    }
  }, [submitApproval, request, reason, onDecision, t, readOnly, submitting, remainingSeconds]);

  const isTimedOut = request.timeout_seconds > 0 && remainingSeconds <= 0 && request.status === 'pending';
  const isPending = request.status === 'pending' && !isTimedOut;

  const formatArgs = (args: Record<string, unknown>) => {
    try {
      return JSON.stringify(args, null, 2);
    } catch {
      return String(args);
    }
  };

  const statusIcon = () => {
    if (request.status === 'approved') return <CheckCircleOutlined className="text-[var(--color-success)]" />;
    if (request.status === 'rejected') return <CloseCircleOutlined className="text-[var(--theme-color-status-error)]" />;
    if (isTimedOut) return <ExclamationCircleOutlined className="text-[var(--color-warning)]" />;
    return <ClockCircleOutlined className="text-[var(--color-primary)]" />;
  };

  const statusText = () => {
    if (request.status === 'approved') return t('chat.approvalApproved');
    if (request.status === 'rejected') return t('chat.approvalRejected');
    if (isTimedOut) return t('chat.approvalTimeout');
    if (request.timeout_seconds <= 0 || readOnly) return t('chat.approvalRequired');
    return `${t('chat.approvalTimeRemaining')}: ${remainingSeconds}s`;
  };

  return (
    <div className="my-2 border border-[var(--color-border-1)] rounded-lg bg-[var(--color-fill-1)] p-3 max-w-md">
      <div className="flex items-center gap-2 mb-2 font-medium text-[var(--color-primary)]">
        <ExclamationCircleOutlined />
        <span>{t('chat.approvalRequired')}</span>
      </div>

      <div className="text-sm mb-1">
        <span className="text-[var(--color-text-2)]">{t('chat.approvalToolName')}: </span>
        <code className="bg-[var(--color-bg)] px-1 rounded text-[var(--color-primary)]">{request.tool_name}</code>
      </div>

      {request.tool_args && Object.keys(request.tool_args).length > 0 && (
        <details className="text-sm mb-2">
          <summary className="text-[var(--color-text-2)] cursor-pointer">{t('chat.approvalToolArgs')}</summary>
          <pre className="bg-[var(--color-bg)] rounded p-2 mt-1 text-xs overflow-auto max-h-32 border">
            {formatArgs(request.tool_args)}
          </pre>
        </details>
      )}

      <div className="flex items-center gap-2 text-sm mb-2">
        {statusIcon()}
        <span>{statusText()}</span>
      </div>

      {isPending && !readOnly && (
        <>
          <Input
            size="small"
            placeholder={t('chat.approvalReasonPlaceholder')}
            value={reason}
            onChange={e => setReason(e.target.value)}
            className="mb-2"
          />
          <div className="flex gap-2">
            <Button
              size="small"
              type="primary"
              icon={<CheckCircleOutlined />}
              loading={submitting}
              onClick={() => handleSubmit('approved')}
            >
              {t('chat.approvalApprove')}
            </Button>
            <Button
              size="small"
              danger
              icon={<CloseCircleOutlined />}
              loading={submitting}
              onClick={() => handleSubmit('rejected')}
            >
              {t('chat.approvalReject')}
            </Button>
          </div>
        </>
      )}
    </div>
  );
};

export default ApprovalCard;
