'use client';

import BaseInfo from './baseInfo';
import EventTable from '@/app/alarm/components/eventTable';
import ActionTimeline from './actionTimeline';
import AlarmAction from './alarmAction';
import Icon from '@/components/icon';
import DeclareIncident from './declareIncident';
import RelatedAlertsPanel from './relatedAlertsPanel';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useAlarmApi } from '@/app/alarm/api/alarms';
import { useSettingApi } from '@/app/alarm/api/settings';
import { useCommon } from '@/app/alarm/context/common';
import { useStateMap, useNotifiedStateMap } from '@/app/alarm/constants/alarm';
import { useAiPageContext } from '@/components/ai-page-context';
import {
  ALARM_DETAIL_EVENT_LIMIT,
  buildAlarmDetailPageContext,
} from './alarmDetail.context';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import CompactEmptyState from '@/components/compact-empty-state';
import {
  Drawer,
  Button,
  Tag,
  Tabs,
  Timeline,
  Tooltip,
  message,
  Spin,
} from 'antd';
import {
  StateMap,
  EventItem,
  AlarmTableDataItem,
} from '@/app/alarm/types/alarms';
import { CopyOutlined, ClockCircleOutlined } from '@ant-design/icons';
import React, {
  useState,
  forwardRef,
  useImperativeHandle,
  useEffect,
  useMemo,
  useRef,
} from 'react';
import {
  ModalRef,
  ModalConfig,
  TabItem,
  Pagination,
  TimeLineItem,
} from '@/app/alarm/types/types';
import {
  RelatedTopologyTabContent,
  relatedTopologyTabItem,
  useRelatedTopologyTab,
} from '@/app/alarm/components/related-topology-tab';
const AlertDetail = forwardRef<ModalRef, ModalConfig & { readonly?: boolean }>(
  ({ handleAction, readonly = false }, ref) => {
    const STATE_MAP = useStateMap();
    const notifiedState = useNotifiedStateMap();
    const { levelList, levelMap } = useCommon();
    const { t } = useTranslation();
    const { convertToLocalizedTime } = useLocalizedTime();
    const { getEventList } = useAlarmApi();
    const { getLogList } = useSettingApi();
    const [groupVisible, setGroupVisible] = useState<boolean>(false);
    const [formData, setFormData] = useState<AlarmTableDataItem | any>({});
    const [title, setTitle] = useState<string>('');
    const [activeTab, setActiveTab] = useState<string>('baseInfo');
    const [recordLoading, setRecordLoading] = useState<boolean>(false);
    const [eventLoading, setEventLoading] = useState<boolean>(false);
    const [eventList, setEventList] = useState<EventItem[]>([]);
    const eventRequestIdRef = useRef(0);
    const [timeLineData, setTimeLineData] = useState<TimeLineItem[]>([]);
    const timelineRef = useRef<HTMLDivElement>(null);
    const isFetchingRef = useRef<boolean>(false);
    const [pagination, setPagination] = useState<Pagination>({
      current: 1,
      total: 0,
      pageSize: 100,
    });
    const isBaseInfo = activeTab === 'baseInfo';
    const isEventTab = activeTab === 'event';
    const {
      visible: relatedTopologyVisible,
      centers: relatedTopologyCenters,
      Widget: RelatedTopologyWidget,
      loadFailed: relatedTopologyLoadFailed,
    } =
      useRelatedTopologyTab(
        groupVisible ? formData.monitor_objects : undefined
      );
    const relatedTab = relatedTopologyTabItem(t, relatedTopologyVisible);
    const tabList: TabItem[] = [
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
      {
        key: 'actionRecords',
        label: t('settings.actionTab'),
      },
      ...(relatedTab ? [relatedTab] : []),
    ];

    const getEventListData = async (params: any) => {
      const requestId = ++eventRequestIdRef.current;
      setEventLoading(true);
      try {
        const { items, count } = await getEventList({
          ...params,
          page: pagination.current,
          page_size: pagination.pageSize,
        });
        if (requestId !== eventRequestIdRef.current) return;
        setEventList(items || []);
        setPagination((prev) => ({ ...prev, total: count }));
      } finally {
        if (requestId === eventRequestIdRef.current) {
          setEventLoading(false);
        }
      }
    };

    const prefetchEvents = async (alertId?: number | string) => {
      if (!alertId) return;
      const requestId = ++eventRequestIdRef.current;
      setEventLoading(true);
      try {
        const { items, count } = await getEventList({
          alert_id: alertId,
          page: 1,
          page_size: ALARM_DETAIL_EVENT_LIMIT,
        });
        if (requestId !== eventRequestIdRef.current) return;
        setEventList(items || []);
        setPagination((prev) => ({
          ...prev,
          current: 1,
          total: count || 0,
        }));
      } catch {
        if (requestId !== eventRequestIdRef.current) return;
        setEventList([]);
      } finally {
        if (requestId === eventRequestIdRef.current) {
          setEventLoading(false);
        }
      }
    };

    useEffect(() => {
      if (activeTab !== 'event' || !groupVisible || !formData.id) {
        return;
      }
      getEventListData({ alert_id: formData.id });
    }, [
      pagination.current,
      pagination.pageSize,
      activeTab,
      groupVisible,
      formData.id,
    ]);

    useImperativeHandle(ref, () => ({
      showModal: ({
        title,
        form,
        defaultTab = 'baseInfo',
      }: {
        title: string;
        form: AlarmTableDataItem;
        defaultTab?: string;
      }) => {
        eventRequestIdRef.current += 1;
        setEventList([]);
        setGroupVisible(true);
        setTitle(title);
        setFormData(form);
        setActiveTab(defaultTab);
        setPagination((prev) => ({ ...prev, current: 1, total: 0 }));
        prefetchEvents(form?.id);
      },
    }));

    useEffect(() => {
      if (groupVisible) {
        getLogTableData();
      }
    }, [formData, groupVisible, activeTab]);

    useEffect(() => {
      if (formData?.id) {
        getLogTableData();
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
        const data: any = await getLogList({
          target_id: formData.alert_id,
          page_size: 10000,
          page: 1,
        });
        const _timelineData = (data.items || []).map((item: any) => ({
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
                className="flex-1 whitespace-nowrap overflow-hidden text-ellipsis mr-[6px]"
                text={item.overview || '--'}
              ></EllipsisWithTooltip>
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
        setTimeLineData([headerItem, ..._timelineData]);
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
      eventRequestIdRef.current += 1;
      setGroupVisible(false);
      setActiveTab('baseInfo');
      setTimeLineData([]);
      setEventList([]);
      setFormData({});
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

    const copyToClipboard = (text: string) => {
      navigator.clipboard.writeText(text);
      message.success(t('alarmCommon.copied'));
    };

    const detailContextLabels = useMemo(
      () => ({
        level: (value?: string | number) =>
          levelList.find((item) => item.level_id === Number(value))
            ?.level_display_name || String(value ?? '--'),
        state: (value?: string) =>
          STATE_MAP[value as keyof StateMap] || value || '--',
        formatTime: (value?: string) =>
          value ? convertToLocalizedTime(value) : '--',
        notifyStatus: (value?: string) =>
          notifiedState[value as keyof typeof notifiedState] || value || '--',
        objects: (form: Record<string, any>) => {
          if (!Array.isArray(form.monitor_objects) || !form.monitor_objects.length) {
            return String(form.resource_name || '');
          }
          return form.monitor_objects
            .map((item: { resource_type?: string; resource_name?: string }) =>
              `${item.resource_type || '--'}: ${item.resource_name || '--'}`,
            )
            .join('；');
        },
      }),
      [STATE_MAP, convertToLocalizedTime, levelList, notifiedState],
    );

    useAiPageContext(
      () =>
        buildAlarmDetailPageContext({
          visible: groupVisible,
          eventLoading,
          formData,
          eventData: eventList,
          eventTotal: pagination.total,
          labels: detailContextLabels,
        }),
      [
        groupVisible,
        eventLoading,
        formData,
        eventList,
        pagination.total,
        detailContextLabels,
      ],
    );

    return (
      <Drawer
        title={
          <div className="flex min-w-0 items-center">
            <span className="shrink-0">{t('alarms.alertDetail')} </span>
            <EllipsisWithTooltip
              className="min-w-0 truncate text-sm text-[var(--color-text-2)]"
              text={`-${title}`}
            />
          </div>
        }
        open={groupVisible}
        width={820}
        onClose={handleCancel}
        maskClosable={false}
        footer={
          <div>
            <Button onClick={handleCancel}>{t('common.close')}</Button>
          </div>
        }
      >
        <div>
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex min-w-0 flex-1 items-center gap-2">
              <Tag className="shrink-0" color={levelMap[formData.level] as string}>
                <div className="flex items-center">
                  <Icon
                    type={
                      levelList.find(
                        (item) => item.level_id === Number(formData.level)
                      )?.icon || ''
                    }
                    className="mr-1 text-sm"
                  />
                  {levelList.find(
                    (item) => item.level_id === Number(formData.level)
                  )?.level_display_name || '--'}
                </div>
              </Tag>
              <EllipsisWithTooltip
                className="min-w-0 flex-1 overflow-hidden text-ellipsis whitespace-nowrap font-semibold"
                text={formData.content || '--'}
              />
            </div>
            {!readonly && (
              <div className="flex shrink-0 items-center gap-2">
                {!formData.incident_name && (
                  <DeclareIncident
                    rowData={[formData]}
                    buttonSize="small"
                    onSuccess={() => {
                      handleAction();
                      setGroupVisible(false);
                    }}
                  />
                )}
                <AlarmAction
                  rowData={[formData]}
                  btnSize="small"
                  displayMode="dropdown"
                  onAction={() => {
                    // 修复：原 onAction 里还调 handleCancel()，会让用户点完执行动作时
                    // 右侧 Drawer 被关闭，妨碍继续操作；现在保留刷新、不再关闭 Drawer。
                    handleAction?.();
                  }}
                />
              </div>
            )}
          </div>
          <ul className="flex mt-[10px] mb-[14px] space-x-2">
            <li>
              <Tag>{STATE_MAP[formData.status as keyof StateMap] || '--'}</Tag>
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
                  {formData.alert_id?.slice(-6) || '--'}
                </Tooltip>
                <CopyOutlined
                  className="cursor-pointer ml-2"
                  onClick={() => copyToClipboard(formData.alert_id || '')}
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
        <div className="w-full min-h-[300px]">
          {isBaseInfo && (
            <div className="flex flex-col gap-4">
              <BaseInfo detail={formData} />
              <RelatedAlertsPanel alert={formData} onRefresh={handleAction} />
            </div>
          )}
          {isEventTab && (
            <div className="pt-[10px]">
              <EventTable
                dataSource={eventList}
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

          {activeTab === 'timeline' && (
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
                <CompactEmptyState description={t('common.noData')} />
              )}
            </Spin>
          )}
          {activeTab === 'relatedTopology' && (
            <RelatedTopologyTabContent
              centers={relatedTopologyCenters}
              Widget={RelatedTopologyWidget}
              loadFailed={relatedTopologyLoadFailed}
            />
          )}
          {activeTab === 'actionRecords' && (
            <ActionTimeline alertId={formData.alert_id || ''} />
          )}
        </div>
      </Drawer>
    );
  }
);

AlertDetail.displayName = 'alertDetail';
export default AlertDetail;
