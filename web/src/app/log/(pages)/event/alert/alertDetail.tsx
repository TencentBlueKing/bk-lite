'use client';

import React, {
  useState,
  forwardRef,
  useImperativeHandle,
  useRef,
  useMemo,
  useCallback,
  useEffect
} from 'react';
import { Button, Tag, Tabs, Spin } from 'antd';
import VirtualList from 'rc-virtual-list';
import OperateModal from '@/app/log/components/operate-drawer';
import { useTranslation } from '@/utils/i18n';
import { ModalRef, ModalConfig, TableDataItem, TabItem } from '@/app/log/types';
import { HeatMapDataItem } from '@/types';
import { AlertOutlined } from '@ant-design/icons';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { HeatMapCellClickPayload } from '@/components/heat-map';
import { useAlertDetailTabs } from '@/app/log/hooks/event';
import useLogEventApi from '@/app/log/api/event';
import Information from './information';
import EventDetail from './eventDetail';
import { LEVEL_MAP } from '@/app/log/constants';
import { useLevelList, useStateMap } from '@/app/log/hooks/event';
import EventHeatMap, { getHeatMapCellColor } from '@/components/heat-map';
import type { ListRef } from 'rc-virtual-list';

const TIMELINE_ITEM_HEIGHT = 48;

type AlertEventItem = TableDataItem & HeatMapDataItem;

const AlertDetail = forwardRef<ModalRef, ModalConfig>(
  ({ userList, onSuccess }, ref) => {
    const { t } = useTranslation();
    const { geEventList, getEventRaw } = useLogEventApi();
    const { convertToLocalizedTime } = useLocalizedTime();
    const STATE_MAP = useStateMap();
    const LEVEL_LIST = useLevelList();
    const eventDetailRef = useRef<ModalRef>(null);
    const timelineRef = useRef<ListRef | null>(null);
    const timelineContainerRef = useRef<HTMLDivElement | null>(null);
    const [groupVisible, setGroupVisible] = useState<boolean>(false);
    const [formData, setFormData] = useState<TableDataItem>({});
    const [title, setTitle] = useState<string>('');
    const [rawData, setRawData] = useState<TableDataItem[]>([]);
    const [activeTab, setActiveTab] = useState<string>('information');
    const [loading, setLoading] = useState<boolean>(false);
    const [eventLoading, setEventLoading] = useState<boolean>(false);
    const tabs: TabItem[] = useAlertDetailTabs();
    const [eventData, setEventData] = useState<AlertEventItem[]>([]);
    const [timelineHeight, setTimelineHeight] = useState(200);

    useEffect(() => {
      const container = timelineContainerRef.current;
      if (!container) return;
      const observer = new ResizeObserver((entries) => {
        for (const entry of entries) {
          const h = Math.floor(entry.contentRect.height);
          if (h > 0) setTimelineHeight(h);
        }
      });
      observer.observe(container);
      return () => observer.disconnect();
    }, [activeTab, groupVisible]);

    // 预计算每个事件所在小时的事件数量 → 对应热力图颜色
    const eventDotColors = useMemo(() => {
      const hourCountMap = new Map<string, number>();
      eventData.forEach((item) => {
        if (!item.event_time) return;
        const d = new Date(item.event_time);
        const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}-${d.getHours()}`;
        hourCountMap.set(key, (hourCountMap.get(key) || 0) + 1);
      });
      return eventData.map((item) => {
        if (!item.event_time) return '#d9d9d9';
        const d = new Date(item.event_time);
        const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}-${d.getHours()}`;
        const count = hourCountMap.get(key) || 0;
        return getHeatMapCellColor(count, 'day');
      });
    }, [eventData]);

    useImperativeHandle(ref, () => ({
      showModal: ({ title, form }) => {
        setGroupVisible(true);
        setTitle(title);
        setFormData(form);
        getRawData(form);
      }
    }));

    const isInformation = useMemo(
      () => activeTab === 'information',
      [activeTab]
    );

    const getEventData = async () => {
      if (!formData.id) return;
      setEventLoading(true);
      try {
        const data = await geEventList({
          page: 1,
          page_size: -1,
          alert_id: formData.id
        });
        setEventData(data || []);
      } catch {
        setEventData([]);
      } finally {
        setEventLoading(false);
      }
    };

    const getRawData = async (form: TableDataItem = formData) => {
      setLoading(true);
      try {
        const responseData = await getEventRaw(form.id);
        const isAggregate = form.alert_type === 'aggregate';
        const data = responseData?.raw_data?.data;
        const aggregateData = data?.query_result ? [data?.query_result] : [];
        const result = !isAggregate
          ? Array.isArray(data)
            ? data
            : []
          : aggregateData;
        const rawList = result.map((item: TableDataItem, index: number) => ({
          ...item,
          id: index
        }));
        setRawData(rawList);
      } catch {
        setRawData([]);
      } finally {
        setLoading(false);
      }
    };

    const openEventDetail = useCallback(
      (row: TableDataItem) => {
        eventDetailRef.current?.showModal({
          title: t('log.event.originalLog'),
          type: 'add',
          form: {
            ...row,
            alert_type: formData.alert_type,
            show_fields: formData.show_fields || []
          }
        });
      },
      [formData.alert_type, formData.show_fields, t]
    );

    const renderTimelineContent = useCallback(
      (item: AlertEventItem) => (
        <>
          <span className="font-[600] mr-[10px] inline-block shrink-0">
            {item.event_time ? convertToLocalizedTime(item.event_time) : '--'}
          </span>
          {`${formData.metric?.display_name || item.content}`}
          <Button
            type="link"
            className="ml-[10px] h-auto p-0 align-baseline leading-[22px]"
            onClick={() => openEventDetail(item)}
          >
            {t('common.detail')}
          </Button>
        </>
      ),
      [convertToLocalizedTime, formData.metric, openEventDetail, t]
    );

    const renderTimelineItem = useCallback(
      (
        item: AlertEventItem,
        _index: number,
        props: { style: React.CSSProperties }
      ) => {
        const dotColor = eventDotColors[_index] || '#d9d9d9';
        const isLast = _index === eventData.length - 1;
        return (
          <div style={props.style} className="relative">
            {/* Tail line */}
            {!isLast && (
              <div
                className="absolute"
                style={{
                  insetInlineStart: 7,
                  top: 16,
                  bottom: 0,
                  width: 2,
                  background: 'rgba(5, 5, 5, 0.06)'
                }}
              />
            )}
            {/* Dot */}
            <div
              style={{
                position: 'absolute',
                width: 10,
                height: 10,
                top: 6,
                insetInlineStart: 3,
                borderRadius: '50%',
                border: `3px solid ${dotColor}`,
                backgroundColor: '#fff',
                boxSizing: 'border-box'
              }}
            />
            {/* Content */}
            <div
              style={{
                marginInlineStart: 26,
                paddingBottom: isLast ? 0 : 20,
                wordBreak: 'break-word',
                fontSize: 14,
                lineHeight: '22px'
              }}
            >
              {renderTimelineContent(item)}
            </div>
          </div>
        );
      },
      [eventData.length, eventDotColors, renderTimelineContent]
    );

    const handleCancel = () => {
      setGroupVisible(false);
      setActiveTab('information');
      setRawData([]);
      setEventData([]);
      timelineRef.current?.scrollTo(0);
    };

    const changeTab = (val: string) => {
      setActiveTab(val);
      setLoading(false);
      setEventLoading(false);
      if (val === 'information') {
        getRawData();
        return;
      }
      getEventData();
    };

    const handleHeatMapCellClick = useCallback(
      ({ startTime, endTime }: HeatMapCellClickPayload) => {
        const startMs = new Date(startTime).getTime();
        const endMs = new Date(endTime).getTime();
        const targetIndex = eventData.findIndex((item) => {
          if (!item.event_time) return false;
          const eventMs = new Date(item.event_time).getTime();
          return eventMs >= startMs && eventMs < endMs;
        });

        if (targetIndex >= 0) {
          timelineRef.current?.scrollTo({ index: targetIndex, align: 'top' });
        }
      },
      [eventData]
    );

    const closeModal = () => {
      handleCancel();
      onSuccess?.();
    };

    return (
      <div>
        <OperateModal
          title={title}
          visible={groupVisible}
          width={900}
          destroyOnClose
          onClose={handleCancel}
          styles={{
            body: {
              overflow: 'hidden',
              padding: 16,
              display: 'flex',
              flexDirection: 'column'
            }
          }}
          footer={
            <div>
              <Button onClick={handleCancel}>{t('common.cancel')}</Button>
            </div>
          }
        >
          <Spin
            spinning={loading}
            wrapperClassName="flex-1 min-h-0 [&>.ant-spin-container]:h-full"
          >
            <div className="flex flex-col h-full overflow-hidden">
              {/* Fixed header area */}
              <div className="shrink-0">
                <div>
                  <Tag
                    icon={<AlertOutlined />}
                    color={LEVEL_MAP[formData.level] as string}
                  >
                    {LEVEL_LIST.find((item) => item.value === formData.level)
                      ?.label || '--'}
                  </Tag>
                  <b>{formData.alert_name || '--'}</b>
                </div>
                <ul className="flex mt-[10px]">
                  <li className="mr-[20px]">
                    <span>{t('common.time')}：</span>
                    <span>
                      {formData.updated_at
                        ? convertToLocalizedTime(formData.updated_at)
                        : '--'}
                    </span>
                  </li>
                  <li>
                    <span>{t('log.event.state')}：</span>
                    <Tag
                      color={
                        formData.status === 'new'
                          ? 'blue'
                          : 'var(--color-text-4)'
                      }
                    >
                      {STATE_MAP[formData.status]}
                    </Tag>
                  </li>
                </ul>
                <Tabs activeKey={activeTab} items={tabs} onChange={changeTab} />
              </div>
              {/* Content area — fills remaining height */}
              <div
                className={`flex-1 min-h-0 ${isInformation ? 'overflow-auto' : 'overflow-hidden'}`}
              >
                {isInformation ? (
                  <Spin className="w-full" spinning={loading}>
                    <Information
                      formData={formData}
                      userList={userList}
                      onClose={closeModal}
                      rawData={rawData}
                    />
                  </Spin>
                ) : (
                  <div className="flex flex-col h-full">
                    <div className="shrink-0">
                      <Spin spinning={eventLoading}>
                        <EventHeatMap
                          data={eventData}
                          className="mb-4"
                          onCellClick={handleHeatMapCellClick}
                        />
                      </Spin>
                    </div>
                    <div
                      ref={timelineContainerRef}
                      className="flex-1 min-h-0 pl-[4px] pt-[10px] overflow-hidden"
                    >
                      <Spin spinning={eventLoading}>
                        <VirtualList
                          ref={timelineRef}
                          data={eventData}
                          height={timelineHeight - 10}
                          itemHeight={TIMELINE_ITEM_HEIGHT}
                          itemKey={(item) =>
                            item.id || item.event_time || item.content
                          }
                        >
                          {renderTimelineItem}
                        </VirtualList>
                      </Spin>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </Spin>
        </OperateModal>
        <EventDetail ref={eventDetailRef} />
      </div>
    );
  }
);

AlertDetail.displayName = 'alertDetail';
export default AlertDetail;
