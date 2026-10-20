import React from 'react';
import { Descriptions } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { AlarmTableDataItem } from '@/app/alarm/types/alarms';
import MonitorObjectList from '@/app/alarm/components/monitor-object-list';
import MonitorSourceList from '@/app/alarm/components/monitor-source-list';
import PersonFieldLabel from '@/app/alarm/components/person-field-label';
import NotificationStatusTooltip from './notificationStatusTooltip';

const BaseInfo: React.FC<{ detail: AlarmTableDataItem }> = ({ detail }) => {
  const { t } = useTranslation();
  const hasMonitorObjects = Boolean(detail.monitor_objects?.length);
  const descriptionItems = [
    {
      key: 'source_names',
      label: t('alarmCommon.ruleFields.source_names'),
      value: <MonitorSourceList sources={detail.source_names} showCopy={false} />,
    },
    {
      key: 'push_source_ids',
      label: t('alarmCommon.monitorSource'),
      value: <MonitorSourceList sources={detail.push_source_ids} />,
    },
    {
      key: 'operator',
      label: (
        <PersonFieldLabel
          label={t('alarmCommon.operator')}
          tip={t('alarms.operatorTip')}
        />
      ),
      value: detail.operator_user,
    },
    {
      key: 'owners',
      label: (
        <PersonFieldLabel
          label={t('alarms.owners')}
          tip={t('alarms.ownersTip')}
        />
      ),
      value: Array.isArray(detail.owners) && detail.owners.length ? detail.owners.join('、') : '--',
    },
    {
      key: 'notificationStatus',
      label: t('alarms.notificationStatus'),
      value: (
        <NotificationStatusTooltip
          status={detail.notify_status}
          total={detail.notify_total}
          records={detail.notify_records}
        />
      ),
    },
    ...(hasMonitorObjects ? [] : [{
      key: 'objectType',
      label: t('alarms.objectType'),
      value: detail.resource_type,
    }]),
    {
      key: 'object',
      label: t('alarms.object'),
      value: hasMonitorObjects ? (
        <MonitorObjectList objects={detail.monitor_objects || []} />
      ) : detail.resource_name,
    },
  ];
  return (
    <Descriptions
      bordered
      size="small"
      column={1}
      style={{ tableLayout: 'fixed' }}
      labelStyle={{
        width: '148px',
        whiteSpace: 'nowrap',
      }}
    >
      <Descriptions.Item
        label={t('alarms.content')}
        styles={{
          content: {
            maxHeight: '100px',
            overflowY: 'auto',
            wordBreak: 'break-word',
          },
        }}
      >
        {detail.content || '--'}
      </Descriptions.Item>
      {descriptionItems.map((item) => (
        <Descriptions.Item key={item.key} label={item.label}>
          {item.value || '--'}
        </Descriptions.Item>
      ))}
    </Descriptions>
  );
};

export default BaseInfo;
