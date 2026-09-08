import type { ColumnsType } from 'antd/es/table';

interface MonitorIdentityEvent {
  monitor_id?: string | null;
  cmdb_id?: string | null;
}

export const getMonitorIdentityColumns = <T extends MonitorIdentityEvent>(
  t: (key: string) => string
): ColumnsType<T> => [
    {
      title: t('alarms.monitorId'),
      dataIndex: 'monitor_id',
      key: 'monitor_id',
      width: 160,
      render: (text?: string | null) => text || '--',
    },
    {
      title: t('alarms.cmdbId'),
      dataIndex: 'cmdb_id',
      key: 'cmdb_id',
      width: 160,
      render: (text?: string | null) => text || '--',
    },
  ];
