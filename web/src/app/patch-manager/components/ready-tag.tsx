'use client';

import React from 'react';
import { Tag, Tooltip } from 'antd';

export type ReadyStatus = 'ready' | 'processing' | 'action_required' | 'unavailable';

const READY_MAP: Record<ReadyStatus, { text: string; color: string }> = {
  ready: { text: '就绪', color: 'success' },
  processing: { text: '处理中', color: 'default' },
  action_required: { text: '需处理', color: 'warning' },
  unavailable: { text: '不可用', color: 'error' },
};

function isReadyStatus(value: string | undefined): value is ReadyStatus {
  return value !== undefined && value in READY_MAP;
}

interface ReadyTagProps {
  status?: ReadyStatus | string;
  reason?: string;
}

export default function ReadyTag({ status, reason }: ReadyTagProps): React.ReactElement {
  const key = isReadyStatus(status) ? status : 'unavailable';
  const tag = <Tag color={READY_MAP[key].color}>{READY_MAP[key].text}</Tag>;
  return reason ? <Tooltip title={reason}>{tag}</Tooltip> : tag;
}
