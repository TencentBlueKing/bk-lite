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
import OperateModal from '@/components/operate-drawer';
import { useAiPageContext } from '@/components/ai-page-context';
import { useTranslation } from '@/utils/i18n';
import {
  ModalRef,
  ModalConfig,
  TableDataItem,
  TabItem,
  ChartData,
  MetricItem
} from '@/app/monitor/types';
import { AlertOutlined } from '@ant-design/icons';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useAlertDetailTabs, useEventActionMap } from '@/app/monitor/hooks/event';
import {
  useLevelList,
  useStateMap,
  useAlertTypeMap
} from '@/app/monitor/hooks';
import useMonitorApi from '@/app/monitor/api';
import useEventApi from '@/app/monitor/api/event';
import Information from './information';
import { renderChart } from '@/app/monitor/utils/common';
import { useUnitTransform } from '@/app/monitor/hooks/useUnitTransform';
import { LEVEL_MAP } from '@/app/monitor/constants';
import { formatUserDisplayName } from '@/utils/userDisplay';
import type { ListRef } from 'rc-virtual-list';
import {
  buildAlertDetailMetricQuery,
  buildAlertSnapshotChartModel,
  decorateAlertSnapshotChartData,
  resolveAlertDetailChartUnit,
  resolveAlertDetailMetric
} from './alertDetailUtils';
import { buildAlertDetailPageContext } from './alertDetail.context';

const TIMELINE_ITEM_HEIGHT = 48;

type AlertEventItem = TableDataItem;

const AlertDetail = forwardRef<ModalRef, ModalConfig>(
  ({ objects, userList, onSuccess }, ref) => {
    const { t } = useTranslation();
    const { getMonitorMetrics } = useMonitorApi();
    const { getMonitorEventDetail, getEventRaw, getSnapshot } = useEventApi();
    const { convertToLocalizedTime } = useLocalizedTime();
    const { getEnumValueUnit, findUnitNameById } = useUnitTransform();
    const STATE_MAP = useStateMap();
    const ALERT_TYPE_MAP = useAlertTypeMap();
    const LEVEL_LIST = useLevelList();
    const EVENT_ACTION_MAP = useEventActionMap();
    const [groupVisible, setGroupVisible] = useState<boolean>(false);
    const [formData, setFormData] = useState<TableDataItem>({});
    const [title, setTitle] = useState<string>('');
    const [chartData, setChartData] = useState<ChartData[]>([]);
    const [chartXAxisDomain, setChartXAxisDomain] = useState<
      [number, number] | null
    >(null);
    const [chartUnit, setChartUnit] = useState<string>('');
    const [trapData, setTrapData] = useState<TableDataItem>({});
    const [activeTab, setActiveTab] = useState<string>('information');
    const [loading, setLoading] = useState<boolean>(false);
    const [eventLoading, setEventLoading] = useState<boolean>(false);
    const [pageLoading, setPageLoading] = useState<boolean>(false);
    const tabs: TabItem[] = useAlertDetailTabs();
    const [eventData, setEventData] = useState<AlertEventItem[]>([]);
    const eventRequestIdRef = useRef(0);
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

    useImperativeHandle(ref, () => ({
      showModal: ({ title, form }) => {
        eventRequestIdRef.current += 1;
        setGroupVisible(true);
        setTitle(title);
        setFormData(form || {});
        setEventData([]);
        setTrapData({});
        setChartData([]);
        setChartXAxisDomain(null);
        setChartUnit('');
        getMetrics(form);
        getEventData(form?.id);
      }
    }));

    const isInformation = useMemo(
      () => activeTab === 'information',
      [activeTab]
    );

    const getMetrics = async (row: TableDataItem) => {
      setPageLoading(true);
      try {
        const query = buildAlertDetailMetricQuery(row);
        let metricInfo: MetricItem | Record<string, never> = {};
        if (query) {
          const { items: data } = await getMonitorMetrics(query);
          metricInfo =
            data.find((item: MetricItem) => Number(item.id) === query.id) ||
            {};
        }
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
        const snapshots = responseData?.snapshots || [];
        const isNoDataAlert = form.alert_type === 'no_data';
        const snapshotChart = buildAlertSnapshotChartModel(
          snapshots,
          isNoDataAlert ? { alertType: 'no_data' } : undefined
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
        const rendered = renderChart(
          [{ values: snapshotChart.dataValues, metric: form.metric }],
          config
        );
        if (isNoDataAlert) {
          setChartData(
            decorateAlertSnapshotChartData(
              rendered,
              snapshotChart.gapIntervals,
              snapshotChart.xAxisDomain,
              snapshotChart.noDataTimes
            )
          );
          setChartXAxisDomain(snapshotChart.xAxisDomain);
        } else {
          setChartData(rendered);
          setChartXAxisDomain(null);
        }
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
      const requestId = ++eventRequestIdRef.current;
      setEventLoading(true);
      try {
        const _data = await getMonitorEventDetail(formId, {
          page: 1,
          page_size: -1
        });
        if (requestId !== eventRequestIdRef.current) return;
        setEventData(_data.results || []);
      } catch {
        if (requestId !== eventRequestIdRef.current) return;
        setEventData([]);
      } finally {
        if (requestId === eventRequestIdRef.current) {
          setEventLoading(false);
        }
      }
    };

    const renderTimelineContent = useCallback(
      (item: AlertEventItem) => {
        const actionLabel = item.action
          ? EVENT_ACTION_MAP[item.action as keyof typeof EVENT_ACTION_MAP]
          : '';
        const levelLabel =
          LEVEL_LIST.find((entry) => entry.value === item.level)?.label ||
          item.level ||
          '';
        return (
          <>
            <span className="font-[600] mr-[10px] inline-block shrink-0">
              {item.event_time ? convertToLocalizedTime(item.event_time) : '--'}
            </span>
            {actionLabel ? (
              <Tag className="mr-[8px]">{actionLabel}</Tag>
            ) : null}
            {levelLabel ? (
              <Tag
                className="mr-[8px]"
                color={LEVEL_MAP[item.level] as string}
              >
                {levelLabel}
              </Tag>
            ) : null}
            {`${formData.metric?.display_name || item.content}`}
            <span className="text-[var(--color-text-3)] ml-[10px]">
              {getEnumValueUnit(formData.metric, item.value)}
            </span>
          </>
        );
      },
      [EVENT_ACTION_MAP, LEVEL_LIST, convertToLocalizedTime, formData.metric, getEnumValueUnit]
    );

    const renderTimelineItem = useCallback(
      (
        item: AlertEventItem,
        _index: number,
        props: { style: React.CSSProperties }
      ) => {
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
                border: '3px solid var(--color-primary)',
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
      [eventData.length, renderTimelineContent]
    );

    const handleCancel = () => {
      eventRequestIdRef.current += 1;
      setGroupVisible(false);
      setActiveTab('information');
      setChartData([]);
      setChartXAxisDomain(null);
      setChartUnit('');
      setTrapData({});
      setEventData([]);
      setFormData({});
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

    const closeModal = () => {
      handleCancel();
      onSuccess?.();
    };

    const detailContextLabels = useMemo(
      () => ({
        level: (value?: string) =>
          LEVEL_LIST.find((item) => item.value === value)?.label ||
          value ||
          '--',
        state: (value?: string) => STATE_MAP[value || ''] || value || '--',
        alertType: (value?: string) =>
          ALERT_TYPE_MAP[value || ''] || value || '--',
        action: (value?: string) =>
          (value
            ? EVENT_ACTION_MAP[value as keyof typeof EVENT_ACTION_MAP]
            : '') || '',
        formatTime: (value?: string) =>
          value ? convertToLocalizedTime(value) : '--',
        formatValue: (metric: unknown, value: unknown) =>
          String(
            getEnumValueUnit(metric as MetricItem, value as number | string) ??
              ''
          ),
        notice: (noticed?: boolean) =>
          t(`monitor.events.${noticed ? 'notified' : 'unnotified'}`),
        formatPerson: (value?: unknown) =>
          formatUserDisplayName(value, userList),
        formatUnit: (unitId?: string) => findUnitNameById(unitId || '')
      }),
      [
        LEVEL_LIST,
        STATE_MAP,
        ALERT_TYPE_MAP,
        EVENT_ACTION_MAP,
        convertToLocalizedTime,
        getEnumValueUnit,
        t,
        userList,
        findUnitNameById
      ]
    );

    useAiPageContext(
      () =>
        buildAlertDetailPageContext({
          visible: groupVisible,
          pageLoading,
          eventLoading,
          formData,
          eventData,
          trapData,
          chartUnit,
          labels: detailContextLabels
        }),
      [
        groupVisible,
        pageLoading,
        eventLoading,
        formData,
        eventData,
        trapData,
        chartUnit,
        detailContextLabels
      ]
    );

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
                      chartXAxisDomain={chartXAxisDomain}
                      chartUnit={chartUnit}
                    />
                  </Spin>
                ) : (
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
