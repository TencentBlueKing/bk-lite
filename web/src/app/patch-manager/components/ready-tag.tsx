'use client';

import React from 'react';
import { Tag, Tooltip } from 'antd';
import { useTranslation } from '@/utils/i18n';

export type ReadyStatus = 'ready' | 'processing' | 'action_required' | 'unavailable';

const READY_COLOR: Record<ReadyStatus, string> = {
  ready: 'success',
  processing: 'default',
  action_required: 'warning',
  unavailable: 'error',
};

function isReadyStatus(value: string | undefined): value is ReadyStatus {
  return value !== undefined && value in READY_COLOR;
}

interface ReadyTagProps {
  status?: ReadyStatus | string;
  reason?: string;
}

export default function ReadyTag({ status, reason }: ReadyTagProps): React.ReactElement {
  const { t } = useTranslation();
  const key = isReadyStatus(status) ? status : 'unavailable';
  const tag = <Tag color={READY_COLOR[key]}>{t(`patchManager.readyStatus.${key}`)}</Tag>;
  return reason ? <Tooltip title={reason}>{tag}</Tooltip> : tag;
}
