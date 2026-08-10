'use client';

import React from 'react';
import { Tag } from 'antd';
import { useTranslation } from '@/utils/i18n';

export type Severity = 'critical' | 'important' | 'moderate' | 'low' | 'unspecified';

const SEV_COLOR: Record<Severity, string> = {
  critical: 'error',
  important: 'warning',
  moderate: 'gold',
  low: 'default',
  unspecified: 'default',
};

function isSeverity(value: string | undefined): value is Severity {
  return value !== undefined && value in SEV_COLOR;
}

interface SeverityTagProps {
  severity?: Severity | string;
}

export default function SeverityTag({ severity }: SeverityTagProps): React.ReactElement {
  const { t } = useTranslation();
  const key = isSeverity(severity) ? severity : 'unspecified';
  return <Tag color={SEV_COLOR[key]}>{t(`patchManager.severityValues.${key}`)}</Tag>;
}
