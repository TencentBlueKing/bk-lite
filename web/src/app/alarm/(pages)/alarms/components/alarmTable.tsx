'use client';

import React, { useRef, useState } from 'react';
import CustomTable from '@/components/custom-table';
import AlarmAction from './alarmAction';
import AlertDetail from './alarmDetail';
import LevelIcon from '@/app/alarm/components/levelIcon';
import OperatorWithOrgCell from '@/app/alarm/components/operator-with-org-cell';
import type { ColumnsType } from 'antd/es/table';
import { Tag, Button } from 'antd';
import { AlarmTableProps } from '@/app/alarm/types/alarms';
import { TableDataItem } from '@/app/alarm/types/types';
import { AlarmTableDataItem } from '@/app/alarm/types/alarms';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { ModalRef } from '@/app/alarm/types/types';
import { useStateMap } from '@/app/alarm/constants/alarm';
import { useCommon } from '@/app/alarm/context/common';
import NotificationStatusTooltip from './notificationStatusTooltip';
import type { ColumnItem } from '@/types/index';
import {
  ALARM_TABLE_ACTION_COLUMN_KEY,
  getAlarmTableChoosableColumns,
  readAlarmDisplayFieldKeys,
  resolveAlarmTableColumns,
  saveAlarmDisplayFieldKeys,
} from '@/app/alarm/utils/alarmTableColumns';

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
  readonly = false,
}) => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const { levelList, levelMap } = useCommon();
  const STATE_MAP = useStateMap();
  const detailRef = useRef<ModalRef>(null);
  const [displayFieldKeys, setDisplayFieldKeys] = useState<string[] | null>(
    () => (typeof window === 'undefined' ? null : readAlarmDisplayFieldKeys(window.localStorage))
  );

  const columns: ColumnsType<AlarmTableDataItem> = [
    {
      title: t('alarms.level'),
      dataIndex: 'level',
      key: 'level',
      width: 90,
      fixed: 'left',
      render: (_: any, { level }: AlarmTableDataItem) => {
        const target = levelList.find(
          (item) => item.level_id === Number(level),
        );
        return (
          <Tag color={levelMap[level || '']}>
            <div className="flex items-center">
              <LevelIcon icon={target?.icon || ''} className="mr-1 w-4 h-4" />
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
      title: t('alarms.closeTime'),
      dataIndex: 'closed_at',
      key: 'closed_at',
      width: 180,
      render: (_: any, { closed_at }: AlarmTableDataItem) =>
        closed_at ? convertToLocalizedTime(closed_at) : '--',
    },
    {
      title: t('alarms.alertName'),
      dataIndex: 'title',
      key: 'title',
      width: 280,
    },
    {
      title: t('alarms.alertContent'),
      dataIndex: 'content',
      key: 'content',
      width: 250,
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
      width: 240,
      shouldCellUpdate: (prev: AlarmTableDataItem, next: AlarmTableDataItem) =>
        prev?.operator_user !== next?.operator_user ||
        JSON.stringify(prev?.team) !== JSON.stringify(next?.team),
      render: (_: any, { operator_user, team }: AlarmTableDataItem) => (
        <OperatorWithOrgCell operatorUser={operator_user} team={team} />
      ),
    },
    {
      title: t('alarms.notificationStatus'),
      dataIndex: 'notify_status',
      key: 'notify_status',
      width: 150,
      render: (_: any, { notify_status, notify_total, notify_records }: AlarmTableDataItem) => (
        <NotificationStatusTooltip
          status={notify_status}
          total={notify_total}
          records={notify_records}
        />
      ),
    },
    // {
    //   title: t('alarms.ruleId'),
    //   dataIndex: 'rule_id',
    //   key: 'rule_id',
    //   width: 250,
    // },
    {
      title: t('alarms.createTime'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (_: any, { created_at }: AlarmTableDataItem) =>
        created_at ? convertToLocalizedTime(created_at) : '--',
    },
    {
      title: t('alarmCommon.action'),
      key: ALARM_TABLE_ACTION_COLUMN_KEY,
      fixed: 'right',
      width: readonly ? 110 : 220,
      render: (_: any, record: AlarmTableDataItem) => (
        <div className="flex items-center">
          <Button
            className={!readonly ? 'mr-[12px]' : ''}
            type="link"
            onClick={() => onOpenDetail(record)}
          >
            {t('common.detail')}
          </Button>
          {!readonly && extraActions && extraActions(record)}
          {!readonly && <AlarmAction rowData={[record]} onAction={onRefresh} />}
        </div>
      ),
    },
  ];

  const onOpenDetail = (
    row: AlarmTableDataItem,
    defaultTab: string = 'baseInfo',
  ) => {
    detailRef.current?.showModal({
      title: row.title,
      form: row,
      type: '',
      defaultTab,
    });
  };

  const choosableFields = getAlarmTableChoosableColumns(columns) as ColumnItem[];
  const resolvedDisplayFieldKeys =
    displayFieldKeys ?? choosableFields.map((column) => String(column.key));
  const currentColumns = resolveAlarmTableColumns(columns, displayFieldKeys);

  const onSelectFields = (fields: string[]) => {
    setDisplayFieldKeys(fields);
    saveAlarmDisplayFieldKeys(fields, window.localStorage);
  };

  return (
    <>
      <CustomTable
        scroll={{ y: tableScrollY, x: 'calc(100vw - 320px)' }}
        columns={currentColumns as ColumnsType<TableDataItem>}
        dataSource={dataSource}
        pagination={pagination}
        loading={loading}
        rowKey="id"
        onChange={onChange}
        fieldSetting={{
          showSetting: true,
          displayFieldKeys: resolvedDisplayFieldKeys,
          choosableFields,
        }}
        onSelectFields={onSelectFields}
        rowSelection={
          readonly
            ? undefined
            : { selectedRowKeys, onChange: onSelectionChange }
        }
      />
      <AlertDetail
        ref={detailRef}
        handleAction={onRefresh}
        readonly={readonly}
      />
    </>
  );
};

export default AlarmTable;
