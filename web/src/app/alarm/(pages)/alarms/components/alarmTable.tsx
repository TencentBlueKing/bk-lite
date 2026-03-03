'use client';

import React, { useRef } from 'react';
import CustomTable from '@/components/custom-table';
import AlarmAction from './alarmAction';
import AlertDetail from './alarmDetail';
import Icon from '@/components/icon';
import UserAvatar from '@/components/user-avatar';
import type { ColumnsType } from 'antd/es/table';
import { Tag, Button } from 'antd';
import { AlarmTableProps } from '@/app/alarm/types/alarms';
import { TableDataItem } from '@/app/alarm/types/types';
import { AlarmTableDataItem } from '@/app/alarm/types/alarms';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { ModalRef } from '@/app/alarm/types/types';
import { useStateMap, useNotifiedStateMap } from '@/app/alarm/constants/alarm';
import { useCommon } from '@/app/alarm/context/common';

const AlarmTable: React.FC<AlarmTableProps> = ({
  dataSource,
  pagination,
  loading,
  tableScrollY,
  selectedRowKeys,
  onChange,
  onRefresh,
  onSelectionChange,
  extraActions,
}) => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const { levelList, levelMap } = useCommon();
  const STATE_MAP = useStateMap();
  const NOTIFIED_STATE: any = useNotifiedStateMap();
  const detailRef = useRef<ModalRef>(null);

  const columns: ColumnsType<AlarmTableDataItem> = [
    {
      title: t('alarms.level'),
      dataIndex: 'level',
      key: 'level',
      width: 90,
      fixed: 'left',
      render: (_: any, { level }: AlarmTableDataItem) => {
        const target = levelList.find(
          (item) => item.level_id === Number(level)
        );
        return (
          <Tag color={levelMap[level || '']}>
            <div className="flex items-center">
              <Icon type={target?.icon || ''} className="mr-1" />
              {target?.level_display_name || '--'}
            </div>
          </Tag>
        );
      },
    },
    {
      title: t('alarms.firstEventTime'),
      dataIndex: 'first_event_time',
      key: 'first_event_time',
      width: 180,
      render: (_: any, { first_event_time }: AlarmTableDataItem) =>
        first_event_time ? convertToLocalizedTime(first_event_time) : '--',
    },
    {
      title: t('alarms.lastEventTime'),
      dataIndex: 'last_event_time',
      key: 'last_event_time',
      width: 180,
      render: (_: any, { last_event_time }: AlarmTableDataItem) =>
        last_event_time ? convertToLocalizedTime(last_event_time) : '--',
    },
    {
      title: t('alarms.alertName'),
      dataIndex: 'title',
      key: 'title',
      width: 280,
    },
    {
      title: t('alarms.incidentName'),
      dataIndex: 'incident_name',
      key: 'incident_name',
      width: 250,
    },
    {
      title: t('alarms.eventCount'),
      dataIndex: 'event_count',
      key: 'event_count',
      width: 100,
      render: (_: any, record: AlarmTableDataItem) => (
        <Button type="link" onClick={() => onOpenDetail(record, 'event')}>
          <span className="text-blue-500">{record.event_count}</span>
        </Button>
      ),
    },
    // {
    //   title: t('alarms.source'),
    //   dataIndex: 'source_names',
    //   key: 'source_names',
    //   width: 130,
    // },
    {
      title: t('alarms.state'),
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (_: any, { status }: AlarmTableDataItem) => (
        <span>{STATE_MAP[status as keyof typeof STATE_MAP] || '--'}</span>
      ),
    },
    {
      title: t('alarms.duration'),
      dataIndex: 'duration',
      key: 'duration',
      width: 170,
    },
    {
      title: t('alarmCommon.operator'),
      dataIndex: 'operator_user',
      key: 'operator_user',
      width: 200,
      shouldCellUpdate: (prev: AlarmTableDataItem, next: AlarmTableDataItem) =>
        prev?.operator_user !== next?.operator_user,
      render: (_: any, { operator_user }: AlarmTableDataItem) =>
        operator_user ? <UserAvatar userName={operator_user} /> : '--',
    },
    {
      title: t('alarms.notificationStatus'),
      dataIndex: 'notify_status',
      key: 'notify_status',
      width: 150,
      render: (_: any, { notify_status }: AlarmTableDataItem) => {
        const COLOR_MAP: Record<string, string> = {
          success: 'success',
          failed: 'error',
          partial_success: 'warning',
        };
        const key = notify_status ? notify_status : 'not_notified';
        const color = COLOR_MAP[key] || 'default';
        const text = NOTIFIED_STATE[key] || '--';
        return <Tag color={color}>{text}</Tag>;
      },
    },
    // {
    //   title: t('alarms.ruleId'),
    //   dataIndex: 'rule_id',
    //   key: 'rule_id',
    //   width: 250,
    // },
    {
      title: t('alarms.alertContent'),
      dataIndex: 'content',
      key: 'content',
      width: 250,
    },
    {
      title: t('alarmCommon.action'),
      key: 'action',
      fixed: 'right',
      width: 220,
      render: (_: any, record: AlarmTableDataItem) => (
        <div className="flex items-center">
          <Button
            className="mr-[12px]"
            type="link"
            onClick={() => onOpenDetail(record)}
          >
            {t('common.detail')}
          </Button>
          {extraActions && extraActions(record)}
          <AlarmAction rowData={[record]} onAction={onRefresh} />
        </div>
      ),
    },
  ];

  const onOpenDetail = (
    row: AlarmTableDataItem,
    defaultTab: string = 'baseInfo'
  ) => {
    detailRef.current?.showModal({
      title: row.title,
      form: row,
      type: '',
      defaultTab,
    });
  };

  return (
    <>
      <CustomTable
        scroll={{ y: tableScrollY, x: 'calc(100vw - 320px)' }}
        columns={columns as ColumnsType<TableDataItem>}
        dataSource={dataSource}
        pagination={pagination}
        loading={loading}
        rowKey="id"
        onChange={onChange}
        rowSelection={{ selectedRowKeys, onChange: onSelectionChange }}
      />
      <AlertDetail ref={detailRef} handleAction={onRefresh} />
    </>
  );
};

export default AlarmTable;
