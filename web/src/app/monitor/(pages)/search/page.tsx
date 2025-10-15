'use client';
import React, { useEffect, useState, useRef } from 'react';
import { Spin, Select, Button, Segmented, Input, Tooltip } from 'antd';
import { BellOutlined, CloseOutlined, PlusOutlined } from '@ant-design/icons';
import { useConditionList } from '@/app/monitor/hooks';
import useApiClient from '@/utils/request';
import useMonitorApi from '@/app/monitor/api';
import TimeSelector from '@/components/time-selector';
import Collapse from '@/components/collapse';
import searchStyle from './index.module.scss';
import { useTranslation } from '@/utils/i18n';
import Icon from '@/components/icon';
import LineChart from '@/app/monitor/components/charts/lineChart';
import CustomTable from '@/components/custom-table';
import {
  ListItem,
  ColumnItem,
  ChartData,
  TimeSelectorDefaultValue,
  TreeItem,
  TimeValuesProps,
  GroupInfo,
  MetricItem,
  IndexViewItem,
  ObjectItem,
} from '@/app/monitor/types';
import { Dayjs } from 'dayjs';
import {
  SearchParams,
  InstanceItem,
  SearchTableDataItem,
  ConditionItem,
} from '@/app/monitor/types/search';
import {
  findUnitNameById,
  mergeViewQueryKeyValues,
  renderChart,
  getRecentTimeRange,
} from '@/app/monitor/utils/common';
import { useSearchParams } from 'next/navigation';
import dayjs from 'dayjs';
import TreeSelector from '@/app/monitor/components/treeSelector';
import { cloneDeep } from 'lodash';
const { Option } = Select;

const SearchView: React.FC = () => {
  const { get, isLoading } = useApiClient();
  const {
    getMonitorObject,
    getMonitorMetrics,
    getMetricsGroup,
    getInstanceList,
  } = useMonitorApi();
  const { t } = useTranslation();
  const CONDITION_LIST = useConditionList();
  const searchParams = useSearchParams();
  const url_instance_id = searchParams.get('instance_id');
  const url_obj_id = searchParams.get('monitor_object');
  const url_metric_id = searchParams.get('metric_id');
  const [pageLoading, setPageLoading] = useState<boolean>(false);
  const [objLoading, setObjLoading] = useState<boolean>(false);
  const [metric, setMetric] = useState<string | null>(url_metric_id || null);
  const [metrics, setMetrics] = useState<MetricItem[]>([]);
  const [metricsLoading, setMetricsLoading] = useState<boolean>(false);
  const [instanceLoading, setInstanceLoading] = useState<boolean>(false);
  const [instanceId, setInstanceId] = useState<string[]>(
    url_instance_id ? [url_instance_id] : []
  );
  const [instances, setInstances] = useState<InstanceItem[]>([]);
  const [labels, setLabels] = useState<string[]>([]);
  const [object, setObject] = useState<React.Key>('');
  const [objects, setObjects] = useState<ObjectItem[]>([]);
  const [activeTab, setActiveTab] = useState<string>('area');
  const [conditions, setConditions] = useState<ConditionItem[]>([]);
  const [timeValues, setTimeValues] = useState<TimeValuesProps>({
    timeRange: [],
    originValue: 15,
  });
  const [timeDefaultValue, setTimeDefaultValue] =
    useState<TimeSelectorDefaultValue>({
      selectValue: 15,
      rangePickerVaule: null,
    });
  const [columns, setColumns] = useState<ColumnItem[]>([]);
  const [tableData, setTableData] = useState<SearchTableDataItem[]>([]);
  const [chartData, setChartData] = useState<ChartData[]>([]);
  const [frequence, setFrequence] = useState<number>(0);
  const [unit, setUnit] = useState<string>('');
  const isArea: boolean = activeTab === 'area';
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const [treeData, setTreeData] = useState<TreeItem[]>([]);
  const [originMetricData, setOriginMetricData] = useState<IndexViewItem[]>([]);
  const [defaultSelectObj, setDefaultSelectObj] = useState<React.Key>('');

  useEffect(() => {
    if (isLoading) return;
    getObjects();
  }, [isLoading]);

  useEffect(() => {
    if (!frequence) {
      clearTimer();
      return;
    }
    timerRef.current = setInterval(() => {
      handleSearch('timer', activeTab);
    }, frequence);
    return () => {
      clearTimer();
    };
  }, [activeTab, frequence, object, metric, conditions, instances, timeValues]);

  useEffect(() => {
    if (isLoading) return;
    if (url_obj_id && metrics.length && instances.length) {
      handleSearch('refresh', 'area');
    }
  }, [url_obj_id, metrics, instances, isLoading]);

  const getObjects = async () => {
    try {
      setObjLoading(true);
      const data: ObjectItem[] = await getMonitorObject({
        add_instance_count: true,
      });
      const _treeData = getTreeData(cloneDeep(data));
      setTreeData(_treeData);
      setObjects(data);
      setDefaultSelectObj(url_obj_id ? +url_obj_id : '');
    } finally {
      setObjLoading(false);
    }
  };

  const getMetrics = async (params = {}) => {
    try {
      setMetricsLoading(true);
      const getGroupList = getMetricsGroup(params);
      const getMetrics = getMonitorMetrics(params);
      Promise.all([getGroupList, getMetrics])
        .then((res) => {
          const metricData = cloneDeep(res[1] || []);
          setMetrics(res[1] || []);
          const groupData = res[0].map((item: GroupInfo) => ({
            ...item,
            child: [],
          }));
          metricData.forEach((metric: MetricItem) => {
            const target = groupData.find(
              (item: GroupInfo) => item.id === metric.metric_group
            );
            if (target) {
              target.child.push(metric);
            }
          });
          const _groupData = groupData.filter(
            (item: IndexViewItem) => !!item.child?.length
          );
          setOriginMetricData(_groupData);
        })
        .finally(() => {
          setMetricsLoading(false);
        });
    } catch {
      setMetricsLoading(false);
    }
  };

  const getInstList = async (id: React.Key) => {
    try {
      setInstanceLoading(true);
      const data = await getInstanceList(id, {
        page_size: -1,
      });
      setInstances(data.results || []);
    } finally {
      setInstanceLoading(false);
    }
  };

  const canSearch = () => {
    return !!metric && instanceId?.length;
  };

  const getParams = (_timeRange: TimeValuesProps): SearchParams => {
    const metricItem = metrics.find((item) => item.name === metric);
    const _query: string = metricItem?.query || '';
    const queryValues: string[][] = instances
      .filter((item) => instanceId.includes(item.instance_id))
      .map((item) => item.instance_id_values);
    const querykeys: string[] = metricItem?.instance_id_keys || [];
    const queryList = [];
    for (let i = 0; i < queryValues.length; i++) {
      queryList.push({
        keys: querykeys,
        values: queryValues[i],
      });
    }
    const params: SearchParams = { query: '' };
    const recentTimeRange = getRecentTimeRange(_timeRange);
    const startTime = recentTimeRange.at(0);
    const endTime = recentTimeRange.at(1);
    if (startTime && endTime) {
      const MAX_POINTS = 100; // 最大数据点数
      const DEFAULT_STEP = 360; // 默认步长
      params.start = startTime;
      params.end = endTime;
      params.step = Math.max(
        Math.ceil(
          (params.end / MAX_POINTS - params.start / MAX_POINTS) / DEFAULT_STEP
        ),
        1
      );
    }
    let query = '';
    if (instanceId?.length) {
      query += mergeViewQueryKeyValues(queryList);
    }
    if (conditions?.length) {
      const conditionQueries = conditions
        .map((condition) => {
          if (condition.label && condition.condition && condition.value) {
            return `${condition.label}${condition.condition}"${condition.value}"`;
          }
          return '';
        })
        .filter(Boolean);
      if (conditionQueries.length) {
        if (query) {
          query += ',';
        }
        query += conditionQueries.join(',');
      }
    }
    params.query = _query.replace(/__\$labels__/g, query);
    return params;
  };

  const onTimeChange = (val: number[], originValue: number | null) => {
    const timeRange = {
      timeRange: val,
      originValue,
    };
    setTimeValues(timeRange);
    handleSearch('refresh', activeTab, timeRange);
  };

  const clearTimer = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
  };

  const onFrequenceChange = (val: number) => {
    setFrequence(val);
  };

  const onRefresh = () => {
    handleSearch('refresh', activeTab);
  };

  const createPolicy = () => {
    const params = new URLSearchParams({
      monitorName: objects.find((item) => item.id === object)?.name + '',
      monitorObjId: object + '',
      metricId: metric || '',
      instanceId: instanceId.join(','),
      type: 'add',
    });
    const targetUrl = `/monitor/event/strategy/detail?${params.toString()}`;
    window.open(targetUrl, '_blank', 'noopener,noreferrer');
  };

  const handleInstanceChange = (val: string[]) => {
    setInstanceId(val);
  };

  const handleMetricChange = (val: string) => {
    setMetric(val);
    const target = metrics.find((item) => item.name === val);
    const _labels = (target?.dimensions || []).map((item) => item.name);
    setLabels(_labels);
    setUnit(target?.unit || '');
  };

  const handleObjectChange = (val: string) => {
    if (object) {
      setMetrics([]);
      setLabels([]);
      setMetric(null);
      setInstanceId([]);
      setInstances([]);
      setConditions([]);
      setChartData([]);
      setTableData([]);
    }
    setObject(val);
    if (val) {
      getMetrics({
        monitor_object_id: val,
      });
      getInstList(val);
    }
  };

  const handleLabelChange = (val: string, index: number) => {
    const _conditions = cloneDeep(conditions);
    _conditions[index].label = val;
    setConditions(_conditions);
  };

  const handleConditionChange = (val: string, index: number) => {
    const _conditions = cloneDeep(conditions);
    _conditions[index].condition = val;
    setConditions(_conditions);
  };

  const handleValueChange = (
    e: React.ChangeEvent<HTMLInputElement>,
    index: number
  ) => {
    const _conditions = cloneDeep(conditions);
    _conditions[index].value = e.target.value;
    setConditions(_conditions);
  };

  const addConditionItem = () => {
    const _conditions = cloneDeep(conditions);
    _conditions.push({
      label: null,
      condition: null,
      value: '',
    });
    setConditions(_conditions);
  };

  const deleteConditionItem = (index: number) => {
    const _conditions = cloneDeep(conditions);
    _conditions.splice(index, 1);
    setConditions(_conditions);
  };

  const searchData = () => {
    handleSearch('refresh', activeTab);
  };

  const onTabChange = (val: string) => {
    setActiveTab(val);
    handleSearch('refresh', val);
  };

  const handleSearch = async (
    type: string,
    tab: string,
    _timeRange = timeValues
  ) => {
    if (type !== 'timer') {
      setChartData([]);
      setTableData([]);
    }
    if (!canSearch()) {
      return;
    }
    try {
      setPageLoading(type === 'refresh');
      const areaCurrent = tab === 'area';
      const url = areaCurrent
        ? '/monitor/api/metrics_instance/query_range/'
        : '/monitor/api/metrics_instance/query/';
      let params = getParams(_timeRange);
      if (!areaCurrent) {
        params = {
          time: params.end,
          query: params.query,
        };
      }
      const responseData = await get(url, {
        params,
      });
      const data = responseData.data?.result || [];
      if (areaCurrent) {
        const list = instances
          .filter((item) => instanceId.includes(item.instance_id))
          .map((item) => {
            const targetMetric = metrics.find((item) => item.name === metric);
            return {
              instance_id_values: item.instance_id_values,
              instance_name: item.instance_name,
              instance_id: item.instance_id,
              instance_id_keys: targetMetric?.instance_id_keys || [],
              dimensions: targetMetric?.dimensions || [],
              title: targetMetric?.display_name || '--',
              showInstName: true,
            };
          });
        const _chartData = renderChart(data, list);
        setChartData(_chartData);
      } else {
        const _tableData = data.map(
          (item: SearchTableDataItem, index: number) => ({
            ...item.metric,
            value: item.value[1] ?? '--',
            index,
          })
        );
        const metricTarget =
          metrics.find((item) => item.name === metric)?.dimensions || [];
        const colKeys = Array.from(
          new Set(
            metricTarget
              .map((item) => item.name)
              .concat(['instance_name', 'instance_id', 'value'])
          )
        );
        const tableColumns = Object.keys(_tableData[0] || {})
          .filter((item) => colKeys.includes(item))
          .map((item) => ({
            title: item,
            dataIndex: item,
            key: item,
            width: 200,
            ellipsis: {
              showTitle: true,
            },
          }));
        const _columns: any = cloneDeep(tableColumns);
        if (_columns[0]) _columns[0].fixed = 'left';
        setColumns(_columns);
        setTableData(_tableData);
      }
    } finally {
      setPageLoading(false);
    }
  };

  const onXRangeChange = (arr: [Dayjs, Dayjs]) => {
    setTimeDefaultValue((pre) => ({
      ...pre,
      rangePickerVaule: arr,
      selectValue: 0,
    }));
    const _times = arr.map((item) => dayjs(item).valueOf());
    const timeRange = {
      timeRange: _times,
      originValue: 0,
    };
    setTimeValues(timeRange);
    handleSearch('refresh', activeTab, timeRange);
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
        title: (item.display_name || '--') + `(${item.instance_count || 0})`,
        label: item.name || '--',
        key: item.id,
        children: [],
      });
      return acc;
    }, {} as Record<string, TreeItem>);
    if (groupedData.Other) {
      groupedData.Other.children = groupedData.Other.children.filter(
        (item) => item.label !== 'SNMP Trap'
      );
    }
    return Object.values(groupedData);
  };

  return (
    <div className={searchStyle.searchWrapper}>
      <div className={searchStyle.time}>
        <TimeSelector
          defaultValue={timeDefaultValue}
          onChange={onTimeChange}
          onFrequenceChange={onFrequenceChange}
          onRefresh={onRefresh}
        />
        <Button
          type="primary"
          className="ml-[8px]"
          disabled={!canSearch()}
          onClick={searchData}
        >
          {t('common.search')}
        </Button>
      </div>
      <div className={searchStyle.searchMain}>
        <div className={searchStyle.tree}>
          <TreeSelector
            data={treeData}
            loading={objLoading}
            defaultSelectedKey={defaultSelectObj as string}
            onNodeSelect={handleObjectChange}
          />
        </div>
        <div className={searchStyle.search}>
          <div className={searchStyle.criteria}>
            <Collapse
              title={t('monitor.search.searchCriteria')}
              icon={
                <Tooltip
                  placement="topLeft"
                  title={t('monitor.events.createPolicy')}
                >
                  <Button
                    disabled={!object}
                    onClick={createPolicy}
                    type="link"
                    size="small"
                    icon={<BellOutlined />}
                  />
                </Tooltip>
              }
            >
              <div className={searchStyle.condition}>
                <div className={searchStyle.conditionItem}>
                  <div className={searchStyle.itemLabel}>
                    {t('monitor.source')}
                  </div>
                  <div className={`${searchStyle.itemOption}`}>
                    <Select
                      mode="multiple"
                      showSearch
                      placeholder={t('monitor.instance')}
                      className={`w-[300px] ${searchStyle.sourceObject}`}
                      maxTagCount="responsive"
                      loading={instanceLoading}
                      value={instanceId}
                      onChange={handleInstanceChange}
                    >
                      {instances.map((item) => (
                        <Option value={item.instance_id} key={item.instance_id}>
                          {item.instance_name}
                        </Option>
                      ))}
                    </Select>
                  </div>
                </div>
                <div className={searchStyle.conditionItem}>
                  <div className={searchStyle.itemLabel}>
                    {t('monitor.metric')}
                  </div>
                  <div className={searchStyle.itemOption}>
                    <Select
                      className="w-[300px]"
                      placeholder={t('monitor.metric')}
                      showSearch
                      value={metric}
                      loading={metricsLoading}
                      options={originMetricData.map((item) => ({
                        label: item.display_name,
                        title: item.name,
                        options: (item.child || []).map((tex) => ({
                          label: tex.display_name,
                          value: tex.name,
                        })),
                      }))}
                      onChange={handleMetricChange}
                    />
                  </div>
                </div>
                <div className={searchStyle.conditionItem}>
                  <div
                    className={`${searchStyle.itemLabel} ${searchStyle.conditionLabel}`}
                  >
                    {t('monitor.filter')}
                  </div>
                  <div className="flex">
                    {conditions.length ? (
                      <ul className={searchStyle.conditions}>
                        {conditions.map((conditionItem, index) => (
                          <li
                            className={`${searchStyle.itemOption} ${searchStyle.filter}`}
                            key={index}
                          >
                            <Select
                              className={`w-[150px] ${searchStyle.filterLabel}`}
                              placeholder={t('monitor.label')}
                              showSearch
                              value={conditionItem.label}
                              onChange={(val) => handleLabelChange(val, index)}
                            >
                              {labels.map((item) => (
                                <Option value={item} key={item}>
                                  {item}
                                </Option>
                              ))}
                            </Select>
                            <Select
                              className="w-[90px]"
                              placeholder={t('monitor.term')}
                              value={conditionItem.condition}
                              onChange={(val) =>
                                handleConditionChange(val, index)
                              }
                            >
                              {CONDITION_LIST.map((item: ListItem) => (
                                <Option value={item.id} key={item.id}>
                                  {item.name}
                                </Option>
                              ))}
                            </Select>
                            <Input
                              className="w-[150px]"
                              placeholder={t('monitor.value')}
                              value={conditionItem.value}
                              onChange={(e) => handleValueChange(e, index)}
                            ></Input>
                            <Button
                              icon={<CloseOutlined />}
                              onClick={() => deleteConditionItem(index)}
                            />
                            <Button
                              icon={<PlusOutlined />}
                              onClick={addConditionItem}
                            />
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <Button
                        className="mt-[10px]"
                        disabled={!metric}
                        icon={<PlusOutlined />}
                        onClick={addConditionItem}
                      />
                    )}
                  </div>
                </div>
              </div>
            </Collapse>
          </div>
          <Spin spinning={pageLoading}>
            <div className={searchStyle.chart}>
              <Segmented
                className="mb-[10px]"
                value={activeTab}
                options={[
                  {
                    label: (
                      <div className="flex items-center">
                        <Icon type="duijimianjitu" className="mr-[8px]" />
                        {t('monitor.search.area')}
                      </div>
                    ),
                    value: 'area',
                  },
                  {
                    label: (
                      <div className="flex items-center">
                        <Icon type="tabulation" className="mr-[8px]" />
                        {t('monitor.search.table')}
                      </div>
                    ),
                    value: 'table',
                  },
                ]}
                onChange={onTabChange}
              />
              {isArea ? (
                <div className={searchStyle.chartArea}>
                  {!!metric && (
                    <div className="flex justify-between items-center">
                      <span className="text-[14px] relative mb-[10px]">
                        <span className="font-[600] mr-[2px]">
                          {metrics.find((item) => item.name === metric)
                            ?.display_name || '--'}
                        </span>
                        <span className="text-[var(--color-text-3)] text-[12px]">
                          {`${
                            findUnitNameById(
                              metrics.find((item) => item.name === metric)?.unit
                            )
                              ? '（' +
                                findUnitNameById(
                                  metrics.find((item) => item.name === metric)
                                    ?.unit
                                ) +
                                '）'
                              : ''
                          }`}
                        </span>
                        <Tooltip
                          placement="topLeft"
                          title={
                            metrics.find((item) => item.name === metric)
                              ?.display_description || ''
                          }
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
                    </div>
                  )}
                  <LineChart
                    metric={metrics.find((item) => item.name === metric)}
                    data={chartData}
                    unit={unit}
                    showDimensionTable
                    onXRangeChange={onXRangeChange}
                  />
                </div>
              ) : (
                <CustomTable
                  scroll={{ y: 'calc(100vh - 440px)' }}
                  columns={columns}
                  dataSource={tableData}
                  pagination={false}
                  rowKey="index"
                />
              )}
            </div>
          </Spin>
        </div>
      </div>
    </div>
  );
};

export default SearchView;
