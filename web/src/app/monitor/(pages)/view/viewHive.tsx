'use client';
import React, {
  useEffect,
  useState,
  useRef,
  useMemo,
  useCallback
} from 'react';
import useApiClient from '@/utils/request';
import useMonitorApi from '@/app/monitor/api';
import useViewApi from '@/app/monitor/api/view';
import { useTranslation } from '@/utils/i18n';
import {
  ViewListProps,
  NodeThresholdColor,
  ChartDataConfig
} from '@/app/monitor/types/view';
import {
  Pagination,
  TableDataItem,
  HexagonData,
  ModalRef,
  MetricItem
} from '@/app/monitor/types';
import TimeSelector from '@/components/time-selector';
import CatalogScopeSegmented from '@/components/catalog-scope-segmented';
import HexGridChart from '@/app/monitor/components/charts/hexgrid';
import HiveModal from './hiveModal';
import { EditOutlined } from '@ant-design/icons';
import { getEnumColor, isStringArray } from '@/app/monitor/utils/common';
import { useUnitTransform } from '@/app/monitor/hooks/useUnitTransform';
import { Select, Spin } from 'antd';
import { findByMonitorId } from '@/app/monitor/utils/monitorIds';
import { shouldSkipPeriodicRefresh } from '@/app/monitor/utils/metricRequestSlot';
import { fillInstanceListDisplayMetrics } from '@/app/monitor/utils/fillListDisplayMetrics';
import { ListItem } from '@/types';
const { Option } = Select;

const HEXAGON_AREA = 6400; // 格子的面积

// 展示指标值现按 (plugin, metric) 复合 key 回填(后端 display_field_key)。蜂巢图的指标选择
// 只携带指标名,故按名解析:先取裸 key(遗留/补充指标),否则取任一 `<plugin>::<metric>` key。
// 按插件隔离保证同一实例对同一指标名至多有一个插件的值,扫描不会取错。
const readDisplayMetricCell = (item: TableDataItem, metricName: string) => {
  if (item[metricName] != null) return item[metricName];
  const suffix = `::${metricName}`;
  for (const key of Object.keys(item)) {
    if (key.endsWith(suffix) && item[key] != null) return item[key];
  }
  return undefined;
};

const ViewHive: React.FC<ViewListProps> = ({ objects, objectId }) => {
  const { isLoading } = useApiClient();
  const { getMonitorMetrics } = useMonitorApi();
  const { getInstanceQueryParams, getInstanceSearch, getInstanceDisplayMetrics } =
    useViewApi();
  const { t } = useTranslation();
  const { getEnumValueUnit } = useUnitTransform();
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const modalRef = useRef<ModalRef>(null);
  const hexGridRef = useRef<HTMLDivElement>(null);
  const isFetchingRef = useRef<boolean>(false); // identity+回填全程在途，对齐 viewList listInFlight
  const requestIdRef = useRef(0);
  const abortControllerRef = useRef<AbortController | null>(null);
  const unassignedOnlyRef = useRef(false);
  const [tableLoading, setTableLoading] = useState<boolean>(false);
  const [chartData, setChartData] = useState<HexagonData[]>([]);
  const chartDataRef = useRef<HexagonData[]>([]);
  chartDataRef.current = chartData;
  const [pagination, setPagination] = useState<Pagination>({
    current: 1,
    total: 0,
    pageSize: 60 // 默认值
  });
  const [frequence, setFrequence] = useState<number>(0);
  const [mertics, setMertics] = useState<MetricItem[]>([]);
  const [node, setNode] = useState<string | null>(null);
  const [unassignedOnly, setUnassignedOnly] = useState(false);
  const [queryMetric, setQueryMetric] = useState<string | null>(null);
  const [hexColor, setHexColor] = useState<NodeThresholdColor[]>([]);
  const [nodeList, setNodeList] = useState<ListItem[]>([]);
  unassignedOnlyRef.current = unassignedOnly;

  const isPod = useMemo(() => {
    return findByMonitorId(objects, objectId)?.name === 'Pod';
  }, [objects, objectId]);

  const metricList = useMemo(() => {
    if (objectId && objects?.length && mertics?.length) {
      const target = findByMonitorId(objects, objectId);
      const metricNames = new Set(
        (target?.display_fields || [])
          .filter((col) => col.type !== 'field')
          .flatMap((col) => (col.metrics || []).map((binding) => binding.metric))
      );
      return mertics.filter((metric) => metricNames.has(metric.name));
    }
    return [];
  }, [mertics, objects, objectId]);

  // 动态设置 pageSize
  useEffect(() => {
    const updatePageSize = () => {
      if (!hexGridRef.current) return;
      const viewportWidth = hexGridRef.current.clientWidth - 44;
      const viewportHeight = hexGridRef.current.clientHeight;
      const calculatedPageSize = Math.floor(
        (viewportWidth * viewportHeight) / HEXAGON_AREA
      );
      setPagination((prev: Pagination) => ({
        ...prev,
        pageSize: calculatedPageSize
      }));
    };
    updatePageSize();
    window.addEventListener('resize', updatePageSize);
    return () => {
      window.removeEventListener('resize', updatePageSize);
      abortControllerRef.current?.abort();
    };
  }, []);

  // 页面初始化请求
  useEffect(() => {
    if (isLoading) return;
    if (objectId && objects?.length) {
      const objName = findByMonitorId(objects, objectId)?.name;
      if (objName) {
        getInitData(objName);
      }
    }
  }, [objectId, objects, isLoading]);

  // 条件过滤请求
  useEffect(() => {
    if (objectId && objects?.length && !isLoading) {
      onRefresh();
    }
  }, [node, unassignedOnly]);

  // 更新与销毁定时器
  useEffect(() => {
    if (!frequence) {
      clearTimer();
      return;
    }
    timerRef.current = setInterval(() => {
      if (shouldSkipPeriodicRefresh(isFetchingRef.current)) {
        return;
      }
      getAssetInsts('timer', {
        hexColor,
        queryMetric,
        metricList
      });
    }, frequence);
    return () => {
      clearTimer();
    };
  }, [
    frequence,
    objectId,
    node,
    pagination.current,
    pagination.pageSize,
    unassignedOnly
  ]);

  const handleScroll = useCallback(() => {
    if (!hexGridRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = hexGridRef.current;
    // 判断是否接近底部
    if (
      scrollTop + clientHeight >= scrollHeight - 10 &&
      !tableLoading &&
      !isFetchingRef.current
    ) {
      if (
        pagination.current * pagination.pageSize < pagination.total &&
        chartData.length < pagination.total
      ) {
        isFetchingRef.current = true; // 设置标志位，表示正在加载
        setPagination((prev) => ({
          ...prev,
          current: prev.current + 1
        }));
        getAssetInsts('more', {
          hexColor,
          queryMetric,
          metricList
        });
      }
    }
  }, [pagination, chartData]);

  const handleNodeChange = (id: string) => {
    setNode(id);
    setChartData([]);
    setPagination((prev: Pagination) => ({
      ...prev,
      current: 1
    }));
  };

  const handleQueryMetricChange = (id: string) => {
    setQueryMetric(id);
  };

  const getParams = () => {
    return {
      page: pagination.current,
      page_size: pagination.pageSize,
      // 展示指标由限流异步批回填，主列表只返回实例行。
      add_metrics: false,
      name: '',
      vm_params: {
        instance_id: '',
        node: node || ''
      },
      ...(unassignedOnly ? { unassigned: true } : {})
    };
  };

  const fillHexagonMetrics = async ({
    rows,
    startIndex,
    requestId,
    toChart,
    signal
  }: {
    rows: TableDataItem[];
    startIndex: number;
    requestId: number;
    toChart: (filled: TableDataItem[]) => HexagonData[];
    signal: AbortSignal;
  }) => {
    const filled = await fillInstanceListDisplayMetrics({
      rows,
      signal,
      isCurrent: () =>
        !signal.aborted && requestId === requestIdRef.current,
      fetchBatch: async (instanceIds, batchSignal) => {
        const payload = await getInstanceDisplayMetrics(
          objectId,
          {
            instance_ids: instanceIds,
            ...(unassignedOnlyRef.current ? { unassigned: true } : {})
          },
          { signal: batchSignal }
        );
        return payload?.results || [];
      }
    });
    if (signal.aborted || requestId !== requestIdRef.current) {
      return;
    }
    const nextChart = toChart(filled);
    // 只覆盖本页格子，避免 replace 整表擦掉已 append 的后续页。
    setChartData((prev) => {
      const merged = [...prev];
      merged.splice(startIndex, nextChart.length, ...nextChart);
      return merged;
    });
  };

  const getInitData = async (name: string) => {
    abortControllerRef.current?.abort();
    const abortController = new AbortController();
    abortControllerRef.current = abortController;
    const currentRequestId = ++requestIdRef.current;
    const params = getParams();
    const objParams = {
      monitor_object_id: String(objectId),
      name: isPod ? 'pod_status_phase' : 'node_status_condition'
    };
    isFetchingRef.current = true;
    setTableLoading(true);
    try {
      const getInstList = getInstanceSearch(objectId, params, {
        signal: abortController.signal
      });
      const getQueryParams = getInstanceQueryParams(name, objParams, {
        signal: abortController.signal
      });
      const { items: metricsData } = await getMonitorMetrics(objParams, {
        signal: abortController.signal
      });
      if (currentRequestId !== requestIdRef.current) {
        return;
      }
      setMertics(metricsData || []);
      const tagetMerticItem = metricsData.find(
        (item: MetricItem) =>
          item.name === (isPod ? 'pod_status_phase' : 'node_status_condition')
      );
      if (isStringArray(tagetMerticItem?.unit || '')) {
        const unitInfo = JSON.parse(tagetMerticItem.unit).map(
          (item: TableDataItem) => ({
            value: item.id || 0,
            color: item.color || '#10e433'
          })
        );
        setHexColor(unitInfo);
        setQueryMetric(tagetMerticItem.name);
      }
      const res = await Promise.all([getInstList, getQueryParams]);
      if (currentRequestId !== requestIdRef.current) {
        return;
      }
      const k8sQuery = res[1];
      if (k8sQuery?.cluster) {
        setNodeList(k8sQuery?.node || []);
      }
      const identityRows = res[0]?.results || [];
      const chartConfig = {
        data: identityRows,
        metricsData,
        hexColor,
        queryMetric: queryMetric as string
      };
      setChartData(dealChartData(chartConfig));
      setPagination((prev: Pagination) => ({
        ...prev,
        total: res[0]?.count || 0
      }));
      setTableLoading(false);
      await fillHexagonMetrics({
        rows: identityRows,
        startIndex: 0,
        requestId: currentRequestId,
        toChart: (filled) =>
          dealChartData({
            data: filled,
            metricsData: metricsData || [],
            hexColor,
            queryMetric: (tagetMerticItem?.name || queryMetric) as string
          }),
        signal: abortController.signal
      });
    } catch {
      if (currentRequestId === requestIdRef.current) {
        setMertics([]);
      }
    } finally {
      if (abortControllerRef.current === abortController) {
        isFetchingRef.current = false;
      }
      if (currentRequestId === requestIdRef.current) {
        setTableLoading(false);
      }
    }
  };

  const dealChartData = (chartConfig: ChartDataConfig) => {
    const {
      data,
      metricsData = metricList,
      hexColor,
      queryMetric
    } = chartConfig;
    const chartList = data.map((item: TableDataItem) => {
      const metricName =
        queryMetric || (isPod ? 'pod_status_phase' : 'node_status_condition');
      const tagetMerticItem = metricsData.find(
        (item) => item.name === metricName
      );
      if (tagetMerticItem) {
        const cellValue = readDisplayMetricCell(item, metricName);
        const isEnumMetric =
          tagetMerticItem.data_type === 'Enum' ||
          isStringArray(tagetMerticItem.unit || '');
        return {
          name: '',
          aiName: item.instance_name,
          aiValue: getEnumValueUnit(tagetMerticItem, cellValue),
          description: (
            <>
              <div>{item.instance_name}</div>
              {`${tagetMerticItem.display_name}: ${getEnumValueUnit(
                tagetMerticItem,
                cellValue
              )}`}
            </>
          ),
          fill: isEnumMetric
            ? handleFillColor(tagetMerticItem, cellValue)
            : handleHexColor(cellValue, hexColor)
        };
      }
      return {
        name: '',
        aiName: item.instance_name,
        description: item.instance_name,
        fill: '#10e433'
      };
    });
    return chartList;
  };

  const handleFillColor = (item: MetricItem, id: number | string) => {
    const color = getEnumColor(item, id);
    if (!color) {
      return '#10e433';
    }
    return color;
  };

  const handleHexColor = (value: any, colors: NodeThresholdColor[]) => {
    const item = colors.find((item) => value >= item.value);
    return item?.color || '#10e433';
  };

  const clearTimer = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
  };

  const getAssetInsts = async (
    type: string,
    {
      hexColor,
      queryMetric,
      metricList
    }: {
      hexColor: NodeThresholdColor[];
      queryMetric: string | null;
      metricList: MetricItem[];
    }
  ) => {
    if (type === 'timer' && shouldSkipPeriodicRefresh(isFetchingRef.current)) {
      return;
    }
    if (type !== 'timer') {
      abortControllerRef.current?.abort();
    } else if (isFetchingRef.current) {
      return;
    }
    const abortController = new AbortController();
    abortControllerRef.current = abortController;
    const currentRequestId = ++requestIdRef.current;
    const params = getParams();
    if (type === 'refresh') {
      params.page = 1;
    }
    if (type === 'more') {
      params.page = params.page + 1;
    }
    try {
      isFetchingRef.current = true;
      setTableLoading(type !== 'timer');
      const data = await getInstanceSearch(objectId, params, {
        signal: abortController.signal
      });
      const applied = currentRequestId === requestIdRef.current;
      if (!applied) {
        return;
      }
      const identityRows = data.results || [];
      const chartConfig = {
        data: identityRows,
        metricsData: metricList,
        hexColor,
        queryMetric: queryMetric as string
      };
      const chartList = dealChartData(chartConfig);
      setPagination((prev: Pagination) => ({
        ...prev,
        total: data.count || 0
      }));
      const startIndex = type === 'more' ? chartDataRef.current.length : 0;
      setChartData(
        type === 'more' ? [...chartDataRef.current, ...chartList] : chartList
      );
      setTableLoading(false);
      await fillHexagonMetrics({
        rows: identityRows,
        startIndex,
        requestId: currentRequestId,
        toChart: (filled) =>
          dealChartData({
            data: filled,
            metricsData: metricList,
            hexColor,
            queryMetric: queryMetric as string
          }),
        signal: abortController.signal
      });
    } finally {
      if (abortControllerRef.current === abortController) {
        isFetchingRef.current = false;
      }
      if (currentRequestId === requestIdRef.current) {
        setTableLoading(false);
      }
    }
  };

  const onFrequenceChange = (val: number) => {
    setFrequence(val);
  };

  const onRefresh = () => {
    setPagination((prev: Pagination) => ({
      ...prev,
      current: 1
    }));
    setChartData([]);
    getAssetInsts('refresh', {
      hexColor,
      queryMetric,
      metricList
    });
  };

  const openHiveModal = () => {
    modalRef.current?.showModal({
      type: '',
      title: '',
      form: metricList,
      query: queryMetric,
      color: hexColor
    });
  };

  const onConfirm = (metric: string, colors: any) => {
    setPagination((prev: Pagination) => ({
      ...prev,
      current: 1
    }));
    setChartData([]);
    getAssetInsts('refresh', {
      hexColor: colors,
      queryMetric: metric,
      metricList
    });
    setQueryMetric(metric);
    setHexColor(colors);
  };

  return (
    <div className="w-full h-[calc(100vh-216px)]">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-y-3">
        <div className="flex items-center gap-3">
          {isPod && (
            <>
              <span className="text-sm">
                {t('monitor.views.filterOptions')}
              </span>
              <Select
                value={node}
                allowClear
                showSearch
                style={{ width: 240 }}
                placeholder={t('monitor.views.node')}
                onChange={handleNodeChange}
              >
                {nodeList.map((item: ListItem, index: number) => (
                  <Option key={index} value={item.id}>
                    {item.name}
                  </Option>
                ))}
              </Select>
            </>
          )}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <CatalogScopeSegmented
            unassignedOnly={unassignedOnly}
            onChange={(checked) => {
              setUnassignedOnly(checked);
              setChartData([]);
              setPagination((prev: Pagination) => ({
                ...prev,
                current: 1
              }));
            }}
          />
          <div className="flex items-center">
            <span className="mr-2.5 text-sm">
              {t('monitor.views.displayIndicators')}
            </span>
            <Select
              className="text-center"
              disabled
              showSearch
              value={queryMetric}
              style={{ width: 120 }}
              suffixIcon={null}
              placeholder={t('monitor.views.editIndicators')}
              onChange={handleQueryMetricChange}
            >
              {metricList.map((item: MetricItem, index: number) => (
                <Option key={index} value={item.name}>
                  {item.display_name}
                </Option>
              ))}
            </Select>
            <EditOutlined
              className="ml-2.5 cursor-pointer"
              onClick={openHiveModal}
            />
          </div>
          <TimeSelector
            onlyRefresh
            onFrequenceChange={onFrequenceChange}
            onRefresh={onRefresh}
          />
        </div>
      </div>
      <div
        className="w-full h-full overflow-hidden overflow-y-auto"
        ref={hexGridRef}
        data-ai-hive-total={pagination.total}
        data-ai-hive-loaded={chartData.length}
        data-ai-hive-metric={metricList.find((item) => item.name === queryMetric)?.display_name || queryMetric || ''}
        data-ai-hive-node={nodeList.find((item) => item.id === node)?.name || node || ''}
        onScroll={handleScroll}
      >
        <Spin spinning={tableLoading} className="w-full h-full">
          <HexGridChart data={chartData}></HexGridChart>
        </Spin>
      </div>
      <HiveModal ref={modalRef} onConfirm={onConfirm} />
    </div>
  );
};
export default ViewHive;
