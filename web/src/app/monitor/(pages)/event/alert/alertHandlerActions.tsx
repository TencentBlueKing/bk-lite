'use client';

import React, { useState } from 'react';
import { Button, Modal, Popconfirm, Select, message } from 'antd';
import Permission from '@/components/permission';
import { useTranslation } from '@/utils/i18n';
import { formatUserName } from '@/utils/userDisplay';
import useMonitorApi from '@/app/monitor/api';
import { TableDataItem, UserItem } from '@/app/monitor/types';
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
  const { patchMonitorAlert, claimMonitorAlert, assignMonitorAlert, getAllUsers } =
    useMonitorApi();
  const [actionLoading, setActionLoading] = useState(false);
  const [assignOpen, setAssignOpen] = useState(false);
  const [orgUsers, setOrgUsers] = useState<UserItem[]>([]);
  const [selectedHandlers, setSelectedHandlers] = useState<Array<string | number>>([]);
  const canClaimOrAssign = canClaimOrAssignAlert(record.status, record.handlers);

  const handleClaim = async () => {
    setActionLoading(true);
    try {
      await claimMonitorAlert(record.id as React.Key);
      message.success(t('monitor.events.successfullyClaimed'));
      onSuccess();
    } finally {
      setActionLoading(false);
    }
  };

  const handleClose = async () => {
    setActionLoading(true);
    try {
      await patchMonitorAlert(record.id as React.Key, { status: 'closed' });
      message.success(t('monitor.events.successfullyClosed'));
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
      await assignMonitorAlert(record.id as React.Key, selectedHandlers);
      message.success(t('monitor.events.successfullyAssigned'));
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
              title={t('monitor.events.claimTitle')}
              description={t('monitor.events.claimContent')}
              okText={t('common.confirm')}
              cancelText={t('common.cancel')}
              okButtonProps={{ loading: actionLoading }}
              onConfirm={handleClaim}
            >
              <Button type="link" className="mr-[10px] p-0">
                {t('monitor.events.claim')}
              </Button>
            </Popconfirm>
            <Button type="link" className="mr-[10px] p-0" onClick={openAssign}>
              {t('monitor.events.assign')}
            </Button>
          </>
        ) : null}
        <Popconfirm
          title={t('monitor.events.closeTitle')}
          description={t('monitor.events.closeContent')}
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
        title={t('monitor.events.assignTitle')}
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
          placeholder={t('monitor.events.assignPlaceholder')}
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
