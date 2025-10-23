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
import { getRandomColor, getRecentTimeRange } from '@/app/log/utils/common';
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
} from '@/app/log/types';
import { ObjectItem } from '@/app/log/types/event';
import { AlertOutlined } from '@ant-design/icons';
import { FiltersConfig } from '@/app/log/types/event';
import CustomTable from '@/components/custom-table';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import TimeSelector from '@/components/time-selector';
import Permission from '@/components/permission';
import StackedBarChart from '@/app/log/components/charts/stackedBarChart';
import AlertDetail from './alertDetail';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useAlarmTabs } from '@/app/log/hooks/event';
import dayjs from 'dayjs';
import { useCommon } from '@/app/log/context/common';
import alertStyle from './index.module.scss';
import { LEVEL_MAP } from '@/app/log/constants';
import { useLevelList, useStateMap } from '@/app/log/hooks/event';
import useLogEventApi from '@/app/log/api/event';
import useLogIntegrationApi from '@/app/log/api/integration';
import TreeSelector from '@/app/log/components/tree-selector';
import { cloneDeep } from 'lodash';
const { Search } = Input;
const { Option } = Select;

const Alert: React.FC = () => {
  const { isLoading } = useApiClient();
  const { getLogAlert, patchLogAlert, getLogAlertStats } = useLogEventApi();
  const { getCollectTypes } = useLogIntegrationApi();
  const { t } = useTranslation();
  const STATE_MAP = useStateMap();
  const LEVEL_LIST = useLevelList();
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
  const [treeLoading, setTreeLoading] = useState<boolean>(false);
  const [objects, setObjects] = useState<ObjectItem[]>([]);
  const [treeData, setTreeData] = useState<TreeItem[]>([]);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const [objectId, setObjectId] = useState<React.Key>('');

  const columns: ColumnItem[] = [
    {
      title: t('log.event.level'),
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
      title: t('log.event.alertName'),
      dataIndex: 'alert_name',
      key: 'alert_name',
      width: 120,
    },
    {
      title: t('log.integration.collectType'),
      dataIndex: 'collect_type_name',
      key: 'collect_type_name',
      width: 120,
    },
    {
      title: t('log.event.alertType'),
      dataIndex: 'alert_type',
      key: 'alert_type',
      width: 140,
      render: (_, { alert_type }) => (
        <EllipsisWithTooltip
          className="w-full overflow-hidden text-ellipsis whitespace-nowrap"
          text={
            alert_type === 'keyword'
              ? t('log.event.keywordAlert')
              : t('log.event.aggregationAlert')
          }
        />
      ),
    },
    {
      title: t('log.event.state'),
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
      title: t('log.event.notify'),
      dataIndex: 'notify',
      key: 'notify',
      width: 100,
      render: (_, record) => (
        <>{t(`log.event.${record.notice ? 'notified' : 'unnotified'}`)}</>
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
              title={t('log.event.closeTitle')}
              description={t('log.event.closeContent')}
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
    clearData();
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
    try {
      setTreeLoading(true);
      const data: ObjectItem[] = await getCollectTypes();
      setObjects(data);
      setTreeData(getTreeData(data));
    } finally {
      setTreeLoading(false);
    }
  };

  const getTreeData = (data: ObjectItem[]): TreeItem[] => {
    const groupedData = data.reduce((acc, item) => {
      if (!acc[item.collector]) {
        acc[item.collector] = {
          title: item.collector || '--',
          key: item.collector,
          children: [],
        };
      }
      acc[item.collector].children.push({
        title: item.name || '--',
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
      await patchLogAlert({
        id,
        status: 'closed',
      });
      message.success(t('log.event.successfullyClosed'));
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
      status: isActive ? 'new' : 'closed',
      levels: filtersMap.level.join(','),
      collect_type: objectId === 'all' ? '' : objectId,
      content: searchText || '',
      page: pagination.current,
      page_size: pagination.pageSize,
      end_event_time: isActive ? '' : dayjs(recentTimeRange[0]).toISOString(),
      start_event_time: isActive ? '' : dayjs(recentTimeRange[1]).toISOString(),
    };
    return params;
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
      const data = await getLogAlert(params);
      setTableData(data.items || []);
      setPagination((pre) => ({
        ...pre,
        total: data.count,
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
    try {
      setChartLoading(type !== 'timer');
      const data = await getLogAlertStats(chartParams);
      const chartList = (data.time_series || []).map((item: TableDataItem) => {
        const levels = {
          critical: 0,
          warning: 0,
          error: 0,
        };
        return {
          ...Object.assign(levels, item.levels),
          time: convertToLocalizedTime(item.time_start),
        };
      });
      setChartData(chartList);
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
      title: t('log.event.alertDetail'),
      type: 'add',
      form: row,
    });
  };

  const onTimeChange = (val: number[], originValue: number | null) => {
    setTimeValues({
      timeRange: val,
      originValue,
    });
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

  const clearData = () => {
    setTableData([]);
    setChartData([]);
  };

  const handleObjectChange = async (id: string) => {
    clearData();
    setObjectId(id);
  };

  return (
    <div className="w-full">
      <div className={alertStyle.alert}>
        <TreeSelector
          loading={treeLoading}
          data={treeData}
          showAllMenu
          defaultSelectedKey="all"
          onNodeSelect={handleObjectChange}
        />
        <div className={alertStyle.alarmList}>
          <Tabs activeKey={activeTab} items={tabs} onChange={changeTab} />
          <div className={alertStyle.searchCondition}>
            <div className="mb-[10px]">{t('log.search.searchCriteria')}</div>
            <div className={alertStyle.condition}>
              <ul className="flex">
                <li className="mr-[8px]">
                  <span className="mr-[8px] text-[12px] text-[var(--color-text-3)]">
                    {t('log.event.level')}
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
                  {t('log.event.distributionMap')}
                  <Tooltip
                    placement="top"
                    title={t(`log.event.${activeTab}MapTips`)}
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
      <AlertDetail
        ref={detailRef}
        objects={objects}
        userList={userList}
        onSuccess={() => getAssetInsts('refresh')}
      />
    </div>
  );
};

export default Alert;
