import React, { useState } from 'react';
import OperateModal from '@/components/operate-modal';
import { Select, message } from 'antd';
import { useCommon } from '@/app/alarm/context/common';
import { UserItem } from '@/app/alarm/types/types';
import { useTranslation } from '@/utils/i18n';
import { ActionType } from '@/app/alarm/types/alarms';
import { useAlarmApi } from '@/app/alarm/api/alarms';

interface AlarmAssignModalProps {
  actionType?: ActionType;
  visible: boolean;
  alertIds?: (number | string)[];
  onCancel: () => void;
  onSuccess: (selectedUserIds: (number | string)[]) => void;
}

const AlarmAssignModal: React.FC<AlarmAssignModalProps> = ({
  visible,
  actionType,
  alertIds,
  onCancel,
  onSuccess,
}) => {
  const common = useCommon();
  const userList: UserItem[] = common?.userList || [];
  const [selectedIds, setSelectedIds] = useState<(number | string)[]>([]);
  const { t } = useTranslation();
  const { alertActionOperate } = useAlarmApi();
  const [confirmLoading, setConfirmLoading] = useState(false);

  const options = userList.map((u: UserItem) => ({
    label: `${u.display_name} (${u.username})`,
    value: u.username,
  }));

  const handleOk = async () => {
    if (!selectedIds.length || !actionType) {
      return;
    }
    setConfirmLoading(true);
    try {
      const data = await alertActionOperate(actionType, {
        alert_id: alertIds || [],
        assignee: selectedIds,
      });
      if (Object.values(data).some((res: any) => !res.result)) {
        message.error(
          `${t(`alarms.${actionType}`)}${t(`alarms.alert`)}${t('alarmCommon.partialFailure')}`
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
    <OperateModal
      zIndex={9999}
      title={t(`alarms.${actionType}`) + `${t('alarms.alert')}`}
      open={visible}
      confirmLoading={confirmLoading}
      onOk={handleOk}
      onCancel={() => {
        setSelectedIds([]);
        onCancel();
      }}
    >
      <div className="mt-2 mb-4">
        <label className="block mb-2">
          {t('common.select')}
          {t('alarms.user')}
        </label>
        <Select
          allowClear
          showSearch
          mode="multiple"
          optionFilterProp="label"
          style={{ width: '100%' }}
          placeholder={t('common.selectTip')}
          options={options}
          value={selectedIds}
          filterOption={(input, option) =>
            (option?.label as string)
              ?.toLowerCase()
              .includes(input.toLowerCase())
          }
          onChange={(val) => setSelectedIds(val)}
        />
      </div>
    </OperateModal>
  );
};

export default AlarmAssignModal;
