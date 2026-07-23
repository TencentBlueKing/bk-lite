'use client';

import React from 'react';
import { Tag } from 'antd';
import { useTranslation } from '@/utils/i18n';

export type ToolConnectionStatus = 'untested' | 'success' | 'failed';

export interface ToolConnectionStatusTagProps {
  scope:
    | 'tool.mysql'
    | 'tool.redis'
    | 'tool.oracle'
    | 'tool.mssql'
    | 'tool.postgres'
    | 'tool.elasticsearch'
    | 'tool.jenkins'
    | 'tool.kubernetes';
  status: ToolConnectionStatus;
}

const statusColorMap: Record<ToolConnectionStatus, string> = {
  untested: 'default',
  success: 'blue',
  failed: 'red',
};

const ToolConnectionStatusTag: React.FC<ToolConnectionStatusTagProps> = ({
  scope,
  status,
}) => {
  const { t } = useTranslation();

  return (
    <Tag color={statusColorMap[status]}>{t(`${scope}.status.${status}`)}</Tag>
  );
};

export default ToolConnectionStatusTag;
