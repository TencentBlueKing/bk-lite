'use client';

import React, { useState } from 'react';
import { Button, Modal, Popconfirm, Select, Space, message } from 'antd';
import Permission from '@/components/permission';
import { useUserInfoContext } from '@/context/userInfo';
import { useTranslation } from '@/utils/i18n';
import { formatUserName } from '@/utils/userDisplay';
import useMonitorApi from '@/app/monitor/api';
import { TableDataItem, UserItem } from '@/app/monitor/types';
import { canClaimOrAssignAlert, canCloseAlert, canReassignAlert } from './alertHandlerUtils';

interface AlertHandlerActionsProps {
  record: TableDataItem;
  closeText: string;
  requiredPermissions?: string[];
  size?: 'small' | 'middle';
  onSuccess: () => void;
}

const AlertHandlerActions: React.FC<AlertHandlerActionsProps> = ({
  record,
  closeText,
  requiredPermissions = ['Operate'],
  size = 'middle',
  onSuccess
}) => {
  const { t } = useTranslation();
  const { userId, username } = useUserInfoContext();
  const { patchMonitorAlert, claimMonitorAlert, assignMonitorAlert, reassignMonitorAlert, getAllUsers } =
    useMonitorApi();
  const [actionLoading, setActionLoading] = useState(false);
  const [assignOpen, setAssignOpen] = useState(false);
  const [handlerAction, setHandlerAction] = useState<'assign' | 'reassign'>('assign');
  const [orgUsers, setOrgUsers] = useState<UserItem[]>([]);
  const [selectedHandlers, setSelectedHandlers] = useState<Array<string | number>>([]);
  const actor = { id: userId, username };
  const canClaimOrAssign = canClaimOrAssignAlert(record.status, record.handlers);
  const canReassign = canReassignAlert(record.status, record.handlers, actor);
  const canClose = canCloseAlert(record.handlers, actor);

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

  const openHandlerModal = async (action: 'assign' | 'reassign', event?: React.MouseEvent) => {
    event?.stopPropagation();
    const orgs = Array.isArray(record.organizations) ? record.organizations : [];
    const users = await getAllUsers(orgs);
    setOrgUsers(Array.isArray(users) ? users : []);
    setSelectedHandlers([]);
    setHandlerAction(action);
    setAssignOpen(true);
  };

  const handleAssign = async () => {
    if (!selectedHandlers.length) return;
    setActionLoading(true);
    try {
      if (handlerAction === 'reassign') {
        await reassignMonitorAlert(record.id as React.Key, selectedHandlers);
        message.success(t('monitor.events.successfullyReassigned'));
      } else {
        await assignMonitorAlert(record.id as React.Key, selectedHandlers);
        message.success(t('monitor.events.successfullyAssigned'));
      }
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
        <Space size={4}>
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
                <Button type="link" size={size} className="p-0">
                  {t('monitor.events.claim')}
                </Button>
              </Popconfirm>
              <Button type="link" size={size} className="p-0" onClick={(event) => void openHandlerModal('assign', event)}>
                {t('monitor.events.assign')}
              </Button>
            </>
          ) : null}
          {canReassign ? (
            <Button type="link" size={size} className="p-0" onClick={(event) => void openHandlerModal('reassign', event)}>
              {t('monitor.events.reassign')}
            </Button>
          ) : null}
          {canClose ? (
            <Popconfirm
              title={t('monitor.events.closeTitle')}
              description={t('monitor.events.closeContent')}
              okText={t('common.confirm')}
              cancelText={t('common.cancel')}
              okButtonProps={{ loading: actionLoading }}
              onConfirm={handleClose}
            >
              <Button type="link" size={size} className="p-0" disabled={record.status !== 'new'}>
                {closeText}
              </Button>
            </Popconfirm>
          ) : null}
        </Space>
      </Permission>
      <Modal
        title={t(handlerAction === 'reassign' ? 'monitor.events.reassignTitle' : 'monitor.events.assignTitle')}
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
          placeholder={t(
            handlerAction === 'reassign'
              ? 'monitor.events.reassignPlaceholder'
              : 'monitor.events.assignPlaceholder'
          )}
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
