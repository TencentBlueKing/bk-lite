'use client';

import React, { useState } from 'react';
import { Select, message } from 'antd';
import OperateFormModal from '@/components/operate-form-modal';
import { useTranslation } from '@/utils/i18n';
import {
  type ActionType,
  type AlarmAssigneeOption,
  type AlarmOperateAction,
} from './types';

interface AlarmAssignModalProps {
  actionType?: ActionType;
  visible: boolean;
  alertIds?: (number | string)[];
  assigneeOptions: AlarmAssigneeOption[];
  operateAction: AlarmOperateAction;
  onCancel: () => void;
  onSuccess: (selectedUserIds: (number | string)[]) => void;
}

const AlarmAssignModal: React.FC<AlarmAssignModalProps> = ({
  visible,
  actionType,
  alertIds,
  assigneeOptions,
  operateAction,
  onCancel,
  onSuccess,
}) => {
  const [selectedIds, setSelectedIds] = useState<(number | string)[]>([]);
  const { t } = useTranslation();
  const [confirmLoading, setConfirmLoading] = useState(false);

  const handleOk = async () => {
    if (!selectedIds.length || !actionType) {
      return;
    }
    setConfirmLoading(true);
    try {
      const data = await operateAction(actionType, {
        alert_id: alertIds || [],
        assignee: selectedIds,
      });
      if (Object.values(data).some((res: any) => !res.result)) {
        message.error(
          `${t(`alarms.${actionType}`)}${t('alarms.alert')}${t('alarmCommon.partialFailure')}`
        );
      } else {
        message.success(t(`alarms.${actionType}`) + t('alarmCommon.success'));
        onSuccess(selectedIds);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setConfirmLoading(false);
      setSelectedIds([]);
      onCancel();
    }
  };

  return (
    <OperateFormModal
      zIndex={9999}
      title={t(`alarms.${actionType}`) + `${t('alarms.alert')}`}
      open={visible}
      confirmLoading={confirmLoading}
      onConfirm={handleOk}
      confirmText={t('common.confirm')}
      cancelText={t('common.cancel')}
      onCancel={() => {
        setSelectedIds([]);
        onCancel();
      }}
    >
      <div className="mt-2 mb-4 flex items-center justify-between">
        <label className="mr-2 block">
          {t('common.select')}
          {t('alarms.user')}
        </label>
        <Select
          allowClear
          showSearch
          mode="multiple"
          optionFilterProp="label"
          style={{ width: '100%', flex: 1 }}
          placeholder={t('common.selectTip')}
          options={assigneeOptions}
          value={selectedIds}
          filterOption={(input, option) =>
            (option?.label as string)?.toLowerCase().includes(input.toLowerCase())
          }
          onChange={(val) => setSelectedIds(val)}
        />
      </div>
    </OperateFormModal>
  );
};

export default AlarmAssignModal;
