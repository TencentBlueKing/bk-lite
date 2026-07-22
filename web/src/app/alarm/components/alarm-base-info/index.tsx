'use client';

import React from 'react';
import DetailListPanel from '@/components/detail-list-panel';
import { useTranslation } from '@/utils/i18n';

export interface AlarmBaseInfoDetail {
  content?: string | null;
  operator_user?: string | null;
  source_names?: string | null;
  notification_status?: string | null;
  notify_status?: string | null;
  resource_type?: string | null;
  resource_name?: string | null;
}

export interface AlarmBaseInfoProps {
  detail: AlarmBaseInfoDetail;
}

const PLACEHOLDER = '--';

const AlarmBaseInfo: React.FC<AlarmBaseInfoProps> = ({ detail }) => {
  const { t } = useTranslation();
  const notifiedStateLabelMap = {
    not_notified: t('alarmCommon.notNotified'),
    success: t('alarmCommon.success'),
    failed: t('alarmCommon.failed'),
    partial_success: t('alarmCommon.partialSuccess'),
  };
  const notificationStatus =
    detail.notification_status || detail.notify_status || '';

  const descriptionItems = [
    {
      key: 'content',
      label: t('alarms.content'),
      displayValue: (
        <div className="max-h-[100px] overflow-y-auto break-words">
          {detail.content || PLACEHOLDER}
        </div>
      ),
      copyable: false,
    },
    {
      key: 'operator',
      label: t('alarmCommon.operator'),
      value: detail.operator_user,
      copyable: false,
    },
    {
      key: 'source',
      label: t('alarms.source'),
      value: detail.source_names,
      copyable: false,
    },
    {
      key: 'notificationStatus',
      label: t('alarms.notificationStatus'),
      value:
        notifiedStateLabelMap[
          notificationStatus as keyof typeof notifiedStateLabelMap
        ] || PLACEHOLDER,
      copyable: false,
    },
    {
      key: 'objectType',
      label: t('alarms.objectType'),
      value: detail.resource_type,
      copyable: false,
    },
    {
      key: 'object',
      label: t('alarms.object'),
      value: detail.resource_name,
      copyable: false,
    },
  ];

  return (
    <DetailListPanel
      labelWidthClassName="w-32"
      placeholder={PLACEHOLDER}
      items={descriptionItems}
    />
  );
};

export default AlarmBaseInfo;
