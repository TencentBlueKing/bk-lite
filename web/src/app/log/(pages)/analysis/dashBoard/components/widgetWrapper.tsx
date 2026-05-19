import React, { useState, useEffect, useRef, useMemo } from 'react';
import { Spin } from 'antd';
import { BaseWidgetProps } from '@/app/log/types/analysis';
import useSearchApi from '@/app/log/api/search';
import useApiClient from '@/utils/request';
import ComPie from '../widgets/comPie';
import ComLine from '../widgets/comLine';
import ComBar from '../widgets/comBar';
import ComTable from '../widgets/comTable';
import Msgtable from '../widgets/msgTable';
import ComSingle from '../widgets/comSingle';
import ComSankey from '../widgets/comSankey';
import ComHeatmap from '../widgets/comHeatmap';
import ComKpiCard from '../widgets/comKpiCard';
import ComBarLine from '../widgets/comBarLine';
import ComScatter from '../widgets/comScatter';
import {
  DockerKpiCard,
  DockerAreaChart,
  DockerDualLine,
  DockerDonutChart,
  DockerSeverityDonut,
  DockerErrorTable,
  DockerBarChart,
  DockerLogTail
} from '../widgets/docker';
import {
  HttpKpiCard,
  HttpBarLine,
  HttpDonut,
  HttpRequestTable
} from '../widgets/http';
import {
  FlowKpiCard,
  FlowTrend,
  FlowDonut,
  FlowBar,
  FlowTable,
  FlowSankey
} from '../widgets/flows';
import {
  MysqlKpiCard,
  MysqlBarLine,
  MysqlDualLine,
  MysqlDonut,
  MysqlSlowTable,
  MysqlDetailTable,
  MysqlInstanceBar
} from '../widgets/mysql';
import {
  RedisKpiCard,
  RedisDonut,
  RedisLogTable,
  RedisInstanceBar,
  RedisTrendLine,
  RedisNodeCompareBar
} from '../widgets/redis';
import { SearchParams } from '@/app/log/types/search';

const buildInstanceFilterQuery = (
  queryText: string,
  instanceIds?: Array<string | number>
) => {
  if (!instanceIds?.length) {
    return queryText;
  }

  const instanceFilter =
    instanceIds.length === 1
      ? `instance_id:"${String(instanceIds[0])}"`
      : `(${instanceIds.map((id) => `instance_id:"${String(id)}"`).join(' OR ')})`;

  const separatorIndex = queryText.indexOf('|');
  const baseFilter =
    separatorIndex >= 0
      ? queryText.slice(0, separatorIndex).trim()
      : queryText.trim();
  const pipeline =
    separatorIndex >= 0 ? queryText.slice(separatorIndex).trimStart() : '';

  const mergedFilter =
    !baseFilter || baseFilter === '*'
      ? instanceFilter
      : `(${baseFilter}) AND ${instanceFilter}`;

  return pipeline ? `${mergedFilter} ${pipeline}` : mergedFilter;
};

const buildContainerFilterQuery = (
  queryText: string,
  containerNames?: Array<string | number>
) => {
  if (!containerNames?.length) {
    return queryText;
  }

  const containerFilter =
    containerNames.length === 1
      ? `container_name:"${String(containerNames[0])}"`
      : `(${containerNames.map((name) => `container_name:"${String(name)}"`).join(' OR ')})`;

  const separatorIndex = queryText.indexOf('|');
  const baseFilter =
    separatorIndex >= 0
      ? queryText.slice(0, separatorIndex).trim()
      : queryText.trim();
  const pipeline =
    separatorIndex >= 0 ? queryText.slice(separatorIndex).trimStart() : '';

  const mergedFilter =
    !baseFilter || baseFilter === '*'
      ? containerFilter
      : `(${baseFilter}) AND ${containerFilter}`;

  return pipeline ? `${mergedFilter} ${pipeline}` : mergedFilter;
};

// 根据时间跨度计算时间间隔
const calculateTimeInterval = (startTime: string, endTime: string): string => {
  const start = new Date(startTime);
  const end = new Date(endTime);
  const diffInHours =
    Math.abs(end.getTime() - start.getTime()) / (1000 * 60 * 60);

  if (diffInHours <= 24) {
    return '1m';
  } else if (diffInHours <= 720) {
    // 720小时 = 30天
    return '1h';
  } else {
    return '1d';
  }
};

const componentMap: Record<string, React.ComponentType<any>> = {
  line: ComLine,
  pie: ComPie,
  bar: ComBar,
  table: ComTable,
  message: Msgtable,
  single: ComSingle,
  sankey: ComSankey,
  heatmap: ComHeatmap,
  kpiCard: ComKpiCard,
  barLine: ComBarLine,
  scatter: ComScatter,
  dockerKpiCard: DockerKpiCard,
  dockerArea: DockerAreaChart,
  dockerDualLine: DockerDualLine,
  dockerDonut: DockerDonutChart,
  dockerSeverityDonut: DockerSeverityDonut,
  dockerErrorTable: DockerErrorTable,
  dockerBar: DockerBarChart,
  dockerLogTail: DockerLogTail,
  httpKpiCard: HttpKpiCard,
  httpBarLine: HttpBarLine,
  httpDonut: HttpDonut,
  httpRequestTable: HttpRequestTable,
  flowKpiCard: FlowKpiCard,
  flowTrend: FlowTrend,
  flowDonut: FlowDonut,
  flowBar: FlowBar,
  flowTable: FlowTable,
  flowSankey: FlowSankey,
  mysqlKpiCard: MysqlKpiCard,
  mysqlBarLine: MysqlBarLine,
  mysqlDualLine: MysqlDualLine,
  mysqlDonut: MysqlDonut,
  mysqlSlowTable: MysqlSlowTable,
  mysqlDetailTable: MysqlDetailTable,
  mysqlInstanceBar: MysqlInstanceBar,
  redisKpiCard: RedisKpiCard,
  redisDonut: RedisDonut,
  redisLogTable: RedisLogTable,
  redisInstanceBar: RedisInstanceBar,
  redisTrendLine: RedisTrendLine,
  redisNodeCompareBar: RedisNodeCompareBar
};

interface WidgetWrapperProps extends BaseWidgetProps {
  chartType?: string;
  editable?: boolean;
  getLatestTimeRange?: () => number[];
}

const WidgetWrapper: React.FC<WidgetWrapperProps> = ({
  chartType,
  config,
  globalTimeRange,
  otherConfig,
  refreshKey,
  onReady,
  editable = false,
  getLatestTimeRange,
  ...otherProps
}) => {
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const prevAbortControllerRef = useRef<AbortController | null>(null);
  const globalTimeRangeRef = useRef(globalTimeRange);
  const [rawData, setRawData] = useState<any>(null);
  const [prevData, setPrevData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const { getLogs } = useSearchApi();
  const { isLoading } = useApiClient();
  const querySignature = useMemo(
    () =>
      JSON.stringify({
        chartType,
        dataSource: config?.dataSource,
        dataSourceParams: config?.dataSourceParams,
        displayMaps: config?.displayMaps
      }),
    [
      chartType,
      config?.dataSource,
      config?.dataSourceParams,
      config?.displayMaps
    ]
  );

  const isKpiCard = [
    'dockerKpiCard',
    'flowKpiCard',
    'httpKpiCard',
    'kpiCard',
    'mysqlKpiCard',
    'redisKpiCard'
  ].includes(chartType || '');

  // 保持 ref 与最新 props 同步
  useEffect(() => {
    globalTimeRangeRef.current = globalTimeRange;
  }, [globalTimeRange]);

  // 组件卸载时取消请求
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
      prevAbortControllerRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (!otherConfig.frequence) {
      clearTimer();
      return;
    }
    timerRef.current = setInterval(() => {
      // Re-derive fresh time range for relative time selections (e.g. "last 15 min")
      if (getLatestTimeRange) {
        globalTimeRangeRef.current = getLatestTimeRange();
      }
      fetchData(true);
    }, otherConfig.frequence);
    return () => {
      clearTimer();
    };
  }, [
    otherConfig.frequence,
    config,
    otherConfig.groupIds,
    otherConfig.instanceIds,
    otherConfig.containerNames,
    otherConfig.timeRange,
    refreshKey
  ]);

  useEffect(() => {
    if (config?.dataSource && !isLoading && otherConfig.groupIds) {
      fetchData();
    }
  }, [
    querySignature,
    otherConfig.groupIds,
    otherConfig.instanceIds,
    otherConfig.containerNames,
    otherConfig.timeRange,
    refreshKey,
    isLoading
  ]);

  const clearTimer = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
  };

  /**
   * 根据当前时间范围计算上一个周期的时间范围
   * 例如当前 [t0, t1]，上一周期为 [t0 - (t1-t0), t0]
   */
  const getPrevTimeRange = (times: number[]): [number, number] => {
    const duration = times[1] - times[0];
    return [times[0] - duration, times[0]];
  };

  const fetchData = async (silent = false) => {
    if (!otherConfig?.groupIds?.length) {
      setLoading(false);
      return;
    }
    // 取消上一次未完成的请求
    abortControllerRef.current?.abort();
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    try {
      if (!silent) setLoading(true);
      const times = globalTimeRangeRef.current;

      const params = getParams({
        config,
        times,
        logGroups: otherConfig.groupIds
      });
      const data = await getLogs(params, { signal: abortController.signal });
      setRawData(data);

      // KPI 卡片额外拉上一周期数据
      if (isKpiCard && times?.length === 2 && times[0] && times[1]) {
        prevAbortControllerRef.current?.abort();
        const prevAbortController = new AbortController();
        prevAbortControllerRef.current = prevAbortController;

        try {
          const [prevStart, prevEnd] = getPrevTimeRange(times);
          const prevParams = getParams({
            config,
            times: [prevStart, prevEnd],
            logGroups: otherConfig.groupIds
          });
          const prevResult = await getLogs(prevParams, {
            signal: prevAbortController.signal
          });
          setPrevData(prevResult);
        } catch (err: any) {
          if (err?.name === 'CanceledError' || err?.code === 'ERR_CANCELED')
            return;
          setPrevData(null);
        }
      }
    } catch (err: any) {
      if (err?.name === 'CanceledError' || err?.code === 'ERR_CANCELED') return;
      console.error('获取数据失败:', err);
      setRawData(null);
    } finally {
      if (!abortController.signal.aborted) {
        setLoading(false);
      }
    }
  };

  const getParams = (extra: {
    config: any;
    times: number[];
    logGroups: React.Key[];
  }) => {
    const times = extra.times;
    const startTime = times[0] ? new Date(times[0]).toISOString() : '';
    const endTime = times[1] ? new Date(times[1]).toISOString() : '';

    // 计算时间间隔并替换query中的${_time}变量
    let query = extra.config.dataSourceParams.query || '*';
    if (query.includes('${_time}') && startTime && endTime) {
      const timeInterval = calculateTimeInterval(startTime, endTime);
      query = query.replace(/\$\{_time\}/g, timeInterval);
    }
    query = buildInstanceFilterQuery(query, otherConfig.instanceIds);
    query = buildContainerFilterQuery(query, otherConfig.containerNames);

    const params: SearchParams = {
      start_time: startTime,
      end_time: endTime,
      field: '_stream',
      fields_limit: 5,
      log_groups: extra.logGroups,
      query: query,
      limit: 100
    };
    params.step = Math.round((times[1] - times[0]) / 100) + 'ms';
    return params;
  };

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Spin spinning={loading}></Spin>
      </div>
    );
  }

  const Component = chartType ? componentMap[chartType] : null;
  if (!Component) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-gray-500">未知的组件类型: {chartType}</div>
      </div>
    );
  }

  return (
    <Component
      rawData={rawData}
      prevData={isKpiCard ? prevData : undefined}
      loading={loading}
      config={config}
      globalTimeRange={globalTimeRange}
      refreshKey={refreshKey}
      onReady={onReady}
      editable={editable}
      {...otherProps}
    />
  );
};

export default WidgetWrapper;
