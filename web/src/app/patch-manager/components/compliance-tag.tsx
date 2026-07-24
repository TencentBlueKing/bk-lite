'use client';

import React from 'react';
import { Tag } from 'antd';

export type ComplianceStatus =
  | 'compliant'
  | 'non_compliant'
  | 'pending'
  | 'evaluating'
  | 'failed'
  | 'unconfigured';

const COMP_COLOR: Record<ComplianceStatus, string> = {
  compliant: 'success',
  non_compliant: 'error',
  pending: 'default',
  evaluating: 'processing',
  failed: 'warning',
  unconfigured: 'gold',
};

const COMP_TEXT: Record<ComplianceStatus, string> = {
  compliant: '合规',
  non_compliant: '不合规',
  pending: '待评估',
  evaluating: '评估中',
  failed: '评估失败',
  unconfigured: '未配置',
};

function isComplianceStatus(value: string | undefined): value is ComplianceStatus {
  return value !== undefined && value in COMP_COLOR;
}

interface ComplianceTagProps {
  status?: ComplianceStatus | string;
  missing?: number;
}

export default function ComplianceTag({
  status,
  missing,
}: ComplianceTagProps): React.ReactElement {
  const key = isComplianceStatus(status) ? status : 'unconfigured';
  const text =
    key === 'non_compliant' && missing !== undefined
      ? `${COMP_TEXT[key]} · 缺${missing}`
      : COMP_TEXT[key];
  return <Tag color={COMP_COLOR[key]}>{text}</Tag>;
}
