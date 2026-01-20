'use client';

import React, { useEffect, useState, useRef, useMemo, useCallback } from 'react';
import Icon from '@/components/icon';
import useApiClient from '@/utils/request';
import dayjs from 'dayjs';
import TimeSelector from '@/components/time-selector';
import StackedBarChart from '@/app/alarm/components/stackedBarChart';
import alertStyle from './index.module.scss';
import AlarmFilters from '@/app/alarm/components/alarmFilters';
import AlarmTable from '@/app/alarm/(pages)/alarms/components/alarmTable';
import SearchFilter from '../../components/searchFilter';
import AlarmAction from './components/alarmAction';
import DeclareIncident from './components/declareIncident';
import { SearchFilterCondition } from '@/app/alarm/types/alarms';
import { useAlarmApi } from '@/app/alarm/api/alarms';
import { useTranslation } from '@/utils/i18n';
import { AlarmTableDataItem, FiltersConfig } from '@/app/alarm/types/alarms';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { deepClone } from '@/app/alarm/utils/common';
import { useCommon } from '@/app/alarm/context/common';
import { baseStates, allStates } from '@/app/alarm/constants/alarm';
import { Checkbox, Tabs, Spin, Tooltip, Switch } from 'antd';
import { processDataForStackedBarChart } from '@/app/alarm/utils/alarmChart';
import {
  Pagination,
  TabItem,
  TimeSelectorDefaultValue,
} from '@/app/alarm/types/types';

const getSettings = () => {
  try {
    return JSON.parse(localStorage.getItem('alarmSettings') || '{}');
  } catch {
    return {};
  }
};

const Alert: React.FC = () => {
  const { isLoading } = useApiClient();
  const { t } = useTranslation();
  const { levelList, levelMap } = useCommon();
  const { getAlarmList } = useAlarmApi();
  const { convertToLocalizedTime } = useLocalizedTime();
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const beginTime: number = dayjs().subtract(10080, 'minute').valueOf();
  const lastTime: number = dayjs().valueOf();
  const [searchCondition, setSearchCondition] =
    useState<SearchFilterCondition | null>(null);
  const [tableLoading, setTableLoading] = useState<boolean>(false);
  const [chartLoading, setChartLoading] = useState<boolean>(false);
  const [tableData, setTableData] = useState<AlarmTableDataItem[]>([]);
  const [frequency, setFrequency] = useState<number>(0);
  const [timeRange, setTimeRange] = useState<number[]>([beginTime, lastTime]);
  const [activeTab, setActiveTab] = useState<string>('activeAlarms');
  const [chartData, setChartData] = useState<Record<string, any>[]>([]);
  const [myAlarms, setMyAlarms] = useState<boolean>(() => {
    const { myAlarms } = getSettings();
    return myAlarms !== undefined ? myAlarms : true;
  });
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);

  const saveSettings = (
    settings: Partial<{
      pageSize: number;
      showChart: boolean;
      myAlarms: boolean;
      stateFilters: string[];
    }>
  ) => {
    localStorage.setItem(
      'alarmSettings',
      JSON.stringify({ ...getSettings(), ...settings })
    );
  };

  const [pagination, setPagination] = useState<Pagination>(() => {
    const { pageSize } = getSettings();
    return {
      current: 1,
      total: 0,
      pageSize: pageSize || 20,
    };
  });

  const tabList: TabItem[] = useMemo(() => [
    {
      label: t('alarms.activeAlarms'),
      key: 'activeAlarms',
    },
    {
      label: t('alarms.historicalAlarms'),
      key: 'historicalAlarms',
    },
  ], [t]);

  const timeDefaultValue =
    (useRef<TimeSelectorDefaultValue>({
      selectValue: 10080,
      rangePickerVaule: null,
    })?.current || {}) as any;

  const [filters, setFilters] = useState<FiltersConfig>(() => {
    const { stateFilters } = getSettings();
    return {
      level: [],
      state: stateFilters || ['pending', 'processing'],
      alarm_source: [],
    };
  });

  const [showChart, setShowChart] = useState<boolean>(() => {
    const { showChart } = getSettings();
    return showChart !== undefined ? showChart : true;
  });

  const tableScrollY = showChart
    ? 'calc(100vh - 500px)'
    : 'calc(100vh - 400px)';

  const isActiveAlarms = activeTab === 'activeAlarms';

  const stateOptions = useMemo(() => (isActiveAlarms ? baseStates : allStates).map((val) => ({
    value: val,
    label: t(`alarms.${val}`),
  })), [isActiveAlarms, t]);

  useEffect(() => {
    return () => {
      clearTimer();
      abortControllerRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (!frequency) {
      clearTimer();
      return;
    }
    timerRef.current = setInterval(() => {
      getAlarmTableData('timer');
      showChart && getChartData('timer');
    }, frequency);
    return () => {
      clearTimer();
    };
  }, [
    frequency,
    timeRange,
    activeTab,
    showChart,
    filters.level,
    filters.state,
    filters.alarm_source,
    pagination.current,
    pagination.pageSize,
    myAlarms,
  ]);

  useEffect(() => {
    if (isLoading) return;
    getAlarmTableData('refresh');
  }, [
    isLoading,
    timeRange,
    activeTab,
    filters.level,
    filters.state,
    filters.alarm_source,
    pagination.current,
    pagination.pageSize,
    myAlarms,
  ]);

  useEffect(() => {
    if (isLoading) return;
    showChart && getChartData('refresh');
  }, [
    isLoading,
    timeRange,
    activeTab,
    filters.state,
    filters.level,
    filters.alarm_source,
  ]);

  const changeTab = useCallback((val: string) => {
    setPagination((prev) => ({ ...prev, current: 1 }));
    setChartData([]);
    setActiveTab(val);
  }, []);

  const clearTimer = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
  };

  const getParams = (condition = null) => {
    const conditionValue = condition || searchCondition;
    const params: any = {
      status: filters.state.join(','),
      level: filters.level.join(','),
      source_name: filters.alarm_source.join(','),
      page: pagination.current,
      page_size: pagination.pageSize,
      created_at_after: dayjs(timeRange[0]).toISOString(),
      created_at_before: dayjs(timeRange[1]).toISOString(),
      activate: isActiveAlarms ? 1 : '',
      my_alert: isActiveAlarms ? (myAlarms ? 1 : '') : undefined,
      has_incident: '',
      [conditionValue?.field as string]: conditionValue?.value,
    };
    return params;
  };

  const handleTableChange = useCallback((pag: any) => {
    saveSettings({ pageSize: pag.pageSize });
    setPagination(pag);
  }, []);

  const getAlarmTableData = async (type: string, condition?: any) => {
    const params: any = getParams(condition);
    try {
      setTableLoading(type !== 'timer');
      if (activeTab === 'activeAlarms') {
        params.created_at_after = '';
        params.created_at_before = '';
      }
      const data = await getAlarmList(params);
      setTableData(data.items);
      setPagination((pre) => ({
        ...pre,
        total: data.count,
      }));
    } finally {
      setTableLoading(false);
    }
  };

  const lastChartParamsRef = useRef<string>('');

  const getChartData = async (type: string) => {
    const params = getParams();
    const chartParams = deepClone(params);
    delete chartParams.page;
    delete chartParams.page_size;
    chartParams.search = '';
    if (activeTab === 'activeAlarms') {
      chartParams.created_at_after = '';
      chartParams.created_at_before = '';
    }
    // 参数序列化对比，若无变化则跳过
    const key = JSON.stringify(chartParams);
    if (type === 'toggle' && key === lastChartParamsRef.current) {
      return;
    }
    lastChartParamsRef.current = key;

    try {
      setChartLoading(type !== 'timer');
      const data = await getAlarmList(chartParams);
      setChartData(
        processDataForStackedBarChart(
          (data || []).filter((item: AlarmTableDataItem) => !!item.level),
          levelList,
          convertToLocalizedTime
        ) as any
      );
    } finally {
      setChartLoading(false);
    }
  };

  const onFrequencyChange = useCallback((val: number) => {
    setFrequency(val);
  }, []);

  const onRefresh = () => {
    setSelectedRowKeys([]);
    getAlarmTableData('refresh');
    showChart && getChartData('refresh');
  };

  const onTimeChange = useCallback((val: number[]) => {
    setTimeRange(val);
  }, []);

  const onFilterChange = useCallback((
    checkedValues: string[],
    field: keyof FiltersConfig
  ) => {
    setFilters((prev) => ({
      ...prev,
      [field]: checkedValues,
    }));

    if (field === 'state') {
      saveSettings({ stateFilters: checkedValues });
    }
  }, []);

  const clearFilters = useCallback((field: keyof FiltersConfig) => {
    setFilters((prev: any) => ({ ...prev, [field]: [] }));
  }, []);

  const onFilterSearch = (condition: SearchFilterCondition) => {
    setSearchCondition(condition);
    setPagination((prev) => ({ ...prev, current: 1 }));
    getAlarmTableData('search', condition);
  };

  const alarmAttrList = useMemo(() => [
    {
      attr_id: 'alert_id',
      attr_name: t('alarms.alertId'),
      attr_type: 'str',
      option: [],
    },
    {
      attr_id: 'title',
      attr_name: t('alarms.alertName'),
      attr_type: 'str',
      option: [],
    },
    {
      attr_id: 'content',
      attr_name: t('alarms.alertContent'),
      attr_type: 'str',
      option: [],
    },
  ], [t]);

  const selectedRowData = useMemo(() =>
    tableData?.filter((item) => selectedRowKeys.includes(item.id)) || [],
  [tableData, selectedRowKeys]
  );

  return (
    <div className="w-full">
      <div className={alertStyle.alert}>
        <AlarmFilters
          filters={filters}
          onFilterChange={onFilterChange}
          clearFilters={clearFilters}
          stateOptions={stateOptions}
        />
        <div className={alertStyle.alertContent}>
          <Spin spinning={chartLoading}>
            <div className={alertStyle.chartWrapper}>
              <div className="flex items-center justify-between pb-[12px]">
                <div className="flex items-center text-[14px] ml-[10px] relative">
                  {t('alarms.distributionMap')}
                  <Tooltip
                    placement="top"
                    title={t(`alarms.${activeTab}MapTips`)}
                  >
                    <div
                      className="cursor-pointer"
                      style={{
                        transform: 'translateY(-6px)',
                      }}
                    >
                      <Icon
                        type="a-shuoming2"
                        className="text-[14px] text-[var(--color-text-3)]"
                      />
                    </div>
                  </Tooltip>
                  <Switch
                    size="small"
                    checked={showChart}
                    onChange={(checked) => {
                      saveSettings({ showChart: checked });
                      setShowChart(checked);
                      if (checked) {
                        getChartData('toggle');
                      }
                    }}
                    className="ml-2"
                  />
                </div>
                <TimeSelector
                  defaultValue={timeDefaultValue}
                  onlyRefresh={isActiveAlarms}
                  onChange={(value) => onTimeChange(value)}
                  onFrequenceChange={onFrequencyChange}
                  onRefresh={onRefresh}
                />
              </div>
              {showChart && (
                <div className={alertStyle.chart}>
                  <StackedBarChart data={chartData} colors={levelMap as any} />
                </div>
              )}
            </div>
          </Spin>
          <div className={alertStyle.table}>
            <Tabs activeKey={activeTab} items={tabList} onChange={changeTab} />
            <div className="flex items-center justify-between mb-[16px] min-w-[900px]">
              <div className="flex items-center space-x-4">
                <SearchFilter
                  attrList={alarmAttrList}
                  onSearch={onFilterSearch}
                />
                {isActiveAlarms && (
                  <Checkbox
                    className="ml-2"
                    checked={myAlarms}
                    onChange={(e) => {
                      const checked = e.target.checked;
                      setMyAlarms(checked);
                      saveSettings({ myAlarms: checked });
                    }}
                  >
                    {t('alarms.myAlarms')}
                  </Checkbox>
                )}
              </div>

              <div className="flex items-center space-x-4">
                <DeclareIncident
                  rowData={selectedRowData}
                  onSuccess={onRefresh}
                />
                <AlarmAction
                  rowData={selectedRowData}
                  displayMode="dropdown"
                  showAll
                  onAction={onRefresh}
                />
              </div>
            </div>
            <AlarmTable
              dataSource={tableData}
              pagination={pagination}
              loading={tableLoading}
              tableScrollY={tableScrollY}
              selectedRowKeys={selectedRowKeys}
              onSelectionChange={setSelectedRowKeys}
              onChange={handleTableChange}
              onRefresh={onRefresh}
            />
          </div>
        </div>
      </div>
    </div>
  );
};

export default Alert;
