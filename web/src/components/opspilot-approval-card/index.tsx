'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Button, Input, message as antMessage } from 'antd';
import { CheckCircleOutlined, CloseCircleOutlined, ClockCircleOutlined, ExclamationCircleOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import type { OpsPilotApprovalRequest } from '@/components/opspilot-cards';
import StructuredDataPreview from '@/components/structured-data-preview';

interface ApprovalCardProps {
  request: OpsPilotApprovalRequest;
  token: string;
  onDecision: (toolCallId: string, decision: 'approved' | 'rejected') => void;
}

const ApprovalCard: React.FC<ApprovalCardProps> = ({ request, token, onDecision }) => {
  const { t } = useTranslation();
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [remainingSeconds, setRemainingSeconds] = useState(() => {
    const elapsed = (Date.now() - request.received_at) / 1000;
    return Math.max(0, Math.floor(request.timeout_seconds - elapsed));
  });

  useEffect(() => {
    if (request.status !== 'pending') return;
    const timer = setInterval(() => {
      const elapsed = (Date.now() - request.received_at) / 1000;
      const remaining = Math.max(0, Math.floor(request.timeout_seconds - elapsed));
      setRemainingSeconds(remaining);
      if (remaining <= 0) {
        clearInterval(timer);
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [request.received_at, request.timeout_seconds, request.status]);

  const handleSubmit = useCallback(async (decision: 'approved' | 'rejected') => {
    setSubmitting(true);
    // 后端 API 要求 'approve' / 'reject'（不带 -d/-ed 后缀）
    const apiDecision = decision === 'approved' ? 'approve' : 'reject';
    try {
      const response = await fetch('/api/proxy/opspilot/bot_mgmt/submit_approval/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          execution_id: request.execution_id,
          node_id: request.node_id,
          tool_call_id: request.tool_call_id,
          decision: apiDecision,
          reason: reason || undefined,
        }),
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      onDecision(request.tool_call_id, decision);
    } catch {
      antMessage.error(t('chat.approvalSubmitFailed'));
    } finally {
      setSubmitting(false);
    }
  }, [token, request, reason, onDecision, t]);

  const isTimedOut = remainingSeconds <= 0 && request.status === 'pending';
  const isPending = request.status === 'pending' && !isTimedOut;

  const formatArgs = (args: Record<string, unknown>) => {
    try {
      return JSON.stringify(args, null, 2);
    } catch {
      return String(args);
    }
  };

  const statusIcon = () => {
    if (request.status === 'approved') return <CheckCircleOutlined className="text-green-500" />;
    if (request.status === 'rejected') return <CloseCircleOutlined className="text-red-500" />;
    if (isTimedOut) return <ExclamationCircleOutlined className="text-orange-500" />;
    return <ClockCircleOutlined className="text-blue-500" />;
  };

  const statusText = () => {
    if (request.status === 'approved') return t('chat.approvalApproved');
    if (request.status === 'rejected') return t('chat.approvalRejected');
    if (isTimedOut) return t('chat.approvalTimeout');
    return `${t('chat.approvalTimeRemaining')}: ${remainingSeconds}s`;
  };

  return (
    <div className="my-2 border border-orange-200 rounded-lg bg-orange-50 p-3 max-w-md">
      <div className="flex items-center gap-2 mb-2 font-medium text-orange-700">
        <ExclamationCircleOutlined />
        <span>{t('chat.approvalRequired')}</span>
      </div>

      <div className="text-sm mb-1">
        <span className="text-gray-500">{t('chat.approvalToolName')}: </span>
        <code className="bg-white px-1 rounded text-orange-800">{request.tool_name}</code>
      </div>

      {request.tool_args && Object.keys(request.tool_args).length > 0 && (
        <details className="text-sm mb-2">
          <summary className="text-gray-500 cursor-pointer">{t('chat.approvalToolArgs')}</summary>
          <StructuredDataPreview
            value={formatArgs(request.tool_args)}
            maxHeight="8rem"
            className="mt-1 border border-[var(--color-border)] bg-white !p-2 !text-xs !leading-5 text-(--color-text-1)"
          />
        </details>
      )}

      <div className="flex items-center gap-2 text-sm mb-2">
        {statusIcon()}
        <span>{statusText()}</span>
      </div>

      {isPending && (
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
