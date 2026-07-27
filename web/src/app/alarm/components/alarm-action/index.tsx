'use client';

import React, { useState } from 'react';
import { Button, Dropdown, Menu, Modal, message } from 'antd';
import { DownOutlined } from '@ant-design/icons';
import PermissionWrapper from '@/components/permission';
import AlarmAssignModal from './assign-modal';
import { useTranslation } from '@/utils/i18n';
import { type ActionType, type AlarmActionProps } from './types';

const AlarmAction: React.FC<AlarmActionProps> = ({
  rowData,
  btnSize = 'middle',
  displayMode = 'inline',
  showAll = false,
  from = 'alarm',
  currentUsername,
  assigneeOptions,
  operateAction,
  onAction,
}) => {
  const idKeyMap = {
    alarm: 'alert_id',
    incident: 'incident_id',
  };
  const { t } = useTranslation();
  const [assignVisible, setAssignVisible] = useState(false);
  const [actionType, setActionType] = useState<ActionType>('assign');
  const idList = rowData
    .map((item) => item[idKeyMap[from]])
    .filter((id): id is string | number => typeof id === 'string' || typeof id === 'number');
  const username = currentUsername;

  const isMine = () =>
    rowData.every((item) =>
      Array.isArray(item?.operator) ? item.operator.includes(username) : false
    );

  const allTypes: ActionType[] = (() => {
    if (from === 'alarm') {
      return ['assign', 'acknowledge', 'reassign', 'close'];
    }
    return ['acknowledge', 'close', 'reopen'];
  })();

  let statusActionMap: Record<string, ActionType[]>;
  if (from === 'alarm') {
    statusActionMap = {
      unassigned: ['assign'],
      pending: ['acknowledge'],
      processing: ['reassign', 'close'],
      closed: [],
      auto_close: [],
    };
  } else {
    statusActionMap = {
      pending: ['acknowledge'],
      processing: ['close'],
      closed: ['reopen'],
      auto_close: [],
    };
  }

  let validStatusMap: Record<string, string[]>;
  if (from === 'alarm') {
    validStatusMap = {
      assign: ['unassigned'],
      acknowledge: ['pending'],
      reassign: ['processing'],
      close: ['processing'],
      auto_close: ['processing'],
    };
  } else {
    validStatusMap = {
      acknowledge: ['pending'],
      close: ['processing'],
      reopen: ['closed'],
    };
  }

  let availableTypes: ActionType[];
  if (showAll) {
    availableTypes = allTypes;
  } else if (rowData[0]?.status) {
    availableTypes = statusActionMap?.[rowData[0].status] || [];
  } else {
    availableTypes = [];
  }

  const handleOperate = (type: ActionType) => {
    if (!['acknowledge', 'close', 'reopen'].includes(type)) {
      setActionType(type);
      setAssignVisible(true);
      return;
    }
    const fromLabel = `${from === 'alarm' ? t('alarms.alert') : t('alarms.incident')}`;
    Modal.confirm({
      title: `${t(`alarms.${type}`)}${fromLabel}`,
      content: `${t('common.confirm')}${t(`alarms.${type}`)}${fromLabel}？`,
      okText: t('confirm'),
      cancelText: t('cancel'),
      centered: true,
      onOk: async () => {
        try {
          const data = await operateAction(type, {
            [idKeyMap[from]]: idList,
            assignee: [],
          });
          if (Object.values(data).some((res: any) => !res.result)) {
            message.error(
              `${t(`alarms.${type}`)}${t('alarms.alert')}${t('alarmCommon.partialFailure')}`
            );
          } else {
            message.success(t(`alarms.${type}`) + t('alarmCommon.success'));
            onAction();
          }
        } catch (err) {
          console.error(err);
        }
      },
    });
  };

  const renderActionButton = (type: ActionType) => {
    const allStatusValid = rowData.every((item) =>
      validStatusMap[type]?.includes(item.status)
    );
    const needMine =
      from === 'alarm' && ['acknowledge', 'reassign'].includes(type);
    const disabled =
      !rowData.length || !allStatusValid || (needMine && !isMine());

    return (
      <PermissionWrapper requiredPermissions={['Edit']} key={type}>
        <Button
          size={btnSize}
          type="link"
          className="mr10"
          disabled={disabled}
          onClick={() => handleOperate(type)}
        >
          {t(`alarms.${type}`)}
        </Button>
      </PermissionWrapper>
    );
  };

  const actionButtons = <>{availableTypes.map(renderActionButton)}</>;

  const menuItems = availableTypes.map((type, idx) => {
    const allStatusValid = rowData.every((item) =>
      validStatusMap[type]?.includes(item.status)
    );
    const needMine =
      from === 'alarm' && ['acknowledge', 'reassign'].includes(type);
    const disabled =
      !rowData.length || !allStatusValid || (needMine && !isMine());

    return {
      key: idx.toString(),
      label: (
        <PermissionWrapper requiredPermissions={['Edit']}>
          <Button
            type="text"
            size="small"
            disabled={disabled}
            onClick={() => handleOperate(type)}
            className="w-full text-left"
          >
            {t(`alarms.${type}`)}
          </Button>
        </PermissionWrapper>
      ),
    };
  });

  const dropdown = menuItems.length ? (
    <PermissionWrapper requiredPermissions={['Edit']}>
      <Dropdown overlay={<Menu items={menuItems} />} trigger={['click']}>
        <Button size={btnSize} type="primary">
          {t('common.actions')}
          <DownOutlined />
        </Button>
      </Dropdown>
    </PermissionWrapper>
  ) : null;

  const inline = <div className="flex items-center gap-2">{actionButtons}</div>;

  return (
    <>
      {displayMode === 'dropdown' && dropdown ? dropdown : inline}
      <AlarmAssignModal
        alertIds={idList}
        assigneeOptions={assigneeOptions}
        visible={assignVisible}
        actionType={actionType}
        operateAction={operateAction}
        onCancel={() => setAssignVisible(false)}
        onSuccess={() => {
          setAssignVisible(false);
          onAction();
        }}
      />
    </>
  );
};

export default AlarmAction;
