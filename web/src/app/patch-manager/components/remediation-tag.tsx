'use client';

import React from 'react';
import { Tag } from 'antd';
import { useTranslation } from '@/utils/i18n';

export type RemediationStatus =
  | 'unplanned'
  | 'scheduled'
  | 'remediating'
  | 'installing'
  | 'rebooting'
  | 'verifying'
  | 'pending_reboot'
  | 'failed'
  | 'fixed'
  | 'invalidated';

const REMEDIATION_COLOR: Record<RemediationStatus, string> = {
  unplanned: 'warning',
  scheduled: 'processing',
  remediating: 'purple',
  installing: 'processing',
  rebooting: 'processing',
  verifying: 'processing',
  pending_reboot: 'default',
  failed: 'error',
  fixed: 'success',
  invalidated: 'default',
};

function isRemediationStatus(value: string | undefined): value is RemediationStatus {
  return value !== undefined && value in REMEDIATION_COLOR;
}

interface RemediationTagProps {
  status?: RemediationStatus | string;
}

export default function RemediationTag({ status }: RemediationTagProps): React.ReactElement {
  const { t } = useTranslation();
  const key = isRemediationStatus(status) ? status : 'unplanned';
  return <Tag color={REMEDIATION_COLOR[key]}>{t(`patchManager.remediationStatus.${key}`)}</Tag>;
}
