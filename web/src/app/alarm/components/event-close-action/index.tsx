'use client';

import React from 'react';
import { Button, Popconfirm } from 'antd';
import Permission from '@/components/permission';
import { useTranslation } from '@/utils/i18n';

interface EventCloseActionProps {
  scope: 'monitor.events' | 'log.event';
  label: React.ReactNode;
  disabled?: boolean;
  loading?: boolean;
  onConfirm: () => void | Promise<void>;
  requiredPermissions?: string[];
  instPermissions?: string[];
}

const EventCloseAction = ({
  scope,
  label,
  disabled = false,
  loading = false,
  onConfirm,
  requiredPermissions = ['Operate'],
  instPermissions,
}: EventCloseActionProps) => {
  const { t } = useTranslation();

  return (
    <Permission
      requiredPermissions={requiredPermissions}
      instPermissions={instPermissions}
    >
      <Popconfirm
        title={t(`${scope}.closeTitle`)}
        description={t(`${scope}.closeContent`)}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        okButtonProps={{ loading }}
        onConfirm={() => onConfirm()}
      >
        <Button type="link" disabled={disabled}>
          {label}
        </Button>
      </Popconfirm>
    </Permission>
  );
};

export default EventCloseAction;
