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
      className="my-2 rounded-md px-3 py-2"
      style={{ background: 'var(--color-fill-1)', fontSize: 13 }}
      role="status"
      aria-live="polite"
    >
      <div className="flex items-center gap-2 text-[var(--color-text-2)]">
        <LoadingOutlined className="text-[var(--color-primary)]" spin />
        <span>{label}</span>
      </div>
    </div>
  );
};

export default PlannedExecutionStatus;
