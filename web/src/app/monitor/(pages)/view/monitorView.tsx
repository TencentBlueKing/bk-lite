'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Spin, Select, Tooltip, Segmented } from 'antd';
import { BellOutlined, SearchOutlined } from '@ant-design/icons';
import TimeSelector from '@/components/time-selector';
import LineChart from '@/app/monitor/components/charts/lineChart';
import Collapse from '@/components/collapse';
import useApiClient from '@/utils/request';
import { TableDataItem, TimeSelectorDefaultValue } from '@/app/monitor/types';
import {
  MetricItem,
  GroupInfo,
  IndexViewItem,
  SearchParams,
  ViewModalProps,
} from '@/app/monitor/types/monitor';
import { useTranslation } from '@/utils/i18n';
import {
  deepClone,
  findUnitNameById,
  mergeViewQueryKeyValues,
  renderChart,
} from '@/app/monitor/utils/common';
import dayjs, { Dayjs } from 'dayjs';
import Icon from '@/components/icon';
import { INIT_VIEW_MODAL_FORM } from '@/app/monitor/constants/monitor';

const MonitorView: React.FC<ViewModalProps> = ({
  monitorObject,
  monitorName,
  plugins,
  form = INIT_VIEW_MODAL_FORM,
}) => {
  const { get, isLoading } = useApiClient();
  const { t } = useTranslation();
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [metricId, setMetricId] = useState<number | null>();
  const beginTime: number = dayjs().subtract(15, 'minute').valueOf();
  const lastTime: number = dayjs().valueOf();
  const [timeRange, setTimeRange] = useState<number[]>([beginTime, lastTime]);
  const [timeDefaultValue, setTimeDefaultValue] =
    useState<TimeSelectorDefaultValue>({
      selectValue: 15,
      rangePickerVaule: null,
    });
  const [frequence, setFrequence] = useState<number>(0);
  const [metricData, setMetricData] = useState<IndexViewItem[]>([]);
  const [originMetricData, setOriginMetricData] = useState<IndexViewItem[]>([]);
  const [expandId, setExpandId] = useState<number>(0);
  const [activeTab, setActiveTab] = useState<string>('');

  useEffect(() => {
    if (isLoading) {
      return;
    }
    if (form?.instance_id_values.length) {
      const _activeTab = plugins[0]?.value || '';
      setActiveTab(_activeTab);
      getInitData(_activeTab);
    }
  }, [isLoading, form]);

  useEffect(() => {
    clearTimer();
    if (frequence > 0) {
      timerRef.current = setInterval(() => {
        handleSearch('timer');
      }, frequence);
    }
    return () => clearTimer();
  }, [frequence, timeRange, metricId, activeTab]);

  useEffect(() => {
    handleSearch('refresh');
  }, [timeRange]);

  const onTabChange = (val: string) => {
    setActiveTab(val);
    setMetricId(null);
    getInitData(val);
  };

  const getInitData = async (tab: string) => {
    const params = {
      monitor_object_id: monitorObject,
      monitor_plugin_id: tab,
    };
    const getGroupList = get(`/monitor/api/metrics_group/`, { params });
    const getMetrics = get('/monitor/api/metrics/', { params });
    setLoading(true);
    try {
      Promise.all([getGroupList, getMetrics])
        .then((res) => {
          const groupData = res[0].map((item: GroupInfo, index: number) => ({
            ...item,
            isLoading: !index,
            child: [],
          }));
          const metricData = res[1];
          metricData.forEach((metric: MetricItem) => {
            const target = groupData.find(
              (item: GroupInfo) => item.id === metric.metric_group
            );
            if (target) {
              target.child.push({
                ...metric,
                viewData: [],
              });
            }
          });
          const _groupData = groupData.filter(
            (item: IndexViewItem) => !!item.child?.length
          );
          setExpandId(_groupData[0]?.id || 0);
          setMetricData(_groupData);
          setOriginMetricData(_groupData);
          fetchViewData(_groupData, _groupData[0]?.id || 0);
        })
        .finally(() => {
          setLoading(false);
        });
    } catch {
      setLoading(false);
    }
  };

  const getParams = (item: MetricItem, ids: string[]) => {
    const params: SearchParams = {
      query: (item.query || '').replace(
        /__\$labels__/g,
        mergeViewQueryKeyValues([
          { keys: item.instance_id_keys || [], values: ids },
        ])
      ),
    };
    const startTime = timeRange.at(0);
    const endTime = timeRange.at(1);
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

  const fetchViewData = async (data: IndexViewItem[], groupId: number) => {
    const metricList = data.find((item) => item.id === groupId)?.child || [];
    const requestQueue = metricList.map((item) =>
      get(`/monitor/api/metrics_instance/query_range/`, {
        params: getParams(item, form?.instance_id_values || []),
      }).then((response) => ({
        id: item.id,
        data: response.data.result || [],
      }))
    );
    try {
      const results = await Promise.all(requestQueue);
      results.forEach((result) => {
        const metricItem = metricList.find((item) => item.id === result.id);
        if (metricItem) {
          const instanceRow = [
            {
              instance_id_values: form.instance_id_values,
              instance_name: form.instance_name,
              instance_id_keys: metricItem?.instance_id_keys,
              dimensions: metricItem?.dimensions || [],
              title: metricItem?.display_name || '--',
            },
          ];
          metricItem.viewData = renderChart(result.data || [], instanceRow);
        }
      });
    } catch (error) {
      console.error('Error fetching view data:', error);
    } finally {
      const _data = deepClone(data).map((item: IndexViewItem) => ({
        ...item,
        isLoading: false,
      }));
      setMetricData(_data);
    }
  };

  const onTimeChange = (val: number[]) => {
    setTimeRange(val);
  };

  const clearTimer = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
  };

  const onFrequenceChange = (val: number) => {
    setFrequence(val);
  };

  const onRefresh = () => {
    handleSearch('refresh');
  };

  const handleSearch = (type?: string) => {
    const _metricData = deepClone(metricData);
    const target = _metricData.find(
      (item: IndexViewItem) => item.id === expandId
    );
    if (type === 'refresh' && target) {
      target.isLoading = true;
    }
    setMetricData(_metricData);
    fetchViewData(_metricData, expandId);
  };

  const handleMetricIdChange = (val: number) => {
    setMetricId(val);
    if (val) {
      const filteredData = originMetricData
        .map((group) => ({
          ...group,
          isLoading: false,
          child: (group?.child || []).filter((item) => item.id === val),
        }))
        .filter((item) => item.child?.find((tex) => tex.id === val));
      const target = filteredData.find((item) =>
        item.child?.find((tex) => tex.id === val)
      );
      if (target) {
        target.isLoading = true;
        const _groupId = target?.id || 0;
        setExpandId(_groupId);
        setMetricData(filteredData);
        fetchViewData(filteredData, _groupId);
      }
    } else {
      getInitData(activeTab);
    }
  };

  const toggleGroup = (expanded: boolean, groupId: number) => {
    if (expanded) {
      const _metricData = deepClone(metricData);
      _metricData.forEach((item: IndexViewItem) => {
        item.isLoading = false;
      });
      const targetIndex = _metricData.findIndex(
        (item: IndexViewItem) => item.id === groupId
      );
      if (targetIndex !== -1) {
        _metricData[targetIndex].isLoading = true;
      }
      setExpandId(groupId);
      setMetricData(_metricData);
      fetchViewData(_metricData, groupId);
    }
  };

  const onXRangeChange = (arr: [Dayjs, Dayjs]) => {
    setTimeDefaultValue((pre) => ({
      ...pre,
      rangePickerVaule: arr,
      selectValue: 0,
    }));
    const _times = arr.map((item) => dayjs(item).valueOf());
    setTimeRange(_times);
  };

  const linkToSearch = (row: TableDataItem) => {
    const _row = {
      monitor_object: monitorName,
      instance_id: form?.instance_id || '',
      metric_id: row.name,
    };
    const queryString = new URLSearchParams(_row).toString();
    const url = `/monitor/search?${queryString}`;
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  const linkToPolicy = (row: TableDataItem) => {
    const _row = {
      monitorName: monitorName,
      monitorObjId: monitorObject + '',
      instanceId: form?.instance_id || '',
      metricId: row.name,
      type: 'add',
    };
    const queryString = new URLSearchParams(_row).toString();
    const url = `/monitor/event/strategy/detail?${queryString}`;
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  return (
    <div>
      <div className="flex justify-between mb-[15px]">
        <Select
          className="w-[250px]"
          placeholder={t('common.searchPlaceHolder')}
          value={metricId}
          allowClear
          showSearch
          options={originMetricData.map((item) => ({
            label: item.display_name,
            title: item.name,
            options: (item.child || []).map((tex) => ({
              label: tex.display_name,
              value: tex.id,
            })),
          }))}
          onChange={handleMetricIdChange}
        ></Select>
        <TimeSelector
          defaultValue={timeDefaultValue}
          onChange={(value) => onTimeChange(value)}
          onFrequenceChange={onFrequenceChange}
          onRefresh={onRefresh}
        />
      </div>
      <Segmented
        className="mb-[20px]"
        value={activeTab}
        options={plugins}
        onChange={onTabChange}
      />
      <div className="groupList">
        <Spin spinning={loading}>
          {metricData.map((metricItem) => (
            <Spin
              className="w-full"
              key={metricItem.id}
              spinning={metricItem.isLoading}
            >
              <Collapse
                className="mb-[10px]"
                title={metricItem.display_name || ''}
                isOpen={metricItem.id === expandId}
                onToggle={(expanded) => toggleGroup(expanded, metricItem.id)}
              >
                <div className="flex flex-wrap justify-between">
                  {(metricItem.child || []).map((item) => (
                    <div
                      key={item.id}
                      className="w-[49%] border border-[var(--color-border-1)] p-[10px] mb-[10px]"
                    >
                      <div className="flex justify-between items-center">
                        <span className="text-[14px] relative">
                          <span className="font-[600] mr-[2px]">
                            {item.display_name}
                          </span>
                          <span className="text-[var(--color-text-3)] text-[12px]">
                            {`${
                              findUnitNameById(item.unit)
                                ? '（' + findUnitNameById(item.unit) + '）'
                                : ''
                            }`}
                          </span>
                          <Tooltip
                            placement="topLeft"
                            title={item.display_description}
                          >
                            <div
                              className="absolute cursor-pointer inline-block"
                              style={{
                                top: '-3px',
                                right: '-14px',
                              }}
                            >
                              <Icon
                                type="a-shuoming2"
                                className="text-[14px] text-[var(--color-text-3)]"
                              />
                            </div>
                          </Tooltip>
                        </span>
                        <div className="text-[var(--color-text-3)]">
                          <SearchOutlined
                            className="cursor-pointer"
                            onClick={() => {
                              linkToSearch(item);
                            }}
                          />
                          <BellOutlined
                            className="ml-[6px] cursor-pointer"
                            onClick={() => {
                              linkToPolicy(item);
                            }}
                          />
                        </div>
                      </div>
                      <div className="h-[200px] mt-[10px]">
                        <LineChart
                          metric={item}
                          data={item.viewData || []}
                          unit={item.unit}
                          onXRangeChange={onXRangeChange}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </Collapse>
            </Spin>
          ))}
        </Spin>
      </div>
    </div>
  );
};
export default MonitorView;
