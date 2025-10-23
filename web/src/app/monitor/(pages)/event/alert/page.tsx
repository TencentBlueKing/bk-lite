'use client';
import React, { useEffect, useState, useRef, useMemo } from 'react';
import {
  Input,
  Button,
  Select,
  Tag,
  message,
  Tabs,
  Spin,
  Tooltip,
  Popconfirm,
} from 'antd';
import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';
import Icon from '@/components/icon';
import { getRandomColor, getRecentTimeRange } from '@/app/monitor/utils/common';
import {
  ColumnItem,
  ModalRef,
  Pagination,
  TableDataItem,
  UserItem,
  TabItem,
  TimeSelectorDefaultValue,
  TimeValuesProps,
  TreeItem,
  ObjectItem,
} from '@/app/monitor/types';
import { AlertOutlined } from '@ant-design/icons';
import { FiltersConfig } from '@/app/monitor/types/event';
import CustomTable from '@/components/custom-table';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import TimeSelector from '@/components/time-selector';
import Permission from '@/components/permission';
import StackedBarChart from '@/app/monitor/components/charts/stackedBarChart';
import AlertDetail from './alertDetail';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useAlarmTabs, useStateList } from '@/app/monitor/hooks/event';
import { useLevelList, useStateMap } from '@/app/monitor/hooks';
import dayjs, { Dayjs } from 'dayjs';
import { useCommon } from '@/app/monitor/context/common';
import alertStyle from './index.module.scss';
import { LEVEL_MAP } from '@/app/monitor/constants';
import useMonitorApi from '@/app/monitor/api/index';
import TreeSelector from '@/app/monitor/components/treeSelector';
import { cloneDeep } from 'lodash';
const { Search } = Input;
const { Option } = Select;

const Alert: React.FC = () => {
  const { isLoading } = useApiClient();
  const { getMonitorAlert, getMonitorObject, patchMonitorAlert } =
    useMonitorApi();
  const { t } = useTranslation();
  const STATE_MAP = useStateMap();
  const LEVEL_LIST = useLevelList();
  const stateList = useStateList();
  const tabs: TabItem[] = useAlarmTabs();
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
  const [timeValues, setTimeValues] = useState<TimeValuesProps>({
    timeRange: [],
    originValue: 10080,
  });
  const timeDefaultValue =
    useRef<TimeSelectorDefaultValue>({
      selectValue: 10080,
      rangePickerVaule: null,
    })?.current || {};
  const [filters, setFilters] = useState<FiltersConfig>({
    level: [],
    state: [],
  });
  const [activeTab, setActiveTab] = useState<string>('activeAlarms');
  const [chartData, setChartData] = useState<Record<string, any>[]>([]);
  const [pageLoading, setPageLoading] = useState<boolean>(false);
  const [objects, setObjects] = useState<ObjectItem[]>([]);
  const [treeData, setTreeData] = useState<TreeItem[]>([]);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const [objectId, setObjectId] = useState<React.Key>('');

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
            <span className="user-name">
              <EllipsisWithTooltip
                className="w-full overflow-hidden text-ellipsis whitespace-nowrap"
                text={operator}
              />
            </span>
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
          <Permission
            requiredPermissions={['Operate']}
            instPermissions={record.permission}
          >
            <Popconfirm
              title={t('monitor.events.closeTitle')}
              description={t('monitor.events.closeContent')}
              okText={t('common.confirm')}
              cancelText={t('common.cancel')}
              okButtonProps={{ loading: confirmLoading }}
              onConfirm={() => alertCloseConfirm(record.id)}
            >
              <Button type="link" disabled={record.status !== 'new'}>
                {t('common.close')}
              </Button>
            </Popconfirm>
          </Permission>
        </>
      ),
    },
  ];

  const isActiveAlarm = useMemo(() => {
    return activeTab === 'activeAlarms';
  }, [activeTab]);

  const activeStateList = useMemo(() => {
    const filterArr = isActiveAlarm ? ['new'] : ['recovered', 'closed'];
    return stateList.filter((item) => filterArr.includes(item.value));
  }, [stateList, isActiveAlarm]);

  useEffect(() => {
    if (!frequence) {
      clearTimer();
      return;
    }
    timerRef.current = setInterval(() => {
      if (objectId) {
        getAssetInsts('timer');
        getChartData('timer');
      }
    }, frequence);
    return () => {
      clearTimer();
    };
  }, [
    frequence,
    timeValues,
    objectId,
    searchText,
    pagination.current,
    pagination.pageSize,
  ]);

  useEffect(() => {
    if (isLoading || !objectId) return;
    getAssetInsts('refresh');
  }, [
    isLoading,
    timeValues,
    objectId,
    pagination.current,
    pagination.pageSize,
  ]);

  useEffect(() => {
    if (isLoading || !objectId) return;
    getChartData('refresh');
  }, [isLoading, timeValues, objectId]);

  useEffect(() => {
    if (isLoading) return;
    getObjects();
  }, [isLoading]);

  const changeTab = (val: string) => {
    setActiveTab(val);
    const filtersConfig = {
      level: [],
      state: [],
    };
    setFilters(filtersConfig);
    setSearchText('');
    getAssetInsts('refresh', { tab: val, filtersConfig, text: 'clear' });
    getChartData('refresh', { tab: val, filtersConfig });
  };

  const getObjects = async () => {
    setPageLoading(true);
    try {
      const data: ObjectItem[] = await getMonitorObject({
        add_policy_count: true,
      });
      setObjects(data);
      const _treeData = getTreeData(cloneDeep(data));
      setTreeData(_treeData);
    } finally {
      setPageLoading(false);
    }
  };

  const getTreeData = (data: ObjectItem[]): TreeItem[] => {
    const groupedData = data.reduce((acc, item) => {
      if (!acc[item.type]) {
        acc[item.type] = {
          title: item.display_type || '--',
          key: item.type,
          children: [],
        };
      }
      acc[item.type].children.push({
        title: item.display_name || '--',
        label: item.name || '--',
        key: item.id,
        children: [],
      });
      return acc;
    }, {} as Record<string, TreeItem>);
    return [
      {
        title: t('common.all'),
        key: 'all',
        children: [],
      },
      ...Object.values(groupedData),
    ];
  };

  const alertCloseConfirm = async (id: string | number) => {
    setConfirmLoading(true);
    try {
      await patchMonitorAlert(id, {
        status: 'closed',
      });
      message.success(t('monitor.events.successfullyClosed'));
      onRefresh();
    } finally {
      setConfirmLoading(false);
    }
  };

  const clearTimer = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
  };

  const getParams = (tab: string, filtersMap: FiltersConfig) => {
    const recentTimeRange = getRecentTimeRange(timeValues);
    const isActive = tab === 'activeAlarms';
    const params = {
      status_in: isActive
        ? 'new'
        : filtersMap.state.join(',') || 'recovered,closed',
      level_in: filtersMap.level.join(','),
      monitor_object_id: objectId === 'all' ? '' : objectId,
      content: searchText || '',
      page: pagination.current,
      page_size: pagination.pageSize,
      created_at_after: isActive ? '' : dayjs(recentTimeRange[0]).toISOString(),
      created_at_before: isActive
        ? ''
        : dayjs(recentTimeRange[1]).toISOString(),
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

  const getAssetInsts = async (
    type: string,
    extra?: {
      text?: string;
      tab?: string;
      filtersConfig?: FiltersConfig;
    }
  ) => {
    const params: any = getParams(
      extra?.tab || activeTab,
      extra?.filtersConfig || filters
    );
    if (extra?.text === 'clear') {
      params.content = '';
    }
    try {
      setTableLoading(type !== 'timer');
      const data = await getMonitorAlert(params);

      setTableData(data.results || []);
      setPagination((pre) => ({
        ...pre,
        total: data.count || 0,
      }));
    } finally {
      setTableLoading(false);
    }
  };

  const getChartData = async (
    type: string,
    extra?: {
      tab?: string;
      filtersConfig?: FiltersConfig;
    }
  ) => {
    const params = getParams(
      extra?.tab || activeTab,
      extra?.filtersConfig || filters
    );
    const chartParams: any = cloneDeep(params);
    delete chartParams.page;
    delete chartParams.page_size;
    chartParams.content = '';
    chartParams.type = 'count';
    try {
      setChartLoading(type !== 'timer');
      const data = await getMonitorAlert(chartParams);
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
    detailRef.current?.showModal({
      title: t('monitor.events.alertDetail'),
      type: 'add',
      form: {
        ...row,
        alertTitle: showObjName(row),
      },
    });
  };

  const onTimeChange = (val: number[], originValue: number | null) => {
    setTimeValues({
      timeRange: val,
      originValue,
    });
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
    const filtersConfig = cloneDeep(filters);
    filtersConfig[field] = checkedValues;
    setFilters(filtersConfig);
    getAssetInsts('refresh', { filtersConfig });
    getChartData('refresh', { filtersConfig });
  };

  const handleSearch = (text: string) => {
    setSearchText(text);
    getAssetInsts('refresh', { text: text || 'clear' });
  };

  const handleObjectChange = async (id: string) => {
    setObjectId(id);
  };

  return (
    <div className="w-full">
      <Spin spinning={pageLoading} className="w-full">
        <div className={alertStyle.alert}>
          <div className={alertStyle.filters}>
            <TreeSelector
              showAllMenu
              data={treeData}
              defaultSelectedKey="all"
              onNodeSelect={handleObjectChange}
            />
          </div>
          <div className={alertStyle.alarmList}>
            <Tabs activeKey={activeTab} items={tabs} onChange={changeTab} />
            <div className={alertStyle.searchCondition}>
              <div className="mb-[10px]">
                {t('monitor.search.searchCriteria')}
              </div>
              <div className={alertStyle.condition}>
                <ul className="flex">
                  <li className="mr-[8px]">
                    <span className="mr-[8px] text-[12px] text-[var(--color-text-3)]">
                      {t('monitor.events.level')}
                    </span>
                    <Select
                      style={{ width: 200 }}
                      dropdownStyle={{ width: 130 }}
                      allowClear
                      mode="multiple"
                      maxTagCount="responsive"
                      value={filters.level}
                      onChange={(val) => onFilterChange(val, 'level')}
                    >
                      {LEVEL_LIST.map((item) => (
                        <Option key={item.value} value={item.value}>
                          <Tag
                            icon={<AlertOutlined />}
                            color={LEVEL_MAP[item.value as string] as string}
                          >
                            {LEVEL_LIST.find((tex) => tex.value === item.value)
                              ?.label || '--'}
                          </Tag>
                        </Option>
                      ))}
                    </Select>
                  </li>
                  <li>
                    <span className="mr-[8px] text-[12px] text-[var(--color-text-3)]">
                      {t('monitor.events.state')}
                    </span>
                    <Select
                      style={{ width: 200 }}
                      allowClear
                      mode="multiple"
                      maxTagCount="responsive"
                      value={filters.state}
                      onChange={(val) => onFilterChange(val, 'state')}
                      options={activeStateList}
                    ></Select>
                  </li>
                </ul>
                <TimeSelector
                  defaultValue={timeDefaultValue}
                  onlyRefresh={isActiveAlarm}
                  onChange={onTimeChange}
                  onFrequenceChange={onFrequenceChange}
                  onRefresh={onRefresh}
                />
              </div>
            </div>
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
                </div>
                <div className={alertStyle.chart}>
                  <StackedBarChart data={chartData} colors={LEVEL_MAP as any} />
                </div>
              </div>
            </Spin>
            <div className={alertStyle.table}>
              <Search
                allowClear
                className="w-[240px] mb-[10px]"
                placeholder={t('common.searchPlaceHolder')}
                value={searchText}
                enterButton
                onChange={(e) => setSearchText(e.target.value)}
                onSearch={handleSearch}
              />
              <CustomTable
                className="w-full"
                scroll={{ y: 'calc(100vh - 630px)', x: 'calc(100vw - 320px)' }}
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
        objectId={objectId}
        objects={objects}
        userList={userList}
        onSuccess={() => getAssetInsts('refresh')}
      />
    </div>
  );
};

export default Alert;
