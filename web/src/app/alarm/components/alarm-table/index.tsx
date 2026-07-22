'use client';

import React, { useMemo, useRef } from 'react';
import { Tag, Button } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import CustomTable from '@/components/custom-table';
import AlarmLevelIcon from '@/app/alarm/components/alarm-level-icon';
import EventLevelTag from '@/app/alarm/components/event-level-tag';
import UserAvatar from '@/components/user-avatar';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import AlarmAction from '@/app/alarm/components/alarm-action';
import AlarmDetailDrawer, {
  type AlarmDetailDrawerData,
  type AlarmDetailDrawerRef,
  type AlarmDetailEventItem,
  type AlarmDetailLogItem,
} from '@/app/alarm/components/alarm-detail-drawer';
import type {
  AlarmActionContextProps,
  AlarmActionRowData,
} from '@/app/alarm/components/alarm-action/types';
import DeclareIncident, {
  type DeclareIncidentProps,
} from '@/app/alarm/components/declare-incident';
import RelatedAlertsPanel, {
  type RelatedAlertsResponse,
} from '@/app/alarm/components/related-alerts-panel';

export interface AlarmTableLevelOption {
  color?: string;
  icon?: string;
  label: string;
  value: string;
}

export interface AlarmTableRow extends AlarmActionRowData {
  id?: number | string;
  alert_id?: string | number;
  content?: string;
  created_at?: string | null;
  duration?: string;
  event_count?: number;
  first_event_time?: string | null;
  incident_name?: string;
  last_event_time?: string | null;
  level?: string;
  notify_status?: string | null;
  operator_user?: string;
  status?: string;
  title?: string;
  [key: string]: unknown;
}

export interface AlarmTablePagination {
  current?: number;
  pageSize?: number;
  total?: number;
}

interface AlarmTableSharedProps {
  dataSource: AlarmTableRow[];
  detailFetchEventList: (
    params: Record<string, unknown>
  ) => Promise<{ items?: AlarmDetailEventItem[]; count?: number }>;
  detailFetchLogList: (
    params: Record<string, unknown>
  ) => Promise<{ items?: AlarmDetailLogItem[] }>;
  fetchRelatedAlerts: (
    alertId: number,
    params?: { time_window?: number; limit?: number }
  ) => Promise<RelatedAlertsResponse>;
  addAlertsToIncidentAction: (incidentId: string, alertIds: number[]) => Promise<any>;
  levelOptions: AlarmTableLevelOption[];
  declareIncidentProps?: Omit<DeclareIncidentProps, 'rowData' | 'onSuccess'>;
  pagination?: AlarmTablePagination;
  loading: boolean;
  tableScrollY: string;
  selectedRowKeys: React.Key[];
  onChange: (pag: { current?: number; pageSize?: number }) => void;
  onRefresh: () => void;
  onSelectionChange: (keys: React.Key[]) => void;
  extraActions?: (record: AlarmTableRow) => React.ReactNode;
}

export type AlarmTableProps = AlarmTableSharedProps &
  (
    | {
        readonly?: false;
        alarmActionProps: AlarmActionContextProps;
      }
    | {
        readonly: true;
        alarmActionProps?: AlarmActionContextProps;
      }
  );

const AlarmTable: React.FC<AlarmTableProps> = ({
  dataSource,
  detailFetchEventList,
  detailFetchLogList,
  fetchRelatedAlerts,
  addAlertsToIncidentAction,
  levelOptions,
  declareIncidentProps,
  pagination,
  loading,
  tableScrollY,
  selectedRowKeys,
  onChange,
  onRefresh,
  onSelectionChange,
  extraActions,
  alarmActionProps,
  readonly = false,
}) => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const detailRef = useRef<AlarmDetailDrawerRef>(null);
  const levelMetaByValue = useMemo(
    () =>
      levelOptions.reduce<Record<string, AlarmTableLevelOption>>((acc, option) => {
        acc[option.value] = option;
        return acc;
      }, {}),
    [levelOptions]
  );
  const stateLabelMap = useMemo(
    () => ({
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
    }),
    [t]
  );
  const notifiedStateLabelMap = useMemo(
    () => ({
      not_notified: t('alarmCommon.notNotified'),
      success: t('alarmCommon.success'),
      failed: t('alarmCommon.failed'),
      partial_success: t('alarmCommon.partialSuccess'),
    }),
    [t]
  );

  const columns: ColumnsType<AlarmTableRow> = [
    {
      title: t('alarms.level'),
      dataIndex: 'level',
      key: 'level',
      width: 90,
      fixed: 'left',
      render: (_: unknown, { level }: AlarmTableRow) => {
        const target = level ? levelMetaByValue[level] : undefined;
        return (
          <EventLevelTag
            color={target?.color}
            label={target?.label || '--'}
            icon={<AlarmLevelIcon icon={target?.icon || ''} className="w-4 h-4" />}
          />
        );
      },
    },
    {
      title: t('alarms.firstEventTime'),
      dataIndex: 'first_event_time',
      key: 'first_event_time',
      width: 180,
      render: (_: unknown, { first_event_time }: AlarmTableRow) =>
        first_event_time ? convertToLocalizedTime(first_event_time) : '--',
    },
    {
      title: t('alarms.lastEventTime'),
      dataIndex: 'last_event_time',
      key: 'last_event_time',
      width: 180,
      render: (_: unknown, { last_event_time }: AlarmTableRow) =>
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
      render: (_: unknown, record: AlarmTableRow) => (
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
      render: (_: unknown, { status }: AlarmTableRow) => (
        <span>{(status && stateLabelMap[status as keyof typeof stateLabelMap]) || '--'}</span>
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
      shouldCellUpdate: (prev: AlarmTableRow, next: AlarmTableRow) =>
        prev?.operator_user !== next?.operator_user,
      render: (_: unknown, { operator_user }: AlarmTableRow) =>
        operator_user ? <UserAvatar userName={operator_user} /> : '--',
    },
    {
      title: t('alarms.notificationStatus'),
      dataIndex: 'notify_status',
      key: 'notify_status',
      width: 150,
      render: (_: unknown, { notify_status }: AlarmTableRow) => {
        const COLOR_MAP: Record<string, string> = {
          success: 'success',
          failed: 'error',
          partial_success: 'warning',
        };
        const key = notify_status ? notify_status : 'not_notified';
        const color = COLOR_MAP[key] || 'default';
        const text = notifiedStateLabelMap[key as keyof typeof notifiedStateLabelMap] || '--';
        return <Tag color={color}>{text}</Tag>;
      },
    },
    {
      title: t('alarms.alertContent'),
      dataIndex: 'content',
      key: 'content',
      width: 250,
    },
    {
      title: t('alarms.createTime'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (_: unknown, { created_at }: AlarmTableRow) =>
        created_at ? convertToLocalizedTime(created_at) : '--',
    },
    {
      title: t('alarmCommon.action'),
      key: 'action',
      fixed: 'right',
      width: readonly ? 110 : 220,
      render: (_: unknown, record: AlarmTableRow) => (
        <div className="flex items-center">
          <Button
            className={!readonly ? 'mr-[12px]' : ''}
            type="link"
            onClick={() => onOpenDetail(record)}
          >
            {t('common.detail')}
          </Button>
          {!readonly && extraActions && extraActions(record)}
          {!readonly && (
            <AlarmAction
              rowData={[record as AlarmActionRowData]}
              onAction={onRefresh}
              {...alarmActionProps}
            />
          )}
        </div>
      ),
    },
  ];

  const onOpenDetail = (
    row: AlarmTableRow,
    defaultTab: string = 'baseInfo',
  ) => {
    detailRef.current?.showModal({
      title: typeof row.title === 'string' ? row.title : '',
      form: row as AlarmDetailDrawerData,
      type: '',
      defaultTab,
    });
  };

  const renderDeclareIncident = declareIncidentProps
    ? (alert: any, context: { onSuccess: (result: any) => void }) => (
        <DeclareIncident
          rowData={[alert]}
          onSuccess={context.onSuccess}
          {...declareIncidentProps}
        />
    )
    : undefined;

  return (
    <>
      <CustomTable
        scroll={{ y: tableScrollY, x: 'calc(100vw - 320px)' }}
        columns={columns}
        dataSource={dataSource}
        pagination={pagination}
        loading={loading}
        rowKey="id"
        onChange={onChange}
        rowSelection={
          readonly ? undefined : { selectedRowKeys, onChange: onSelectionChange }
        }
      />
      <AlarmDetailDrawer
        ref={detailRef}
        fetchEventList={detailFetchEventList}
        fetchLogList={detailFetchLogList}
        levelOptions={levelOptions}
        handleAction={onRefresh}
        readonly={readonly}
        alarmActionProps={alarmActionProps}
        renderDeclareIncident={renderDeclareIncident}
        renderRelatedAlerts={(alert, context) => (
          <RelatedAlertsPanel
            alert={alert}
            fetchRelatedAlerts={fetchRelatedAlerts}
            addAlertsToIncidentAction={addAlertsToIncidentAction}
            detailFetchEventList={detailFetchEventList}
            detailFetchLogList={detailFetchLogList}
            alarmActionProps={alarmActionProps}
            declareIncidentProps={declareIncidentProps}
            levelOptions={levelOptions}
            onRefresh={context.onRefresh}
          />
        )}
      />
    </>
  );
};

export default AlarmTable;
