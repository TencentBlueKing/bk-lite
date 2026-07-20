import React from 'react';
import { Tag, Tooltip } from 'antd';
import type { NotifyRecord } from '@/app/alarm/types/alarms';
import { useNotifiedStateMap } from '@/app/alarm/constants/alarm';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useTranslation } from '@/utils/i18n';

interface NotificationStatusTooltipProps {
  status?: string;
  total?: number;
  records?: NotifyRecord[];
}

const STATUS_COLOR_MAP: Record<string, string> = {
  success: 'success',
  failed: 'error',
  partial_success: 'warning',
};

const NotificationStatusTooltip: React.FC<NotificationStatusTooltipProps> = ({
  status = '',
  total = 0,
  records = [],
}) => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const notifiedState = useNotifiedStateMap();
  const statusKey = status || 'not_notified';
  const visibleRecords = records.slice(0, 5);
  const summary = t('alarms.notificationSummary')
    .replace('{{total}}', String(total))
    .replace('{{shown}}', String(visibleRecords.length));

  const tooltipContent = (
    <div className="w-[400px] max-h-[320px] overflow-y-auto pr-1 text-xs">
      <div className="mb-2 font-medium text-sm">
        {summary}
      </div>
      {visibleRecords.length === 0 ? (
        <div className="py-3 text-center text-gray-400">
          {t('alarms.noNotificationRecords')}
        </div>
      ) : (
        visibleRecords.map((record, index) => {
          const recipients = record.recipients
            .map((recipient) => recipient.display_name || recipient.username)
            .join(', ');
          const recordStatus = notifiedState[record.result] || record.result;
          return (
            <div
              key={`${record.notify_time}-${record.channel}-${index}`}
              className="border-t border-white/20 py-2 first:border-t-0 first:pt-0"
            >
              <div>{t('alarms.notificationTime')}: {convertToLocalizedTime(record.notify_time)}</div>
              <div>{t('alarms.notificationChannel')}: {record.channel_name || record.channel || '--'}</div>
              <div>{t('alarms.notificationRecipients')}: {recipients || '--'}</div>
              <div>
                {t('alarms.notificationResult')}: <span className={record.result === 'failed' ? 'text-red-300' : 'text-green-300'}>{recordStatus}</span>
              </div>
              {record.result === 'failed' ? (
                <div className="break-words text-red-200">
                  {t('alarms.notificationFailureReason')}: {record.failure_reason || t('alarms.notificationReasonUnavailable')}
                </div>
              ) : null}
            </div>
          );
        })
      )}
    </div>
  );

  return (
    <Tooltip
      title={tooltipContent}
      placement="topLeft"
      trigger={['hover', 'focus']}
      overlayStyle={{ maxWidth: 440 }}
    >
      <Tag tabIndex={0} color={STATUS_COLOR_MAP[statusKey] || 'default'}>
        {notifiedState[statusKey] || '--'}
      </Tag>
    </Tooltip>
  );
};

export default NotificationStatusTooltip;
