'use client';

import React from 'react';
import { Tag } from 'antd';

export type Severity = 'critical' | 'important' | 'moderate' | 'low' | 'unspecified';

const SEV_COLOR: Record<Severity, string> = {
  critical: 'error',
  important: 'warning',
  moderate: 'gold',
  low: 'default',
  unspecified: 'default',
};

const SEV_TEXT: Record<Severity, string> = {
  critical: '严重',
  important: '重要',
  moderate: '中等',
  low: '低',
  unspecified: '未指定',
};

function isSeverity(value: string | undefined): value is Severity {
  return value !== undefined && value in SEV_COLOR;
}

interface SeverityTagProps {
  severity?: Severity | string;
}

export default function SeverityTag({ severity }: SeverityTagProps): React.ReactElement {
  const key = isSeverity(severity) ? severity : 'unspecified';
  return <Tag color={SEV_COLOR[key]}>{SEV_TEXT[key]}</Tag>;
}
