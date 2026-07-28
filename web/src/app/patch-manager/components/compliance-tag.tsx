'use client';

import React from 'react';
import { Tag } from 'antd';
import { useTranslation } from '@/utils/i18n';

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
  const { t } = useTranslation();
  const key = isComplianceStatus(status) ? status : 'unconfigured';
  const statusText = t(`patchManager.complianceStatus.${key}`);
  const text =
    key === 'non_compliant' && missing !== undefined
      ? t('patchManager.complianceStatus.missingCount', '{status} · Missing {count}', { status: statusText, count: missing })
      : statusText;
  return <Tag color={COMP_COLOR[key]}>{text}</Tag>;
}
