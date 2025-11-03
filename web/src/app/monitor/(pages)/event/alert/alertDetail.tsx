'use client';

import React, {
  useState,
  forwardRef,
  useImperativeHandle,
  useEffect,
  useRef,
  useMemo,
} from 'react';
import { Button, Tag, Tabs, Spin, Timeline } from 'antd';
import OperateModal from '@/app/monitor/components/operate-drawer';
import { useTranslation } from '@/utils/i18n';
import {
  ModalRef,
  ModalConfig,
  TableDataItem,
  TabItem,
  ChartData,
  Pagination,
  TimeLineItem,
  MetricItem,
} from '@/app/monitor/types';
import { HeatMapDataItem } from '@/types';
import { AlertOutlined } from '@ant-design/icons';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useAlertDetailTabs } from '@/app/monitor/hooks/event';
import { useLevelList, useStateMap } from '@/app/monitor/hooks';
import useMonitorApi from '@/app/monitor/api';
import useEventApi from '@/app/monitor/api/event';
import Information from './information';
import EventHeatMap from '@/components/heat-map';
import { getEnumValueUnit, renderChart } from '@/app/monitor/utils/common';
import { LEVEL_MAP } from '@/app/monitor/constants';

const AlertDetail = forwardRef<ModalRef, ModalConfig>(
  ({ objects, userList, onSuccess, objectId }, ref) => {
    const { t } = useTranslation();
    const { getMonitorMetrics } = useMonitorApi();
    const { getMonitorEventDetail, getEventRaw, getSnapshot } = useEventApi();
    const { convertToLocalizedTime } = useLocalizedTime();
    const STATE_MAP = useStateMap();
    const LEVEL_LIST = useLevelList();
    const [groupVisible, setGroupVisible] = useState<boolean>(false);
    const [formData, setFormData] = useState<TableDataItem>({});
    const [title, setTitle] = useState<string>('');
    const [chartData, setChartData] = useState<ChartData[]>([]);
    const [trapData, setTrapData] = useState<TableDataItem>({});
    const [activeTab, setActiveTab] = useState<string>('information');
    const [loading, setLoading] = useState<boolean>(false);
    const [pagination, setPagination] = useState<Pagination>({
      current: 1,
      total: 0,
      pageSize: 100,
    });
    const [tableLoading, setTableLoading] = useState<boolean>(false);
    const [eventChartLoading, setEventChartLoading] = useState<boolean>(false);
    const [pageLoading, setPageLoading] = useState<boolean>(false);
    const tabs: TabItem[] = useAlertDetailTabs();
    const [timeLineData, setTimeLineData] = useState<TimeLineItem[]>([]);
    const [eventData, setEventData] = useState<HeatMapDataItem[]>([]);
    const timelineRef = useRef<HTMLDivElement>(null); // 用于引用 Timeline 容器
    const isFetchingRef = useRef<boolean>(false); // 用于标记是否正在加载数据

    useImperativeHandle(ref, () => ({
      showModal: ({ title, form }) => {
        setGroupVisible(true);
        setTitle(title);
        getMetrics(form, objectId as React.Key);
        if (form?.id) {
          getEventData(form?.id);
        }
      },
    }));

    const isInformation = useMemo(
      () => activeTab === 'information',
      [activeTab]
    );

    useEffect(() => {
      // 当分页加载完成后，重置 isFetchingRef 标志位
      if (!tableLoading) {
        isFetchingRef.current = false;
      }
    }, [tableLoading]);

    const getMetrics = async (row: TableDataItem, id: React.Key) => {
      setPageLoading(true);
      try {
        const data = await getMonitorMetrics({ monitor_object_id: id });
        const metricInfo =
          data.find(
            (item: MetricItem) =>
              item.id === row.policy?.query_condition?.metric_id
          ) || {};
        const form: TableDataItem = {
          ...row,
          metric: metricInfo,
          alertValue: getEnumValueUnit(metricInfo as MetricItem, row.value),
        };
        setFormData(form);
        if (form.policy?.query_condition?.type === 'pmq') {
          getRawData(form);
          return;
        }
        getChartData(form);
      } finally {
        setPageLoading(false);
      }
    };

    const getTableData = async (customPage?: number) => {
      setTableLoading(true);
      const currentPage = customPage || pagination.current;
      const params = {
        page: currentPage,
        page_size: pagination.pageSize,
      };
      try {
        const data = await getMonitorEventDetail(formData.id, params);
        const _timelineData = data.results.map((item: TableDataItem) => ({
          color: LEVEL_MAP[item.level] || 'gray',
          children: (
            <>
              <span className="font-[600] mr-[10px]">
                {item.created_at
                  ? convertToLocalizedTime(item.created_at)
                  : '--'}
              </span>
              {`${formData.metric?.display_name || item.content}`}
              <span className="text-[var(--color-text-3)] ml-[10px]">
                {getEnumValueUnit(formData.metric, item.value)}
              </span>
            </>
          ),
        }));
        setTimeLineData((prev) => [...prev, ..._timelineData]); // 追加新数据
        setPagination((prev: Pagination) => ({
          ...prev,
          total: data.count,
        }));
      } finally {
        setTableLoading(false);
      }
    };

    const getChartData = async (form: TableDataItem = formData) => {
      setLoading(true);
      try {
        const responseData = await getSnapshot({
          id: form.id,
          page_size: -1,
          page: 10,
        });
        const data = (responseData?.results || []).reduce(
          (pre: any, cur: any) => {
            const values = cur.raw_data?.[0]?.values?.at(-1);
            if (values) {
              pre.push(values);
            }
            return pre;
          },
          []
        );

        const config = [
          {
            instance_id_values: form.instance_id_values,
            instance_name: form.monitor_instance_name,
            instance_id: form.monitor_instance_id,
            instance_id_keys: form.metric?.instance_id_keys || [],
            dimensions: form.metric?.dimensions || [],
            title: form.metric?.display_name || '--',
          },
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
      setEventChartLoading(true);
      try {
        const _data = await getMonitorEventDetail(formId, {
          page: 1,
          page_size: -1,
        });
        setEventData(_data.results || []);
      } catch {
        setEventData([]);
      } finally {
        setEventChartLoading(false);
      }
    };

    const loadMore = () => {
      if (pagination.current * pagination.pageSize < pagination.total) {
        isFetchingRef.current = true; // 设置标志位，表示正在加载
        const nextPage = pagination.current + 1;
        setPagination((prev) => ({
          ...prev,
          current: nextPage,
        }));
        getTableData(nextPage);
      }
    };

    const handleScroll = () => {
      if (!timelineRef.current) return;
      const { scrollTop, scrollHeight, clientHeight } = timelineRef.current;
      // 判断是否接近底部
      if (
        scrollTop + clientHeight >= scrollHeight - 10 &&
        !tableLoading &&
        !isFetchingRef.current
      ) {
        loadMore();
      }
    };

    const handleCancel = () => {
      setGroupVisible(false);
      setActiveTab('information');
      setChartData([]);
      setTrapData({});
      setTimeLineData([]);
      setEventData([]);
    };

    const changeTab = (val: string) => {
      setActiveTab(val);
      setTimeLineData([]);
      setPagination({
        current: 1,
        total: 0,
        pageSize: 100,
      });
      setLoading(false);
      setTableLoading(false);
      setEventChartLoading(false);
      if (formData.id) {
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
      getTableData();
    };

    const closeModal = () => {
      handleCancel();
      onSuccess();
    };

    return (
      <div>
        <OperateModal
          title={title}
          visible={groupVisible}
          width={800}
          onClose={handleCancel}
          footer={
            <div>
              <Button onClick={handleCancel}>{t('common.cancel')}</Button>
            </div>
          }
        >
          <Spin spinning={pageLoading}>
            <div>
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
                <li>
                  <span>{t('monitor.events.state')}：</span>
                  <Tag
                    color={
                      formData.status === 'new' ? 'blue' : 'var(--color-text-4)'
                    }
                  >
                    {STATE_MAP[formData.status]}
                  </Tag>
                </li>
              </ul>
            </div>
            <Tabs activeKey={activeTab} items={tabs} onChange={changeTab} />
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
                  eventData={eventData}
                />
              </Spin>
            ) : (
              <div>
                <Spin spinning={eventChartLoading}>
                  <EventHeatMap data={eventData} className="mb-4" />
                </Spin>
                <Spin spinning={tableLoading}>
                  <div
                    className="pt-[10px]"
                    style={{
                      height: 'calc(100vh - 520px)',
                      overflowY: 'auto',
                    }}
                    ref={timelineRef}
                    onScroll={handleScroll}
                  >
                    <Timeline items={timeLineData} />
                  </div>
                </Spin>
              </div>
            )}
          </Spin>
        </OperateModal>
      </div>
    );
  }
);

AlertDetail.displayName = 'alertDetail';
export default AlertDetail;
