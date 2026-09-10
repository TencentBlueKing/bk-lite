'use client';

import React from 'react';
import { LoadingOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import type { PlannedExecutionStatusValue } from '@/app/opspilot/types/chat';

interface PlannedExecutionStatusProps {
  status: PlannedExecutionStatusValue;
}

export const isActivePlannedExecutionStatus = (phase?: string) =>
  phase === 'planning' || phase === 'replanning';

const PlannedExecutionStatus: React.FC<PlannedExecutionStatusProps> = ({ status }) => {
  const { t } = useTranslation();

  if (!isActivePlannedExecutionStatus(status.phase)) {
    return null;
  }

  const label =
    status.phase === 'replanning'
      ? t('chat.replanningExecution') || '正在根据执行结果重新规划…'
      : t('chat.planningExecution') || '正在分析任务并规划执行步骤…';

  return (
    <div
      className="my-1.5 flex items-center gap-1.5 py-0.5 text-xs text-[var(--color-text-3)]"
      role="status"
      aria-live="polite"
    >
      <LoadingOutlined className="text-[var(--color-primary)] text-xs" spin />
      <span>{label}</span>
    </div>
  );
};

export default PlannedExecutionStatus;
