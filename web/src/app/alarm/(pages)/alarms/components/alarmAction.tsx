'use client';

import React, { useState } from 'react';
import AlarmAssignModal from './assignModal';
import PermissionWrapper from '@/components/permission';
import { Button, Dropdown, Menu, Modal, Tag, message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { DownOutlined } from '@ant-design/icons';
import { AlarmActionProps, ActionType } from '@/app/alarm/types/alarms';
import { ActionRuleListItem } from '@/app/alarm/types/settings';
import { useAlarmApi } from '@/app/alarm/api/alarms';
import { useIncidentsApi } from '@/app/alarm/api/incidents';
import { useSettingApi } from '@/app/alarm/api/settings';
import { useSession } from 'next-auth/react';

const AlarmAction: React.FC<AlarmActionProps> = ({
  rowData,
  btnSize = 'middle',
  displayMode = 'inline',
  showAll = false,
  from = 'alarm',
  onAction,
}) => {
  const idKeyMap = {
    alarm: 'alert_id',
    incident: 'incident_id',
  };
  const { t } = useTranslation();
  const { data: session } = useSession();
  const { alertActionOperate } = useAlarmApi();
  const { incidentActionOperate } = useIncidentsApi();
  const { getActionRuleList, manualTriggerAction } = useSettingApi();
  const [assignVisible, setAssignVisible] = useState(false);
  const [actionType, setActionType] = useState<ActionType>('assign');
  const [jobRules, setJobRules] = useState<ActionRuleListItem[]>([]);
  const [rulesLoading, setRulesLoading] = useState(false);
  const idList = rowData.map((item) => item[idKeyMap[from]]);
  const username = (session?.user as any)?.username;

  const isMine = () =>
    rowData.every((item) =>
      Array.isArray(item?.operator) ? item.operator.includes(username) : false
    );

  const apiNameMap = {
    alarm: alertActionOperate,
    incident: incidentActionOperate,
  };

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
          const data = await apiNameMap[from](type, {
            [idKeyMap[from]]: idList,
            assignee: [],
          });
          if (Object.values(data).some((res: any) => !res.result)) {
            message.error(
              `${t(`alarms.${type}`)}${t(`alarms.alert`)}${t('alarmCommon.partialFailure')}`
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

  const handleFetchJobRules = async () => {
    if (rulesLoading) return;
    setRulesLoading(true);
    try {
      const res = await getActionRuleList({ action_type: 'job', is_active: true, page: 1, page_size: 100 });
      // request.ts 的 handleResponse 已 unwrap 到 data，本应用分页返回 { items, count }
      setJobRules(Array.isArray(res?.items) ? res.items : Array.isArray(res) ? res : []);
    } catch (err) {
      console.error(err);
      setJobRules([]);
    } finally {
      setRulesLoading(false);
    }
  };

  const handleManualTrigger = async (rule: ActionRuleListItem) => {
    if (!rowData.length) return;
    const alertId = rowData[0][idKeyMap[from]];
    try {
      await manualTriggerAction({ alert_id: alertId, rule_id: rule.id });
      message.success(t('common.operationSuccess') || '已触发');
      onAction();
    } catch (err) {
      console.error(err);
    }
  };

  const jobRuleMenuItems = rulesLoading
    ? [{ key: '__loading__', label: <span>{t('common.loading') || '加载中...'}</span>, disabled: true }]
    : jobRules.length === 0
      ? [{ key: '__empty__', label: <span>{t('settings.noAvailableRules', '暂无可用规则')}</span>, disabled: true }]
      : jobRules.map((rule) => {
        // 三态展示主机来源：fixed 醒目蓝、from_alert 浅灰、mode 缺省（老规则）按 from_alert 语义显示
        const rawMode = rule.action_config?.target_binding?.mode;
        let hostTagText: string;
        let hostTagColor: string;
        if (rawMode === 'fixed') {
          hostTagText = t('settings.actionTargetHostModeFixed');
          hostTagColor = 'blue';
        } else if (rawMode === 'from_alert') {
          hostTagText = t('settings.actionTargetHostModeFromAlert');
          hostTagColor = 'default';
        } else {
          hostTagText = t('settings.actionTargetHostModeLegacy');
          hostTagColor = 'default';
        }
        return {
          key: String(rule.id),
          label: (
            <span
              className="inline-flex items-center gap-2"
              onClick={() => handleManualTrigger(rule)}
            >
              <span>{rule.name}</span>
              <Tag color={hostTagColor}>{hostTagText}</Tag>
            </span>
          ),
        };
      });

  const manualTriggerDropdown = from === 'alarm' ? (
    <PermissionWrapper requiredPermissions={['Edit']}>
      <Dropdown
        overlay={<Menu items={jobRuleMenuItems} />}
        trigger={['click']}
        onOpenChange={(open) => { if (open) handleFetchJobRules(); }}
      >
        <Button size={btnSize} type="link" className="mr10">
          {t('settings.actionManualTrigger')}
          <DownOutlined />
        </Button>
      </Dropdown>
    </PermissionWrapper>
  ) : null;

  const actionButtons = (
    <>
      {availableTypes.map(renderActionButton)}
      {manualTriggerDropdown}
    </>
  );

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

  const inline = <div className="gap-2 flex items-center">{actionButtons}</div>;

  const dropdownWithManual = (
    <div className="gap-2 flex items-center">
      {dropdown}
      {manualTriggerDropdown}
    </div>
  );

  return (
    <>
      {displayMode === 'dropdown' ? dropdownWithManual : inline}
      <AlarmAssignModal
        alertIds={idList}
        visible={assignVisible}
        actionType={actionType}
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
