'use client';

import React from 'react';
import { Tag } from 'antd';

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

const REMEDIATION_TEXT: Record<RemediationStatus, string> = {
  unplanned: '待修复',
  scheduled: '已计划',
  remediating: '修复中',
  installing: '安装中',
  rebooting: '重启中',
  verifying: '验证中',
  pending_reboot: '待重启',
  failed: '修复失败',
  fixed: '已修复',
  invalidated: '已失效',
};

function isRemediationStatus(value: string | undefined): value is RemediationStatus {
  return value !== undefined && value in REMEDIATION_COLOR;
}

interface RemediationTagProps {
  status?: RemediationStatus | string;
}

export default function RemediationTag({ status }: RemediationTagProps): React.ReactElement {
  const key = isRemediationStatus(status) ? status : 'unplanned';
  return <Tag color={REMEDIATION_COLOR[key]}>{REMEDIATION_TEXT[key]}</Tag>;
}
