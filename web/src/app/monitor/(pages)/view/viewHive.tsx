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
import HexGridChart from '@/app/monitor/components/charts/hexgrid';
import HiveModal from './hiveModal';
import { EditOutlined } from '@ant-design/icons';
import { getEnumColor, isStringArray } from '@/app/monitor/utils/common';
import { useUnitTransform } from '@/app/monitor/hooks/useUnitTransform';
import { useObjectConfigInfo } from '@/app/monitor/hooks/integration/common/getObjectConfig';
import { Select, Spin } from 'antd';
import { ListItem } from '@/types';
const { Option } = Select;

const HEXAGON_AREA = 6400; // 格子的面积

const ViewHive: React.FC<ViewListProps> = ({ objects, objectId }) => {
  const { isLoading } = useApiClient();
  const { getMonitorMetrics } = useMonitorApi();
  const { getInstanceQueryParams, getInstanceSearch } = useViewApi();
  const { t } = useTranslation();
  const { getEnumValueUnit } = useUnitTransform();
  const { getTableDiaplay } = useObjectConfigInfo();
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const modalRef = useRef<ModalRef>(null);
  const hexGridRef = useRef<HTMLDivElement>(null);
  const isFetchingRef = useRef<boolean>(false); // 用于标记是否正在加载数据
  const [tableLoading, setTableLoading] = useState<boolean>(false);
  const [chartData, setChartData] = useState<HexagonData[]>([]);
  const [pagination, setPagination] = useState<Pagination>({
    current: 1,
    total: 0,
    pageSize: 60 // 默认值
  });
  const [frequence, setFrequence] = useState<number>(0);
  const [queryData, setQueryData] = useState<any[]>([]);
  const [mertics, setMertics] = useState<MetricItem[]>([]);
  const [colony, setColony] = useState<string | null>(null);
  const [node, setNode] = useState<string | null>(null);
  const [queryMetric, setQueryMetric] = useState<string | null>(null);
  const [hexColor, setHexColor] = useState<NodeThresholdColor[]>([]);
  const [nodeList, setNodeList] = useState<ListItem[]>([]);

  const isPod = useMemo(() => {
    return objects.find((item) => item.id === objectId)?.name === 'Pod';
  }, [objects, objectId]);

  const metricList = useMemo(() => {
    if (objectId && objects?.length && mertics?.length) {
      const objName = objects.find((item) => item.id === objectId)?.name;
      const nodeMetircs = [
        { type: 'progress', key: 'node_cpu_utilization' },
        { type: 'enum', key: 'node_status_condition' }
      ];
      if (objName) {
        const filterMetrics = isPod ? getTableDiaplay(objName) : nodeMetircs;
        return mertics.filter((metric) =>
          filterMetrics.find((item: TableDataItem) => item.key === metric.name)
        );
      }
    }
    return [];
  }, [mertics, isPod]);

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
    };
  }, []);

  // 页面初始化请求
  useEffect(() => {
    if (isLoading) return;
    if (objectId && objects?.length) {
      const objName = objects.find((item) => item.id === objectId)?.name;
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
  }, [colony, node]);

  // 更新与销毁定时器
  useEffect(() => {
    if (!frequence) {
      clearTimer();
      return;
    }
    timerRef.current = setInterval(() => {
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
    colony,
    node,
    pagination.current,
    pagination.pageSize
  ]);

  // 加载更多节流
  useEffect(() => {
    if (!tableLoading) {
      isFetchingRef.current = false;
    }
  }, [tableLoading]);

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

  const handleColonyChange = (id: string) => {
    setColony(id);
    setNode(null);
    setChartData([]);
    setPagination((prev: Pagination) => ({
      ...prev,
      current: 1
    }));
  };

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
      add_metrics: true,
      name: '',
      vm_params: {
        instance_id: colony || '',
        node: node || ''
      }
    };
  };

  const getInitData = async (name: string) => {
    const params = getParams();
    const objParams = {
      monitor_object_id: objectId
    };
    const getInstList = await getInstanceSearch(objectId, params);
    const getQueryParams = await getInstanceQueryParams(name, objParams);
    setTableLoading(true);
    try {
      const metricsData = await getMonitorMetrics(objParams);
      setMertics(metricsData || []);
      const tagetMerticItem = metricsData.find(
        (item: MetricItem) =>
          item.name === (isPod ? 'pod_status_phase' : 'node_status_condition')
      );
      console.log(tagetMerticItem);
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
      const k8sQuery = res[1];
      let queryForm: any[] = [];
      if (k8sQuery?.cluster) {
        queryForm = k8sQuery?.cluster || [];
        setNodeList(k8sQuery?.node || []);
      } else {
        queryForm = (k8sQuery || []).map((item: any) => {
          if (typeof item === 'string') {
            return { id: item, child: [] };
          }
          return {
            id: item?.id,
            name: item?.name || '',
            child: []
          };
        });
      }
      const chartConfig = {
        data: res[0]?.results || [],
        metricsData,
        hexColor,
        queryMetric: queryMetric as string
      };
      setQueryData(queryForm);
      setChartData(dealChartData(chartConfig));
      setPagination((prev: Pagination) => ({
        ...prev,
        total: res[0]?.count || 0
      }));
    } catch {
      setMertics([]);
    } finally {
      setTableLoading(false);
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
        return {
          name: '',
          description: (
            <>
              <div>{item.instance_name}</div>
              {`${tagetMerticItem.display_name}: ${getEnumValueUnit(
                tagetMerticItem,
                item[metricName]
              )}`}
            </>
          ),
          fill: queryMetric
            ? handleHexColor(item[metricName], hexColor)
            : handleFillColor(tagetMerticItem, item[metricName])
        };
      }
      return {
        name: '',
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
    const params = getParams();
    if (type === 'refresh') {
      params.page = 1;
    }
    if (type === 'more') {
      params.page = params.page + 1;
    }
    try {
      setTableLoading(type !== 'timer');
      const data = await getInstanceSearch(objectId, params);
      const chartConfig = {
        data: data.results || [],
        metricsData: metricList,
        hexColor,
        queryMetric: queryMetric as string
      };
      const chartList = dealChartData(chartConfig);
      setPagination((prev: Pagination) => ({
        ...prev,
        total: data.count || 0
      }));
      setChartData((prev: any) =>
        type === 'more' ? [...prev, ...chartList] : chartList
      );
    } finally {
      setTableLoading(false);
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
      <div className="flex justify-between flex-wrap">
        <div className="flex items-center mb-[20px]">
          <span className="text-[14px] mr-[10px]">
            {t('monitor.views.filterOptions')}
          </span>
          <Select
            value={colony}
            allowClear
            showSearch
            style={{ width: 240 }}
            placeholder={t('monitor.views.colony')}
            onChange={handleColonyChange}
          >
            {queryData.map((item) => (
              <Option key={item.id} value={item.id}>
                {item.id}
              </Option>
            ))}
          </Select>
          {isPod && (
            <>
              <Select
                className="ml-[8px]"
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
        <div className="flex items-center mb-[20px]">
          <div className="mr-[8px]">
            <span className="text-[14px] mr-[10px]">
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
              className="ml-[10px] cursor-pointer"
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
