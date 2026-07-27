'use client';

import React, {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from 'react';
import {
  Spin,
  Tabs,
  Tag,
  Timeline,
  Tooltip,
} from 'antd';
import { ClockCircleOutlined, CopyOutlined } from '@ant-design/icons';
import AlarmBaseInfo from '@/app/alarm/components/alarm-base-info';
import ContentFormDrawer from '@/components/content-form-drawer';
import AlarmEventTable, {
  type AlarmEventTableItem,
  type AlarmEventLevelOption,
} from '@/app/alarm/components/alarm-event-table';
import AlarmAction from '@/app/alarm/components/alarm-action';
import CompactEmptyState from '@/components/compact-empty-state';
import DetailListPanel from '@/components/detail-list-panel';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import EventLevelTag from '@/app/alarm/components/event-level-tag';
import Icon from '@/components/icon';
import StructuredDataPreview from '@/components/structured-data-preview';
import { useCopy } from '@/hooks/useCopy';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import type {
  AlarmActionContextProps,
  AlarmActionRowData,
} from '@/app/alarm/components/alarm-action/types';

export interface AlarmDetailLevelOption {
  color?: string;
  icon?: string;
  label: string;
  value: string;
}

const toEventLevelOptions = (
  options: AlarmDetailLevelOption[]
): AlarmEventLevelOption[] =>
  options.map((option) => ({
    value: option.value,
    label: option.label,
    color: option.color,
    icon: option.icon,
  }));

export type AlarmDetailEventItem = AlarmEventTableItem;

export interface AlarmDetailLogItem {
  created_at?: string;
  operator?: string;
  operator_object?: string;
  overview?: string;
  [key: string]: unknown;
}

export interface AlarmDetailDrawerData extends AlarmActionRowData {
  alert_id?: string | number;
  content?: string;
  duration?: string;
  enrichment?: Record<string, Record<string, unknown>>;
  first_event_time?: string | null;
  incident_name?: string;
  last_event_time?: string | null;
  level?: string;
  notification_status?: string;
  notify_status?: string;
  operator_user?: string;
  resource_name?: string;
  resource_type?: string;
  source_names?: string;
  title?: string;
}

export interface AlarmDetailDrawerRef {
  showModal: (config: {
    title: string;
    form: AlarmDetailDrawerData;
    type?: string;
    defaultTab?: string;
  }) => void;
}

interface AlarmDetailPagination {
  current: number;
  total: number;
  pageSize: number;
}

interface AlarmDetailDrawerSharedProps {
  handleAction?: () => void;
  levelOptions: AlarmDetailLevelOption[];
  fetchEventList: (
    params: Record<string, unknown>
  ) => Promise<{ items?: AlarmDetailEventItem[]; count?: number }>;
  fetchLogList: (
    params: Record<string, unknown>
  ) => Promise<{ items?: AlarmDetailLogItem[] }>;
  renderDeclareIncident?: (
    alert: AlarmDetailDrawerData,
    context: {
      onSuccess: () => void;
    }
  ) => React.ReactNode;
  renderRelatedAlerts?: (
    alert: AlarmDetailDrawerData,
    context: {
      onRefresh?: () => void;
    }
  ) => React.ReactNode;
}

type AlarmDetailDrawerProps = AlarmDetailDrawerSharedProps &
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

const AlarmDetailDrawer = forwardRef<
  AlarmDetailDrawerRef,
  AlarmDetailDrawerProps
>(
  (
    {
      handleAction,
      levelOptions,
      readonly = false,
      alarmActionProps,
      fetchEventList,
      fetchLogList,
      renderDeclareIncident,
      renderRelatedAlerts,
    },
    ref
  ) => {
    const { t } = useTranslation();
    const { copy } = useCopy();
    const { convertToLocalizedTime } = useLocalizedTime();
    const eventListFetcher = fetchEventList;
    const logListFetcher = fetchLogList;
    const [groupVisible, setGroupVisible] = useState<boolean>(false);
    const [formData, setFormData] = useState<AlarmDetailDrawerData>({});
    const [title, setTitle] = useState<string>('');
    const [activeTab, setActiveTab] = useState<string>('baseInfo');
    const [recordLoading, setRecordLoading] = useState<boolean>(false);
    const [eventLoading, setEventLoading] = useState<boolean>(false);
    const [eventList, setEventList] = useState<AlarmEventTableItem[]>([]);
    const [timeLineData, setTimeLineData] = useState<Array<{ color: string; children: React.ReactNode }>>([]);
    const timelineRef = useRef<HTMLDivElement>(null);
    const isFetchingRef = useRef<boolean>(false);
    const isBaseInfo = activeTab === 'baseInfo';
    const isEventTab = activeTab === 'event';
    const [pagination, setPagination] = useState<AlarmDetailPagination>({
      current: 1,
      total: 0,
      pageSize: 100,
    });
    const tabList = [
      {
        key: 'baseInfo',
        label: t('alarms.summary'),
      },
      {
        key: 'event',
        label: t('alarms.event'),
      },
      {
        key: 'timeline',
        label: t('alarms.changes'),
      },
    ];

    useEffect(() => {
      if (!groupVisible || !formData.id) {
        return;
      }
      void getEventListData({ alert_id: formData.id });
    }, [groupVisible, formData.id]);

    const getEventListData = async (params: Record<string, unknown>) => {
      setEventLoading(true);
      try {
        const { items, count } = await eventListFetcher({
          ...params,
          page: pagination.current,
          page_size: pagination.pageSize,
        });
        setEventList(items || []);
        setPagination((prev) => ({ ...prev, total: count || 0 }));
      } finally {
        setEventLoading(false);
      }
    };

    useEffect(() => {
      if (activeTab === 'event' && groupVisible && formData.id) {
        void getEventListData({ alert_id: formData.id });
      }
    }, [pagination.current, pagination.pageSize, activeTab]);

    useImperativeHandle(ref, () => ({
      showModal: ({
        title,
        form,
        defaultTab = 'baseInfo',
      }) => {
        setEventList([]);
        setGroupVisible(true);
        setTitle(title);
        setFormData(form);
        setActiveTab(defaultTab);
      },
    }));

    useEffect(() => {
      if (groupVisible) {
        void getLogTableData();
      }
    }, [formData, groupVisible, activeTab]);

    useEffect(() => {
      if (formData?.id) {
        void getLogTableData();
      }
    }, [pagination.current, pagination.pageSize]);

    useEffect(() => {
      if (!recordLoading) {
        isFetchingRef.current = false;
      }
    }, [recordLoading]);

    const getLogTableData = async () => {
      setRecordLoading(true);
      try {
        const data: any = await logListFetcher({
          target_id: formData.alert_id,
          page_size: 10000,
          page: 1,
        });
        const nextTimelineData = (data.items || []).map((item: any) => ({
          color: 'blue',
          children: (
            <div className="flex px-4 text-sm">
              <span className="w-[160px]">
                {item.created_at
                  ? convertToLocalizedTime(item.created_at)
                  : '--'}
              </span>
              <span className="w-[160px]">{item.operator_object || '--'}</span>
              <span className="w-[120px]">{item.operator || '--'}</span>
              <EllipsisWithTooltip
                className="mr-[6px] flex-1 overflow-hidden whitespace-nowrap text-ellipsis"
                text={item.overview || '--'}
              />
            </div>
          ),
        }));
        const headerItem = {
          color: 'blue',
          children: (
            <div className="flex px-4 text-sm font-semibold">
              <span className="w-[160px]">{t('alarmCommon.time')}</span>
              <span className="w-[160px]">{t('alarmCommon.action')}</span>
              <span className="w-[120px]">{t('alarmCommon.operator')}</span>
              <span className="flex-1">
                {t('settings.operationLog.summary')}
              </span>
            </div>
          ),
        };
        setTimeLineData([headerItem, ...nextTimelineData]);
      } finally {
        setRecordLoading(false);
      }
    };

    const loadMore = () => {
      if (pagination.current * pagination.pageSize < pagination.total) {
        isFetchingRef.current = true;
        setPagination((prev) => ({
          ...prev,
          current: prev.current + 1,
        }));
      }
    };

    const handleScroll = () => {
      if (!timelineRef.current) return;
      const { scrollTop, scrollHeight, clientHeight } = timelineRef.current;
      if (
        scrollTop + clientHeight >= scrollHeight - 10 &&
        !recordLoading &&
        !isFetchingRef.current
      ) {
        loadMore();
      }
    };

    const handleCancel = () => {
      setGroupVisible(false);
      setActiveTab('baseInfo');
      setTimeLineData([]);
    };

    const changeTab = (val: string) => {
      setActiveTab(val);
      setTimeLineData([]);
      setPagination({
        current: 1,
        total: 0,
        pageSize: 20,
      });
      setRecordLoading(false);
    };

    const levelMeta = formData.level
      ? levelOptions.find((item) => item.value === String(formData.level))
      : undefined;
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
    };

    return (
      <ContentFormDrawer
        title={
          <div className="flex items-center">
            <span>{t('alarms.alertDetail')} </span>
            <span className="text-sm text-[var(--color-text-2)]">-{title}</span>
          </div>
        }
        open={groupVisible}
        width={820}
        onClose={handleCancel}
        maskClosable={false}
        cancelText={t('common.close')}
        onCancel={handleCancel}
      >
        <div>
          <div className="flex justify-between">
            <div>
              <EventLevelTag
                color={levelMeta?.color}
                label={levelMeta?.label || '--'}
                icon={
                  <Icon
                    type={levelMeta?.icon || ''}
                    className="text-sm"
                  />
                }
              />
              <b>{formData.content || '--'}</b>
            </div>
            {!readonly && (
              <div>
                <span className="mr-2">
                  {!formData.incident_name &&
                    renderDeclareIncident?.(formData, {
                      onSuccess: () => {
                        handleAction?.();
                        setGroupVisible(false);
                      },
                    })}
                </span>
                <AlarmAction
                  rowData={[formData]}
                  displayMode="dropdown"
                  {...alarmActionProps}
                  onAction={() => {
                    handleAction?.();
                    handleCancel();
                  }}
                />
              </div>
            )}
          </div>
          <ul className="mt-[10px] mb-[14px] flex space-x-2">
            <li>
              <Tag>
                {stateLabelMap[formData.status as keyof typeof stateLabelMap] || '--'}
              </Tag>
            </li>
            <li className="flex items-center space-x-1">
              <Tag>
                <Tooltip
                  title={formData.alert_id}
                  styles={{
                    body: {
                      minWidth: 'fit-content',
                      whiteSpace: 'nowrap',
                    },
                  }}
                >
                  <span className="mr-2">ID</span>
                  {String(formData.alert_id || '').slice(-6) || '--'}
                </Tooltip>
                <CopyOutlined
                  className="ml-2 cursor-pointer"
                  onClick={() => copy(String(formData.alert_id || ''))}
                />
              </Tag>
            </li>
            <li>
              <Tag>
                <ClockCircleOutlined className="mr-[4px]" />
                {formData.duration}
              </Tag>
            </li>
            <li>
              <Tag>
                {formData.first_event_time && formData.last_event_time && (
                  <span>
                    {formData.first_event_time
                      ? convertToLocalizedTime(formData.first_event_time)
                      : ''}
                    <span className="ml-[2px] mr-[2px]">-</span>
                    {formData.last_event_time
                      ? convertToLocalizedTime(formData.last_event_time)
                      : ''}
                  </span>
                )}
              </Tag>
            </li>
          </ul>
        </div>
        <Tabs activeKey={activeTab} items={tabList} onChange={changeTab} />
        <div className="min-h-[300px] w-full">
          {isBaseInfo && (
            <div className="flex flex-col gap-4">
              <AlarmBaseInfo detail={formData} />
              {formData?.enrichment &&
                Object.keys(formData.enrichment).length > 0 && (
                  <div className="mt-2">
                    <div className="mb-2 font-medium">
                      {t('settings.enrichmentTitle')}
                    </div>
                    {Object.entries(
                      formData.enrichment as Record<string, Record<string, any>>
                    ).map(([ns, fields]) => (
                      <div key={ns} className="mb-2">
                        <div className="mb-1 text-[var(--color-text-3)]">
                          {ns}
                        </div>
                        <DetailListPanel
                          className="rounded-[12px] border border-[var(--color-border-1)] bg-[var(--color-fill-1)]"
                          labelWidthClassName="w-32"
                          items={Object.entries(fields || {}).map(([k, v]) => {
                            const isObjectValue =
                              v !== null && typeof v === 'object';
                            return {
                              key: `${ns}-${k}`,
                              label: k,
                              value: isObjectValue ? JSON.stringify(v, null, 2) : String(v ?? ''),
                              displayValue: isObjectValue ? (
                                <StructuredDataPreview
                                  value={v}
                                  maxHeight="10rem"
                                  className="!bg-transparent !p-0 !text-xs"
                                />
                              ) : (
                                String(v ?? '--')
                              ),
                              copyable: !isObjectValue,
                            };
                          })}
                        />
                      </div>
                    ))}
                  </div>
              )}
              {renderRelatedAlerts?.(formData, { onRefresh: handleAction })}
            </div>
          )}
          {isEventTab && (
            <div className="pt-[10px]">
              <AlarmEventTable
                dataSource={eventList}
                levelOptions={toEventLevelOptions(levelOptions)}
                loading={eventLoading}
                pagination={pagination}
                tableScrollY="calc(100vh - 410px)"
                onChange={(pag) =>
                  setPagination((prev) => ({
                    ...prev,
                    current: pag.current ?? prev.current,
                    pageSize: pag.pageSize ?? prev.pageSize,
                  }))
                }
              />
            </div>
          )}

          {!isBaseInfo && !isEventTab && (
            <Spin spinning={recordLoading}>
              {timeLineData.length > 1 ? (
                <div
                  className="pt-[10px]"
                  style={{ height: 'calc(100vh - 330px)', overflowY: 'auto' }}
                  ref={timelineRef}
                  onScroll={handleScroll}
                >
                  <Timeline items={timeLineData} />
                </div>
              ) : (
                <CompactEmptyState description={t('common.noData')} className="py-6" />
              )}
            </Spin>
          )}
        </div>
      </ContentFormDrawer>
    );
  }
);

AlarmDetailDrawer.displayName = 'alarmDetailDrawer';

export default AlarmDetailDrawer;
