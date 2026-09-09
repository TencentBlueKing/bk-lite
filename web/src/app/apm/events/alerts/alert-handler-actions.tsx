'use client';

import { useState, type MouseEvent } from 'react';
import { Button, Modal, Popconfirm, Select, Space, message } from 'antd';
import useApmApi from '@/app/apm/api';
import type { ApmAlert, ApmNotificationRecipient } from '@/app/apm/types';
import { formatUserName } from '@/utils/userDisplay';
import { useTranslation } from '@/utils/i18n';
import { canClaimOrAssignAlert } from './alertHandlerUtils';

interface AlertHandlerActionsProps {
  alert: ApmAlert;
  closeText: string;
  closeDanger?: boolean;
  size?: 'small' | 'middle';
  onSuccess: () => void;
}

export default function AlertHandlerActions({
  alert,
  closeText,
  closeDanger = false,
  size = 'small',
  onSuccess,
}: AlertHandlerActionsProps) {
  const { t } = useTranslation();
  const { closeAlert, claimAlert, assignAlert, getNotificationRecipients } = useApmApi();
  const [actionLoading, setActionLoading] = useState(false);
  const [assignOpen, setAssignOpen] = useState(false);
  const [orgUsers, setOrgUsers] = useState<ApmNotificationRecipient[]>([]);
  const [selectedHandlers, setSelectedHandlers] = useState<Array<string | number>>([]);
  const canClaimOrAssign = canClaimOrAssignAlert(alert.status, alert.handlers);

  const handleClaim = async () => {
    setActionLoading(true);
    try {
      await claimAlert(alert.id);
      message.success(t('apm.alerts.successfullyClaimed', '认领成功'));
      onSuccess();
    } finally {
      setActionLoading(false);
    }
  };

  const handleClose = async () => {
    setActionLoading(true);
    try {
      await closeAlert(alert.id);
      message.success(t('apm.alerts.closed', '告警已关闭'));
      onSuccess();
    } finally {
      setActionLoading(false);
    }
  };

  const openAssign = async (event?: MouseEvent) => {
    event?.stopPropagation();
    const organizationIds = (alert.organizations || []).join(',');
    const users = organizationIds
      ? await getNotificationRecipients({ organization_ids: organizationIds, limit: 100 })
      : [];
    setOrgUsers(Array.isArray(users) ? users : []);
    setSelectedHandlers([]);
    setAssignOpen(true);
  };

  const handleAssign = async () => {
    if (!selectedHandlers.length) return;
    setActionLoading(true);
    try {
      await assignAlert(alert.id, selectedHandlers);
      message.success(t('apm.alerts.successfullyAssigned', '分派成功'));
      setAssignOpen(false);
      onSuccess();
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <>
      <Space size={4}>
        {canClaimOrAssign ? (
          <>
            <Popconfirm
              title={t('apm.alerts.claimTitle', '确认认领该告警？')}
              description={t('apm.alerts.claimContent', '认领后你将成为该告警的处理人。')}
              okText={t('apm.alerts.confirmAction', '确定')}
              cancelText={t('common.cancel', '取消')}
              okButtonProps={{ loading: actionLoading }}
              onConfirm={handleClaim}
            >
              <Button type="link" size={size} className="p-0" onClick={(event) => event.stopPropagation()}>
                {t('apm.alerts.claim', '认领')}
              </Button>
            </Popconfirm>
            <Button type="link" size={size} className="p-0" onClick={openAssign}>
              {t('apm.alerts.assign', '分派')}
            </Button>
          </>
        ) : null}
        <Popconfirm
          title={t('apm.alerts.closeConfirm', '确定关闭此告警？')}
          description={t('apm.alerts.closeConfirmDescription', '关闭后会追加人工关闭事件，确认继续？')}
          okText={t('apm.alerts.confirmAction', '确定')}
          cancelText={t('common.cancel', '取消')}
          disabled={alert.status !== 'active'}
          okButtonProps={{ loading: actionLoading }}
          onConfirm={handleClose}
        >
          <Button
            type={closeDanger ? 'primary' : 'link'}
            danger
            size={size}
            disabled={alert.status !== 'active'}
            onClick={(event) => event.stopPropagation()}
          >
            {closeText}
          </Button>
        </Popconfirm>
      </Space>
      <Modal
        title={t('apm.alerts.assignTitle', '分派处理人')}
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
          placeholder={t('apm.alerts.assignPlaceholder', '从告警所属组织选择处理人')}
          value={selectedHandlers}
          onChange={setSelectedHandlers}
          options={orgUsers.map((item) => ({
            value: item.id,
            label: formatUserName(item),
          }))}
        />
      </Modal>
    </>
  );
}
