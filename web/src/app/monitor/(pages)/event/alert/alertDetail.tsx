'use client';

import React, {
  useState,
  forwardRef,
  useImperativeHandle,
  useEffect,
  useRef,
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
} from '@/app/monitor/types';
import { SearchParams } from '@/app/monitor/types/monitor';
import { AlertOutlined } from '@ant-design/icons';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import useApiClient from '@/utils/request';
import Information from './information';
import {
  getEnumValueUnit,
  mergeViewQueryKeyValues,
  renderChart,
} from '@/app/monitor/utils/common';
import {
  LEVEL_MAP,
  useLevelList,
  useStateMap,
} from '@/app/monitor/constants/monitor';

const AlertDetail = forwardRef<ModalRef, ModalConfig>(
  ({ objects, metrics, userList, onSuccess }, ref) => {
    const { t } = useTranslation();
    const { get } = useApiClient();
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
    const isInformation = activeTab === 'information';
    const tabs: TabItem[] = [
      {
        label: t('common.detail'),
        key: 'information',
      },
      {
        label: t('monitor.events.event'),
        key: 'event',
      },
    ];
    const [timeLineData, setTimeLineData] = useState<TimeLineItem[]>([]);
    const timelineRef = useRef<HTMLDivElement>(null); // 用于引用 Timeline 容器
    const isFetchingRef = useRef<boolean>(false); // 用于标记是否正在加载数据

    useImperativeHandle(ref, () => ({
      showModal: ({ title, form }) => {
        setGroupVisible(true);
        setTitle(title);
        setFormData(form);
      },
    }));

    useEffect(() => {
      if (groupVisible) {
        if (isInformation) {
          if (formData.policy?.query_condition?.type === 'pmq') {
            getRawData();
            return;
          }
          getChartData();
          return;
        }
        getTableData();
      }
    }, [formData, groupVisible, activeTab]);

    useEffect(() => {
      if (formData?.id) {
        getTableData();
      }
    }, [pagination.current, pagination.pageSize]);

    useEffect(() => {
      // 当分页加载完成后，重置 isFetchingRef 标志位
      if (!tableLoading) {
        isFetchingRef.current = false;
      }
    }, [tableLoading]);

    const getParams = () => {
      const _query: string = formData.metric?.query || '';
      const ids = formData.metric?.instance_id_keys || [];
      const params: SearchParams = {
        query: _query.replace(
          /__\$labels__/g,
          mergeViewQueryKeyValues([
            { keys: ids || [], values: formData.instance_id_values },
          ])
        ),
      };
      const startTime = new Date(formData.start_event_time).getTime();
      const endTime = formData.end_event_time
        ? new Date(formData.end_event_time).getTime()
        : new Date().getTime();
      const MAX_POINTS = 100; // 最大数据点数
      const DEFAULT_STEP = 360; // 默认步长
      if (startTime && endTime) {
        params.start = startTime;
        params.end = endTime;
        params.step = Math.max(
          Math.ceil(
            (params.end / MAX_POINTS - params.start / MAX_POINTS) / DEFAULT_STEP
          ),
          1
        );
      }
      return params;
    };

    const getTableData = async () => {
      setTableLoading(true);
      const params = {
        page: pagination.current,
        page_size: pagination.pageSize,
      };
      try {
        const data = await get(
          `/monitor/api/monitor_event/query/${formData.id}/`,
          {
            params,
          }
        );
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

    const getChartData = async () => {
      setLoading(true);
      try {
        const responseData = await get(
          `/monitor/api/metrics_instance/query_range/`,
          {
            params: getParams(),
          }
        );
        const data = responseData.data?.result || [];
        const config = [
          {
            instance_id_values: formData.instance_id_values,
            instance_name: formData.monitor_instance_name,
            instance_id: formData.monitor_instance_id,
            instance_id_keys: formData.metric?.instance_id_keys || [],
            dimensions: formData.metric?.dimensions || [],
            title: formData.metric?.display_name || '--',
          },
        ];
        const _chartData = renderChart(data, config);
        setChartData(_chartData);
      } finally {
        setLoading(false);
      }
    };

    const getRawData = async () => {
      setLoading(true);
      try {
        const responseData = await get(
          `/monitor/api/monitor_event/raw_data/${formData.id}/`
        );
        setTrapData(responseData);
      } finally {
        setLoading(false);
      }
    };

    const loadMore = () => {
      if (pagination.current * pagination.pageSize < pagination.total) {
        isFetchingRef.current = true; // 设置标志位，表示正在加载
        setPagination((prev) => ({
          ...prev,
          current: prev.current + 1,
        }));
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
          <div>
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
            <Spin className="w-full" spinning={loading || tableLoading}>
              {isInformation ? (
                <Information
                  formData={formData}
                  objects={objects}
                  metrics={metrics}
                  userList={userList}
                  onClose={closeModal}
                  trapData={trapData}
                  chartData={chartData}
                />
              ) : (
                <div
                  className="pt-[10px]"
                  style={{
                    height: 'calc(100vh - 276px)',
                    overflowY: 'auto',
                  }}
                  ref={timelineRef}
                  onScroll={handleScroll}
                >
                  <Timeline items={timeLineData} />
                </div>
              )}
            </Spin>
          </div>
        </OperateModal>
      </div>
    );
  }
);

AlertDetail.displayName = 'alertDetail';
export default AlertDetail;
