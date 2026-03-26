'use client';

import BaseInfo from './baseInfo';
import EventTable from '@/app/alarm/components/eventTable';
import AlarmAction from './alarmAction';
import Icon from '@/components/icon';
import DeclareIncident from './declareIncident';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useAlarmApi } from '@/app/alarm/api/alarms';
import { useSettingApi } from '@/app/alarm/api/settings';
import { useCommon } from '@/app/alarm/context/common';
import { useStateMap } from '@/app/alarm/constants/alarm';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import {
  Drawer,
  Button,
  Tag,
  Tabs,
  Timeline,
  Tooltip,
  message,
  Spin,
  Empty,
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
  useRef,
} from 'react';
import {
  ModalRef,
  ModalConfig,
  TabItem,
  Pagination,
  TimeLineItem,
} from '@/app/alarm/types/types';

const AlertDetail = forwardRef<ModalRef, ModalConfig & { readonly?: boolean }>(
  ({ handleAction, readonly = false }, ref) => {
    const STATE_MAP = useStateMap();
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
    const [timeLineData, setTimeLineData] = useState<TimeLineItem[]>([]);
    const timelineRef = useRef<HTMLDivElement>(null);
    const isFetchingRef = useRef<boolean>(false);
    const isBaseInfo = activeTab === 'baseInfo';
    const isEventTab = activeTab === 'event';
    const [pagination, setPagination] = useState<Pagination>({
      current: 1,
      total: 0,
      pageSize: 100,
    });
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
    ];

    useEffect(() => {
      if (!groupVisible || !formData.id) {
        return;
      }
      getEventListData({ alert_id: formData.id });
    }, [groupVisible, formData.id]);

    const getEventListData = async (params: any) => {
      setEventLoading(true);
      try {
        const { items, count } = await getEventList({
          ...params,
          page: pagination.current,
          page_size: pagination.pageSize,
        });
        setEventList(items || []);
        setPagination((prev) => ({ ...prev, total: count }));
      } finally {
        setEventLoading(false);
      }
    };

    useEffect(() => {
      if (activeTab === 'event' && groupVisible && formData.id) {
        getEventListData({ alert_id: formData.id });
      }
    }, [pagination.current, pagination.pageSize, activeTab]);

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
        setEventList([]);
        setGroupVisible(true);
        setTitle(title);
        setFormData(form);
        setActiveTab(defaultTab);
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

    const copyToClipboard = (text: string) => {
      navigator.clipboard.writeText(text);
      message.success(t('alarmCommon.copied'));
    };

    return (
      <Drawer
        title={
          <div className="flex items-center">
            <span>{t('alarms.alertDetail')} </span>
            <span className="text-[var(--color-text-2)] text-sm">-{title}</span>
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
          <div className="flex justify-between">
            <div>
              <Tag color={levelMap[formData.level] as string}>
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
              <b>{formData.content || '--'}</b>
            </div>
            {!readonly && (
              <div>
                <span className="mr-2">
                  {!formData.incident_name && (
                    <DeclareIncident
                      rowData={[formData]}
                      onSuccess={() => {
                        handleAction();
                        setGroupVisible(false);
                      }}
                    />
                  )}
                </span>
                <AlarmAction
                  rowData={[formData]}
                  displayMode="dropdown"
                  onAction={() => {
                    handleAction?.();
                    handleCancel();
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
          {isBaseInfo && <BaseInfo detail={formData} />}
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
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={t('common.noData')}
                />
              )}
            </Spin>
          )}
        </div>
      </Drawer>
    );
  }
);

AlertDetail.displayName = 'alertDetail';
export default AlertDetail;
