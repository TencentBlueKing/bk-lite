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
import OperateModal from '@/app/monitor/components/operate-drawer';
import { useTranslation } from '@/utils/i18n';
import {
  ModalRef,
  ModalConfig,
  TableDataItem,
  TabItem,
  ChartData,
  MetricItem
} from '@/app/monitor/types';
import { HeatMapDataItem } from '@/types';
import { AlertOutlined } from '@ant-design/icons';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { HeatMapCellClickPayload } from '@/components/heat-map';
import { useAlertDetailTabs } from '@/app/monitor/hooks/event';
import {
  useLevelList,
  useStateMap,
  useAlertTypeMap
} from '@/app/monitor/hooks';
import useMonitorApi from '@/app/monitor/api';
import useEventApi from '@/app/monitor/api/event';
import Information from './information';
import EventHeatMap, { getHeatMapCellColor } from '@/components/heat-map';
import { renderChart } from '@/app/monitor/utils/common';
import { useUnitTransform } from '@/app/monitor/hooks/useUnitTransform';
import { LEVEL_MAP } from '@/app/monitor/constants';
import type { ListRef } from 'rc-virtual-list';
import {
  buildAlertSnapshotChartValues,
  resolveAlertDetailChartUnit,
  resolveAlertDetailMetric
} from './alertDetailUtils';

const TIMELINE_ITEM_HEIGHT = 48;

type AlertEventItem = TableDataItem & HeatMapDataItem;

const AlertDetail = forwardRef<ModalRef, ModalConfig>(
  ({ objects, userList, onSuccess, objectId }, ref) => {
    const { t } = useTranslation();
    const { getMonitorMetrics } = useMonitorApi();
    const { getMonitorEventDetail, getEventRaw, getSnapshot } = useEventApi();
    const { convertToLocalizedTime } = useLocalizedTime();
    const { getEnumValueUnit } = useUnitTransform();
    const STATE_MAP = useStateMap();
    const ALERT_TYPE_MAP = useAlertTypeMap();
    const LEVEL_LIST = useLevelList();
    const [groupVisible, setGroupVisible] = useState<boolean>(false);
    const [formData, setFormData] = useState<TableDataItem>({});
    const [title, setTitle] = useState<string>('');
    const [chartData, setChartData] = useState<ChartData[]>([]);
    const [chartUnit, setChartUnit] = useState<string>('');
    const [trapData, setTrapData] = useState<TableDataItem>({});
    const [activeTab, setActiveTab] = useState<string>('information');
    const [loading, setLoading] = useState<boolean>(false);
    const [eventLoading, setEventLoading] = useState<boolean>(false);
    const [pageLoading, setPageLoading] = useState<boolean>(false);
    const tabs: TabItem[] = useAlertDetailTabs();
    const [eventData, setEventData] = useState<AlertEventItem[]>([]);
    const timelineRef = useRef<ListRef | null>(null);
    const timelineContainerRef = useRef<HTMLDivElement | null>(null);
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
      // 按小时分组统计数量
      const hourCountMap = new Map<string, number>();
      eventData.forEach((item) => {
        if (!item.event_time) return;
        const d = new Date(item.event_time);
        const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}-${d.getHours()}`;
        hourCountMap.set(key, (hourCountMap.get(key) || 0) + 1);
      });
      // 为每个事件生成颜色（按天视图的阈值，因为按小时分桶）
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
        getMetrics(form, objectId as React.Key);
      }
    }));

    const isInformation = useMemo(
      () => activeTab === 'information',
      [activeTab]
    );

    const getMetrics = async (row: TableDataItem, id: React.Key) => {
      setPageLoading(true);
      try {
        const data = await getMonitorMetrics({ monitor_object_id: id });
        const metricInfo =
          data.find(
            (item: MetricItem) =>
              item.id === row.policy?.query_condition?.metric_id
          ) || {};
        const metricWithUnit = resolveAlertDetailMetric(row, metricInfo);
        const form: TableDataItem = {
          ...row,
          metric: metricWithUnit,
          alertValue: getEnumValueUnit(metricWithUnit as MetricItem, row.value)
        };
        setFormData(form);
        setChartUnit(resolveAlertDetailChartUnit(form, ''));
        if (form.policy?.query_condition?.type === 'pmq') {
          getRawData(form);
          return;
        }
        getChartData(form);
      } finally {
        setPageLoading(false);
      }
    };

    const getChartData = async (form: TableDataItem = formData) => {
      setLoading(true);
      try {
        const responseData = await getSnapshot({
          id: form.id,
          page_size: -1,
          page: 10
        });
        const data = buildAlertSnapshotChartValues(
          responseData?.snapshots || []
        );
        setChartUnit(
          resolveAlertDetailChartUnit(form, responseData?.chart_unit)
        );
        const config = [
          {
            instance_id_values: form.instance_id_values,
            instance_name: form.monitor_instance_name,
            instance_id: form.monitor_instance_id,
            instance_id_keys: form.metric?.instance_id_keys || [],
            dimensions: form.metric?.dimensions || [],
            title: form.metric?.display_name || '--'
          }
        ];
        const _chartData = renderChart(
          [{ values: data, metric: form.metric }],
          config
        );
        setChartData(_chartData);
      } finally {
        setLoading(false);
      }
    };

    const getRawData = async (form: TableDataItem = formData) => {
      setLoading(true);
      try {
        const responseData = await getEventRaw(form.id);
        setTrapData(responseData);
      } finally {
        setLoading(false);
      }
    };

    const getEventData = async (formId?: string | number) => {
      if (!formId) return;
      setEventLoading(true);
      try {
        const _data = await getMonitorEventDetail(formId, {
          page: 1,
          page_size: -1
        });
        setEventData(_data.results || []);
      } catch {
        setEventData([]);
      } finally {
        setEventLoading(false);
      }
    };

    const renderTimelineContent = useCallback(
      (item: AlertEventItem) => (
        <>
          <span className="font-[600] mr-[10px] inline-block shrink-0">
            {item.event_time ? convertToLocalizedTime(item.event_time) : '--'}
          </span>
          {`${formData.metric?.display_name || item.content}`}
          <span className="text-[var(--color-text-3)] ml-[10px]">
            {getEnumValueUnit(formData.metric, item.value)}
          </span>
        </>
      ),
      [convertToLocalizedTime, formData.metric, getEnumValueUnit]
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
      setChartData([]);
      setChartUnit('');
      setTrapData({});
      setEventData([]);
      timelineRef.current?.scrollTo(0);
    };

    const changeTab = (val: string) => {
      setActiveTab(val);
      setLoading(false);
      setEventLoading(false);
      if (formData.id && val !== 'information') {
        getEventData(formData.id);
      }
      if (val === 'information') {
        if (formData.policy?.query_condition?.type === 'pmq') {
          getRawData();
          return;
        }
        getChartData();
        return;
      }
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
          width={800}
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
            spinning={pageLoading}
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
                  <b>{formData.content || '--'}</b>
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
                  <li className="mr-[20px]">
                    <span>{t('monitor.events.alertType')}：</span>
                    <Tag color="default">
                      {ALERT_TYPE_MAP[formData.alert_type] || '--'}
                    </Tag>
                  </li>
                  <li>
                    <span>{t('monitor.events.state')}：</span>
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
                      objects={objects}
                      metrics={formData.metrics || {}}
                      userList={userList}
                      onClose={closeModal}
                      trapData={trapData}
                      chartData={chartData}
                      chartUnit={chartUnit}
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
      </div>
    );
  }
);

AlertDetail.displayName = 'alertDetail';
export default AlertDetail;
