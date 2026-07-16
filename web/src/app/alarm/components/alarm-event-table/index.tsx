import React, { useState } from 'react';
import { Button } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import CustomTable from '@/components/custom-table';
import AlarmLevelIcon from '@/app/alarm/components/alarm-level-icon';
import ContentFormDrawer from '@/components/content-form-drawer';
import EventLevelTag from '@/components/event-level-tag';
import StructuredDataPreview from '@/components/structured-data-preview';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';

export interface AlarmEventLevelOption {
  color?: string;
  icon?: string;
  label: string;
  value: string;
}

export interface AlarmEventRawData {
  [key: string]: unknown;
}

export interface AlarmEventTableItem {
  id: number | string;
  start_time?: string;
  source_name?: string;
  title?: string;
  resource_type?: string;
  status?: string;
  item?: string;
  value?: number | string;
  level?: string;
  raw_data?: AlarmEventRawData;
}

export interface AlarmEventTableProps {
  dataSource: AlarmEventTableItem[];
  levelOptions: AlarmEventLevelOption[];
  loading?: boolean;
  tableScrollY?: string;
  pagination: {
    current: number;
    pageSize: number;
    total: number;
  };
  onChange: (pagination: { current: number; pageSize: number }) => void;
}

const AlarmEventTable: React.FC<AlarmEventTableProps> = ({
  dataSource,
  levelOptions,
  loading,
  pagination,
  tableScrollY,
  onChange,
}) => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const [rawVisible, setRawVisible] = useState(false);
  const [rawData, setRawData] = useState<AlarmEventRawData>();
  const stateLabelMap = {
    new: t('alarms.new'),
    closed: t('alarms.closed'),
    pending: t('alarms.pending'),
    processing: t('alarms.processing'),
    unassigned: t('alarms.unassigned'),
    auto_close: t('alarms.auto_close'),
    resolved: t('alarms.resolved'),
    shield: t('alarms.shield'),
    received: t('alarms.received'),
    auto_recovery: t('alarms.auto_recovery'),
    firing: t('alarms.processing'),
  };

  const handleShowRaw = (record: AlarmEventTableItem) => {
    setRawData((record.raw_data || record) as AlarmEventRawData);
    setRawVisible(true);
  };

  const columns: ColumnsType<AlarmEventTableItem> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 110 },
    {
      title: t('alarms.level'),
      dataIndex: 'level',
      key: 'level',
      width: 110,
      render: (_: unknown, { level }) => {
        const target = levelOptions.find((item) => item.value === String(level));
        return (
          <EventLevelTag
            color={target?.color}
            label={target?.label || '--'}
            icon={
              <AlarmLevelIcon icon={target?.icon || ''} className="w-4 h-4" />
            }
          />
        );
      },
    },
    {
      title: t('alarmCommon.time'),
      dataIndex: 'start_time',
      key: 'start_time',
      width: 180,
      render: (text?: string) =>
        text ? convertToLocalizedTime(text) : '--',
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
      render: (_: unknown, { status }) => (
        <span>{status ? stateLabelMap[status as keyof typeof stateLabelMap] || '--' : '--'}</span>
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
      render: (_: unknown, record) => (
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
      <ContentFormDrawer
        title={t('alarms.rawData')}
        open={rawVisible}
        width={600}
        onClose={() => setRawVisible(false)}
        maskClosable={false}
        destroyOnClose
        hideFooter
      >
        <StructuredDataPreview value={rawData} maxHeight="calc(100vh - 160px)" />
      </ContentFormDrawer>
    </>
  );
};

export default AlarmEventTable;
