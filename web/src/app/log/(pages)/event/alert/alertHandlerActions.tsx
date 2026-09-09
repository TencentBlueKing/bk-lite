'use client';

import React, { useState } from 'react';
import { Button, Modal, Popconfirm, Select, message } from 'antd';
import Permission from '@/components/permission';
import { useTranslation } from '@/utils/i18n';
import { formatUserName } from '@/utils/userDisplay';
import useLogApi from '@/app/log/api';
import useLogEventApi from '@/app/log/api/event';
import { TableDataItem, UserItem } from '@/app/log/types';
import { canClaimOrAssignAlert } from './alertHandlerUtils';

interface AlertHandlerActionsProps {
  record: TableDataItem;
  closeText: string;
  requiredPermissions?: string[];
  onSuccess: () => void;
}

const AlertHandlerActions: React.FC<AlertHandlerActionsProps> = ({
  record,
  closeText,
  requiredPermissions = ['Operate'],
  onSuccess
}) => {
  const { t } = useTranslation();
  const { getAllUsers } = useLogApi();
  const { patchLogAlert, claimLogAlert, assignLogAlert } = useLogEventApi();
  const [actionLoading, setActionLoading] = useState(false);
  const [assignOpen, setAssignOpen] = useState(false);
  const [orgUsers, setOrgUsers] = useState<UserItem[]>([]);
  const [selectedHandlers, setSelectedHandlers] = useState<Array<string | number>>([]);
  const canClaimOrAssign = canClaimOrAssignAlert(record.status, record.handlers);

  const handleClaim = async () => {
    setActionLoading(true);
    try {
      await claimLogAlert(record.id as React.Key);
      message.success(t('log.event.successfullyClaimed'));
      onSuccess();
    } finally {
      setActionLoading(false);
    }
  };

  const handleClose = async () => {
    setActionLoading(true);
    try {
      await patchLogAlert({ id: record.id, status: 'closed' });
      message.success(t('log.event.successfullyClosed'));
      onSuccess();
    } finally {
      setActionLoading(false);
    }
  };

  const openAssign = async (event?: React.MouseEvent) => {
    event?.stopPropagation();
    const orgs = Array.isArray(record.organizations) ? record.organizations : [];
    const users = await getAllUsers(orgs);
    setOrgUsers(Array.isArray(users) ? users : []);
    setSelectedHandlers([]);
    setAssignOpen(true);
  };

  const handleAssign = async () => {
    if (!selectedHandlers.length) return;
    setActionLoading(true);
    try {
      await assignLogAlert(record.id as React.Key, selectedHandlers);
      message.success(t('log.event.successfullyAssigned'));
      setAssignOpen(false);
      onSuccess();
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <>
      <Permission
        requiredPermissions={requiredPermissions}
        instPermissions={record.permission}
      >
        {canClaimOrAssign ? (
          <>
            <Popconfirm
              title={t('log.event.claimTitle')}
              description={t('log.event.claimContent')}
              okText={t('common.confirm')}
              cancelText={t('common.cancel')}
              okButtonProps={{ loading: actionLoading }}
              onConfirm={handleClaim}
            >
              <Button type="link" className="mr-[10px] p-0">
                {t('log.event.claim')}
              </Button>
            </Popconfirm>
            <Button type="link" className="mr-[10px] p-0" onClick={openAssign}>
              {t('log.event.assign')}
            </Button>
          </>
        ) : null}
        <Popconfirm
          title={t('log.event.closeTitle')}
          description={t('log.event.closeContent')}
          okText={t('common.confirm')}
          cancelText={t('common.cancel')}
          okButtonProps={{ loading: actionLoading }}
          onConfirm={handleClose}
        >
          <Button type="link" disabled={record.status !== 'new'}>
            {closeText}
          </Button>
        </Popconfirm>
      </Permission>
      <Modal
        title={t('log.event.assignTitle')}
        open={assignOpen}
        confirmLoading={actionLoading}
        okButtonProps={{ disabled: !selectedHandlers.length }}
        onOk={() => void handleAssign()}
        onCancel={() => setAssignOpen(false)}
      >
        <Select
          className="w-full"
          mode="multiple"
          showSearch
          optionFilterProp="label"
          placeholder={t('log.event.assignPlaceholder')}
          value={selectedHandlers}
          onChange={setSelectedHandlers}
          options={orgUsers.map((item) => ({
            value: item.id,
            label: formatUserName(item)
          }))}
        />
      </Modal>
    </>
  );
};

export default AlertHandlerActions;
