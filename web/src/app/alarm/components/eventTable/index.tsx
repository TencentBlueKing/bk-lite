import React, { useState } from 'react';
import CustomTable from '@/components/custom-table';
import Icon from '@/components/icon';
import { Drawer, Button, Tag } from 'antd';
import { ColumnsType } from 'antd/es/table';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useCommon } from '@/app/alarm/context/common';
import { useStateMap } from '@/app/alarm/constants/alarm';
import { EventTableItem, RawEventData } from '@/app/alarm/types/integration';

interface EventTableProps {
  dataSource: EventTableItem[];
  loading?: boolean;
  tableScrollY?: string;
  pagination: {
    current: number;
    pageSize: number;
    total: number;
  };
  onChange: (pagination: { current: number; pageSize: number }) => void;
}

const EventTable: React.FC<EventTableProps> = ({
  dataSource,
  loading,
  pagination,
  tableScrollY,
  onChange,
}) => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const { levelListEvent, levelMapEvent } = useCommon();
  const [rawVisible, setRawVisible] = useState(false);
  const [rawData, setRawData] = useState<RawEventData>();
  const STATE_MAP = useStateMap();

  const handleShowRaw = (record: EventTableItem) => {
    setRawData((record.raw_data || record) as any);
    setRawVisible(true);
  };

  const columns: ColumnsType<any> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 110 },
    {
      title: t('alarms.level'),
      dataIndex: 'level',
      key: 'level',
      width: 110,
      render: (_: any, { level }) => {
        const target = levelListEvent.find(
          (item) => item.level_id === Number(level)
        );
        return (
          <Tag color={levelMapEvent[level || '']}>
            <div className="flex items-center">
              <Icon type={target?.icon || ''} className="mr-1" />
              {target?.level_display_name || '--'}
            </div>
          </Tag>
        );
      },
    },
    {
      title: t('alarmCommon.time'),
      dataIndex: 'start_time',
      key: 'start_time',
      width: 180,
      render: (text: string) => (text ? convertToLocalizedTime(text) : '--'),
    },
    {
      title: t('alarms.eventTitle'),
      dataIndex: 'title',
      key: 'title',
      width: 230,
    },
    {
      title: t('alarms.object'),
      dataIndex: 'resource_type',
      key: 'resource_type',
      width: 120,
    },
    {
      title: t('alarms.state'),
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (_: any, { status }: EventTableItem) => (
        <span>{STATE_MAP[status as keyof typeof STATE_MAP] || '--'}</span>
      ),
    },
    {
      title: t('alarms.metricName'),
      dataIndex: 'item',
      key: 'item',
      width: 120,
    },
    {
      title: t('alarms.metricValue'),
      dataIndex: 'value',
      key: 'value',
      width: 120,
    },
    {
      title: t('alarms.source'),
      dataIndex: 'source_name',
      key: 'source_name',
      width: 120,
    },
    {
      title: t('alarmCommon.action'),
      key: 'action',
      fixed: 'right',
      width: 100,
      render: (_: any, record: EventTableItem) => (
        <Button type="link" onClick={() => handleShowRaw(record)}>
          {t('alarms.rawData')}
        </Button>
      ),
    },
  ];

  return (
    <>
      <CustomTable
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={dataSource}
        scroll={{ x: 'max-content', y: tableScrollY }}
        pagination={{
          current: pagination.current,
          pageSize: pagination.pageSize,
          total: pagination.total,
        }}
        onChange={(pag) =>
          onChange({
            current: pag.current ?? pagination.current,
            pageSize: pag.pageSize ?? pagination.pageSize,
          })
        }
      />
      <Drawer
        title={t('alarms.rawData')}
        open={rawVisible}
        width={600}
        onClose={() => setRawVisible(false)}
      >
        <pre
          style={{
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            overflow: 'auto',
            maxHeight: 'calc(100vh - 120px)',
            backgroundColor: '#f6f8fa',
            padding: '16px',
            borderRadius: '6px',
            fontSize: '14px',
            lineHeight: '1.5',
          }}
        >
          {JSON.stringify(rawData, null, 2)}
        </pre>
      </Drawer>
    </>
  );
};

export default EventTable;
