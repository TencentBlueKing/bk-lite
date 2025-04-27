'use client';
import React, { useEffect, useState, useRef } from 'react';
import {
  Input,
  Button,
  Checkbox,
  Space,
  Tag,
  Modal,
  message,
  Tabs,
  Spin,
  Tooltip,
} from 'antd';
import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';
import Icon from '@/components/icon';
import {
  deepClone,
  getRandomColor,
  getEnumValueUnit,
} from '@/app/monitor/utils/common';
import {
  ColumnItem,
  ModalRef,
  Pagination,
  TableDataItem,
  UserItem,
  TabItem,
  TimeSelectorDefaultValue,
} from '@/app/monitor/types';
import { MetricItem, ObectItem } from '@/app/monitor/types/monitor';
import { AlertOutlined } from '@ant-design/icons';
import { FiltersConfig } from '@/app/monitor/types/monitor';
import CustomTable from '@/components/custom-table';
import TimeSelector from '@/components/time-selector';
import Permission from '@/components/permission';
import StackedBarChart from '@/app/monitor/components/charts/stackedBarChart';
import AlertDetail from './alertDetail';
import Collapse from '@/components/collapse';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import dayjs, { Dayjs } from 'dayjs';
import { useCommon } from '@/app/monitor/context/common';
import alertStyle from './index.module.scss';
import {
  LEVEL_MAP,
  useLevelList,
  useStateMap,
} from '@/app/monitor/constants/monitor';

const Alert: React.FC = () => {
  const { get, patch, isLoading } = useApiClient();
  const { t } = useTranslation();
  const STATE_MAP = useStateMap();
  const LEVEL_LIST = useLevelList();
  const { confirm } = Modal;
  const { convertToLocalizedTime } = useLocalizedTime();
  const commonContext = useCommon();
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const detailRef = useRef<ModalRef>(null);
  const users = useRef(commonContext?.userList || []);
  const userList: UserItem[] = users.current;
  const [searchText, setSearchText] = useState<string>('');
  const [tableLoading, setTableLoading] = useState<boolean>(false);
  const [chartLoading, setChartLoading] = useState<boolean>(false);
  const [tableData, setTableData] = useState<TableDataItem[]>([]);
  const [pagination, setPagination] = useState<Pagination>({
    current: 1,
    total: 0,
    pageSize: 20,
  });
  const [frequence, setFrequence] = useState<number>(0);
  const beginTime: number = dayjs().subtract(10080, 'minute').valueOf();
  const lastTime: number = dayjs().valueOf();
  const [timeRange, setTimeRange] = useState<number[]>([beginTime, lastTime]);
  const timeDefaultValue =
    useRef<TimeSelectorDefaultValue>({
      selectValue: 10080,
      rangePickerVaule: null,
    })?.current || {};
  const [filters, setFilters] = useState<FiltersConfig>({
    level: [],
    state: [],
    notify: [],
    monitor_objects: [],
  });
  const [activeTab, setActiveTab] = useState<string>('activeAlarms');
  const [chartData, setChartData] = useState<Record<string, any>[]>([]);
  const [pageLoading, setPageLoading] = useState<boolean>(false);
  const [objects, setObjects] = useState<ObectItem[]>([]);
  const [groupObjects, setGroupObjects] = useState<ObectItem[]>([]);
  const [metrics, setMetrics] = useState<MetricItem[]>([]);

  const tabs: TabItem[] = [
    {
      label: t('monitor.events.activeAlarms'),
      key: 'activeAlarms',
    },
    {
      label: t('monitor.events.historicalAlarms'),
      key: 'historicalAlarms',
    },
  ];
  const columns: ColumnItem[] = [
    {
      title: t('monitor.events.level'),
      dataIndex: 'level',
      key: 'level',
      width: 100,
      render: (_, { level }) => (
        <Tag icon={<AlertOutlined />} color={LEVEL_MAP[level] as string}>
          {LEVEL_LIST.find((item) => item.value === level)?.label || '--'}
        </Tag>
      ),
    },
    {
      title: t('common.time'),
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 160,
      sorter: (a: any, b: any) => a.id - b.id,
      render: (_, { updated_at }) => (
        <>{updated_at ? convertToLocalizedTime(updated_at) : '--'}</>
      ),
    },
    {
      title: t('monitor.events.alertName'),
      dataIndex: 'content',
      key: 'content',
      width: 120,
    },
    {
      title: t('monitor.asset'),
      dataIndex: 'monitor_instance_name',
      key: 'monitor_instance_name',
      width: 200,
    },
    {
      title: t('monitor.events.assetType'),
      dataIndex: 'assetType',
      key: 'assetType',
      width: 120,
      render: (_, record) => <>{showObjName(record)}</>,
    },
    {
      title: t('monitor.events.state'),
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (_, { status }) => (
        <Tag color={status === 'new' ? 'blue' : 'var(--color-text-4)'}>
          {STATE_MAP[status]}
        </Tag>
      ),
    },
    {
      title: t('monitor.events.notify'),
      dataIndex: 'notify',
      key: 'notify',
      width: 100,
      render: (_, record) => (
        <>
          {t(
            `monitor.events.${
              record.policy?.notice ? 'notified' : 'unnotified'
            }`
          )}
        </>
      ),
    },
    {
      title: t('common.operator'),
      dataIndex: 'operator',
      key: 'operator',
      width: 100,
      render: (_, { operator }) => {
        return operator ? (
          <div className="column-user" title={operator}>
            <span
              className="user-avatar"
              style={{ background: getRandomColor() }}
            >
              {operator.slice(0, 1).toLocaleUpperCase()}
            </span>
            <span className="user-name">{operator}</span>
          </div>
        ) : (
          <>--</>
        );
      },
    },
    {
      title: t('common.action'),
      key: 'action',
      dataIndex: 'action',
      width: 120,
      fixed: 'right',
      render: (_, record) => (
        <>
          <Button
            className="mr-[10px]"
            type="link"
            onClick={() => openAlertDetail(record)}
          >
            {t('common.detail')}
          </Button>
          <Permission requiredPermissions={['Operate']}>
            <Button
              type="link"
              disabled={record.status !== 'new'}
              onClick={() => showAlertCloseConfirm(record)}
            >
              {t('common.close')}
            </Button>
          </Permission>
        </>
      ),
    },
  ];

  useEffect(() => {
    if (!frequence) {
      clearTimer();
      return;
    }
    timerRef.current = setInterval(() => {
      getAssetInsts('timer');
      getChartData('timer');
    }, frequence);
    return () => {
      clearTimer();
    };
  }, [
    frequence,
    timeRange,
    activeTab,
    filters.level,
    filters.state,
    filters.monitor_objects,
    pagination.current,
    pagination.pageSize,
  ]);

  useEffect(() => {
    if (isLoading) return;
    getAssetInsts('refresh');
  }, [
    isLoading,
    timeRange,
    activeTab,
    filters.level,
    filters.state,
    filters.monitor_objects,
    pagination.current,
    pagination.pageSize,
  ]);

  useEffect(() => {
    if (isLoading) return;
    getChartData('refresh');
  }, [
    isLoading,
    timeRange,
    filters.state,
    activeTab,
    filters.level,
    filters.monitor_objects,
  ]);

  useEffect(() => {
    if (isLoading) return;
    getInitData();
  }, [isLoading]);

  const changeTab = (val: string) => {
    setActiveTab(val);
  };

  const getInitData = () => {
    setPageLoading(true);
    Promise.all([getMetrics(), getObjects()]).finally(() => {
      setPageLoading(false);
    });
  };

  const getMetrics = async () => {
    const data = await get(`/monitor/api/metrics/`);
    setMetrics(data);
  };

  const getObjects = async () => {
    const data: ObectItem[] = await get('/monitor/api/monitor_object/', {
      params: {
        add_policy_count: true,
      },
    });
    const groupedData = data.reduce((acc, item) => {
      if (!acc[item.type]) {
        acc[item.type] = {
          label: item.display_type,
          title: item.type,
          options: [],
        };
      }
      acc[item.type].options.push({
        label: item.display_name,
        value: item.id,
      });
      return acc;
    }, {} as Record<string, any>);
    setGroupObjects(Object.values(groupedData));
    setObjects(data);
  };

  const showAlertCloseConfirm = (row: TableDataItem) => {
    confirm({
      title: t('monitor.events.closeTitle'),
      content: t('monitor.events.closeContent'),
      centered: true,
      onOk() {
        return new Promise(async (resolve) => {
          try {
            await patch(`/monitor/api/monitor_alert/${row.id}/`, {
              status: 'closed',
            });
            message.success(t('monitor.events.successfullyClosed'));
            onRefresh();
          } finally {
            resolve(true);
          }
        });
      },
    });
  };

  const clearTimer = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
  };

  const getParams = () => {
    const params = {
      status_in: filters.state,
      level_in: filters.level.join(','),
      monitor_objects: filters.monitor_objects.join(','),
      content: searchText,
      page: pagination.current,
      page_size: pagination.pageSize,
      created_at_after: dayjs(timeRange[0]).toISOString(),
      created_at_before: dayjs(timeRange[1]).toISOString(),
    };
    return params;
  };

  const showObjName = (row: TableDataItem) => {
    return (
      objects.find((item) => item.id === row.policy?.monitor_object)
        ?.display_name || '--'
    );
  };

  const handleTableChange = (pagination: any) => {
    setPagination(pagination);
  };

  const getAssetInsts = async (type: string, text?: string) => {
    const params: any = getParams();
    if (text) {
      params.content = '';
    }
    if (activeTab === 'activeAlarms') {
      params.created_at_before = '';
      params.created_at_after = '';
      if (params.status_in.length && !params.status_in.includes('new')) {
        setTableData([]);
        setPagination((pre) => ({
          ...pre,
          total: 0,
        }));
        return;
      }
      params.status_in = 'new';
    } else {
      if (params.status_in.length === 1 && params.status_in[0] === 'new') {
        setTableData([]);
        setPagination((pre) => ({
          ...pre,
          total: 0,
        }));
        return;
      }
      params.status_in =
        params.status_in.filter((item: any) => item !== 'new').join(',') ||
        'recovered,closed';
    }
    try {
      setTableLoading(type !== 'timer');
      const data = await get('/monitor/api/monitor_alert/', { params });
      setTableData(data.results);
      setPagination((pre) => ({
        ...pre,
        total: data.count,
      }));
    } finally {
      setTableLoading(false);
    }
  };

  const getChartData = async (type: string) => {
    const params = getParams();
    const chartParams = deepClone(params);
    delete chartParams.page;
    delete chartParams.page_size;
    chartParams.content = '';
    chartParams.type = 'count';
    if (activeTab === 'activeAlarms') {
      chartParams.created_at_before = '';
      chartParams.created_at_after = '';
      if (
        chartParams.status_in.length &&
        !chartParams.status_in.includes('new')
      ) {
        setChartData([]);
        return;
      }
      chartParams.status_in = 'new';
    } else {
      if (
        chartParams.status_in.length === 1 &&
        chartParams.status_in[0] === 'new'
      ) {
        setChartData([]);
        return;
      }
      chartParams.status_in =
        chartParams.status_in.filter((item: any) => item !== 'new').join(',') ||
        'recovered,closed';
    }
    try {
      setChartLoading(type !== 'timer');
      const data = await get('/monitor/api/monitor_alert/', {
        params: chartParams,
      });
      setChartData(
        processDataForStackedBarChart(
          (data.results || []).filter((item: TableDataItem) => !!item.level)
        ) as any
      );
    } finally {
      setChartLoading(false);
    }
  };

  const onFrequenceChange = (val: number) => {
    setFrequence(val);
  };

  const onRefresh = () => {
    getAssetInsts('refresh');
    getChartData('refresh');
  };

  const openAlertDetail = (row: TableDataItem) => {
    const metricInfo =
      metrics.find(
        (item) => item.id === row.policy?.query_condition?.metric_id
      ) || {};
    detailRef.current?.showModal({
      title: t('monitor.events.alertDetail'),
      type: 'add',
      form: {
        ...row,
        metric: metricInfo,
        alertTitle: showObjName(row),
        alertValue: getEnumValueUnit(metricInfo as MetricItem, row.value),
      },
    });
  };

  const onTimeChange = (val: number[]) => {
    setTimeRange(val);
  };

  const processDataForStackedBarChart = (
    data: TableDataItem,
    desiredSegments = 12
  ) => {
    if (!data?.length) return [];
    // 1. 找到最早时间和最晚时间
    const timestamps = data.map((item: TableDataItem) =>
      dayjs(item.created_at)
    );
    const minTime = timestamps.reduce(
      (min: Dayjs, curr: Dayjs) => (curr.isBefore(min) ? curr : min),
      timestamps[0]
    ); // 最早时间
    const maxTime = timestamps.reduce(
      (max: Dayjs, curr: Dayjs) => (curr.isAfter(max) ? curr : max),
      timestamps[0]
    ); // 最晚时间
    // 2. 计算时间跨度（以分钟为单位）
    const totalMinutes = maxTime.diff(minTime, 'minute');
    // 3. 动态计算时间区间（每段的分钟数）
    const intervalMinutes = Math.max(
      Math.ceil(totalMinutes / desiredSegments),
      1
    ); // 确保 intervalMinutes 至少为 1
    // 4. 按动态时间区间划分数据
    const groupedData = data.reduce(
      (acc: TableDataItem, curr: TableDataItem) => {
        // 根据 created_at 时间戳，计算所属时间区间
        const timestamp = dayjs(curr.created_at).startOf('minute'); // 转为分钟级别时间戳
        const roundedTime = convertToLocalizedTime(
          minTime.add(
            Math.floor(timestamp.diff(minTime, 'minute') / intervalMinutes) *
              intervalMinutes,
            'minute'
          )
        );
        if (!acc[roundedTime]) {
          acc[roundedTime] = {
            time: roundedTime,
            critical: 0,
            error: 0,
            warning: 0,
          };
        }
        // 根据 level 统计数量
        if (curr.level === 'critical') {
          acc[roundedTime].critical += 1;
        } else if (curr.level === 'error') {
          acc[roundedTime].error += 1;
        } else if (curr.level === 'warning') {
          acc[roundedTime].warning += 1;
        }
        return acc;
      },
      {}
    );
    // 5. 将分组后的对象转为数组
    return Object.values(groupedData).sort(
      (a: any, b: any) => dayjs(b.time).valueOf() - dayjs(a.time).valueOf()
    );
  };

  const onFilterChange = (
    checkedValues: string[],
    field: keyof FiltersConfig
  ) => {
    setFilters((pre) => {
      pre[field] = checkedValues;
      return {
        ...pre,
      };
    });
  };

  const enterText = () => {
    getAssetInsts('refresh');
  };

  const clearText = () => {
    setSearchText('');
    getAssetInsts('refresh', 'clear');
  };

  return (
    <div className="w-full">
      <Spin spinning={pageLoading} className="w-full">
        <div className={alertStyle.alert}>
          <div className={alertStyle.filters}>
            <h3 className="font-[800] mb-[15px] text-[15px]">
              {t('monitor.events.filterItems')}
            </h3>
            <div className="mb-[15px]">
              <Collapse title={t('monitor.events.level')}>
                <Checkbox.Group
                  className="ml-[20px]"
                  value={filters.level}
                  onChange={(checkeds) => onFilterChange(checkeds, 'level')}
                >
                  <Space direction="vertical">
                    <Checkbox value="critical">
                      <div className={alertStyle.level}>
                        {t('monitor.events.critical')}
                      </div>
                    </Checkbox>
                    <Checkbox value="error">
                      <div
                        className={alertStyle.level}
                        style={{
                          borderLeft: `4px solid ${LEVEL_MAP.error}`,
                        }}
                      >
                        {t('monitor.events.error')}
                      </div>
                    </Checkbox>
                    <Checkbox value="warning">
                      <div
                        className={alertStyle.level}
                        style={{
                          borderLeft: `4px solid ${LEVEL_MAP.warning}`,
                        }}
                      >
                        {t('monitor.events.warning')}
                      </div>
                    </Checkbox>
                  </Space>
                </Checkbox.Group>
              </Collapse>
            </div>
            <div className="mb-[15px]">
              <Collapse title={t('monitor.events.state')}>
                <Checkbox.Group
                  value={filters.state}
                  className="ml-[20px]"
                  onChange={(checkeds) => onFilterChange(checkeds, 'state')}
                >
                  <Space direction="vertical">
                    <Checkbox value="new">{t('monitor.events.new')}</Checkbox>
                    <Checkbox value="recovered">
                      {t('monitor.events.recovery')}
                    </Checkbox>
                    <Checkbox value="closed">
                      {t('monitor.events.closed')}
                    </Checkbox>
                  </Space>
                </Checkbox.Group>
              </Collapse>
            </div>
            <div>
              <Collapse title={t('monitor.events.assetType')}>
                <Checkbox.Group
                  className="ml-[20px]"
                  value={filters.monitor_objects}
                  onChange={(checkeds) =>
                    onFilterChange(checkeds, 'monitor_objects')
                  }
                >
                  <Space direction="vertical">
                    {groupObjects.map((item, index) => {
                      return (
                        <Collapse
                          key={index}
                          title={item.label || '--'}
                          className={alertStyle.assetType}
                        >
                          {(item.options || []).map(
                            (optionItem, optionIndex) => (
                              <Checkbox
                                key={optionIndex}
                                value={optionItem.value}
                              >
                                <span
                                  className="inline-block w-[110px] hide-text align-middle"
                                  title={optionItem.label}
                                >
                                  {optionItem.label}
                                </span>
                              </Checkbox>
                            )
                          )}
                        </Collapse>
                      );
                    })}
                  </Space>
                </Checkbox.Group>
              </Collapse>
            </div>
          </div>
          <div>
            <Spin spinning={chartLoading}>
              <div className={alertStyle.chartWrapper}>
                <div className="flex items-center justify-between mb-[2px]">
                  <div className="text-[14px] ml-[10px] relative">
                    {t('monitor.events.distributionMap')}
                    <Tooltip
                      placement="top"
                      title={t(`monitor.events.${activeTab}MapTips`)}
                    >
                      <div
                        className="absolute cursor-pointer"
                        style={{
                          top: '-4px',
                          right: '-14px',
                        }}
                      >
                        <Icon
                          type="a-shuoming2"
                          className="text-[14px] text-[var(--color-text-3)]"
                        />
                      </div>
                    </Tooltip>
                  </div>
                  <TimeSelector
                    defaultValue={timeDefaultValue}
                    onlyRefresh={activeTab === 'activeAlarms'}
                    onChange={(value) => onTimeChange(value)}
                    onFrequenceChange={onFrequenceChange}
                    onRefresh={onRefresh}
                  />
                </div>
                <div className={alertStyle.chart}>
                  <StackedBarChart data={chartData} colors={LEVEL_MAP as any} />
                </div>
              </div>
            </Spin>
            <div className={alertStyle.table}>
              <Tabs activeKey={activeTab} items={tabs} onChange={changeTab} />
              <div className="flex justify-between mb-[10px]">
                <Input
                  allowClear
                  className="w-[350px]"
                  placeholder={t('common.searchPlaceHolder')}
                  onChange={(e) => setSearchText(e.target.value)}
                  onPressEnter={enterText}
                  onClear={clearText}
                />
              </div>
              <CustomTable
                scroll={{ y: 'calc(100vh - 540px)', x: 'calc(100vw - 320px)' }}
                columns={columns}
                dataSource={tableData}
                pagination={pagination}
                loading={tableLoading}
                rowKey="id"
                onChange={handleTableChange}
              />
            </div>
          </div>
        </div>
      </Spin>
      <AlertDetail
        ref={detailRef}
        objects={objects}
        metrics={metrics}
        userList={userList}
        onSuccess={() => getAssetInsts('refresh')}
      />
    </div>
  );
};

export default Alert;
