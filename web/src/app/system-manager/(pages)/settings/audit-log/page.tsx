'use client';

import React from 'react';
import { Tabs } from 'antd';
import { useTranslation } from '@/utils/i18n';
import OperationLogs from '@/app/system-manager/components/security/operationLogs';
import UserLoginLogs from '@/app/system-manager/components/security/loginLogs';

const AuditLogPage: React.FC = () => {
  const { t } = useTranslation();

  const items = [
    {
      key: 'operation',
      label: t('system.security.operationLogs'),
      children: <OperationLogs />,
    },
    {
      key: 'login',
      label: t('system.security.loginLogs') || 'Login Logs',
      children: <UserLoginLogs />,
    },
  ];

  return (
    <div className="w-full h-full bg-[var(--color-bg)] p-4 overflow-hidden flex flex-col">
      <Tabs
        className="flex-1 flex flex-col overflow-hidden [&>.ant-tabs-nav]:mb-3 [&>.ant-tabs-content-holder]:flex-1 [&>.ant-tabs-content-holder]:overflow-hidden [&_.ant-tabs-content]:h-full [&_.ant-tabs-tabpane]:h-full [&_.ant-tabs-tabpane]:m-0"
        defaultActiveKey="operation"
        items={items}
        destroyOnHidden
      />
    </div>
  );
};

export default AuditLogPage;
