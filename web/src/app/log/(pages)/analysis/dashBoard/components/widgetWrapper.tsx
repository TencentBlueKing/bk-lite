import React, { useState, useEffect, useRef, useMemo } from 'react';
import { Spin } from 'antd';
import { BaseWidgetProps } from '@/app/log/types/analysis';
import useSearchApi from '@/app/log/api/search';
import useApiClient from '@/utils/request';
import {
  calculateLogTimeInterval,
  getDashboardQueryLimit
} from '../timeRangeUtils';
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
  HttpRequestTable,
  HttpRequestTrend,
  HttpStatusCategoryDonut,
  HttpLatencyBar,
  HttpStatusTrend
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
import {
  MongodbKpiCard,
  MongodbBarLine,
  MongodbBar,
  MongodbPie,
  MongodbTable,
  MongodbTrend
} from '../widgets/mongodb';
import {
  KafkaKpiCard,
  KafkaBarLine,
  KafkaBar,
  KafkaPie,
  KafkaTable,
  KafkaTrend
} from '../widgets/kafka';
import {
  ElasticsearchKpiCard,
  ElasticsearchPie,
  ElasticsearchTable,
  ElasticsearchTrend
} from '../widgets/elasticsearch';
import {
  SyslogKpiCard,
  SyslogPie,
  SyslogTable,
  SyslogTrend
} from '../widgets/syslog';
import {
  ApacheKpiCard,
  ApachePie,
  ApacheTable,
  ApacheTrend
} from '../widgets/apache';
import {
  PostgresqlKpiCard,
  PostgresqlPie,
  PostgresqlTable,
  PostgresqlTrend
} from '../widgets/postgresql';
import {
  NginxKpiCard,
  NginxPie,
  NginxTable,
  NginxTrend
} from '../widgets/nginx';
import {
  FileIntegrityKpiCard,
  FileIntegrityPie,
  FileIntegrityTable,
  FileIntegrityTrend
} from '../widgets/fileIntegrity';
import {
  RabbitmqBar,
  RabbitmqKpiCard,
  RabbitmqPie,
  RabbitmqTable,
  RabbitmqTrend
} from '../widgets/rabbitmq';
import {
  WindowsEventBar,
  WindowsEventKpiCard,
  WindowsEventPie,
  WindowsEventTable,
  WindowsEventTrend
} from '../widgets/windowsEvent';
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
  httpRequestTrend: HttpRequestTrend,
  httpStatusCategoryDonut: HttpStatusCategoryDonut,
  httpLatencyBar: HttpLatencyBar,
  httpStatusTrend: HttpStatusTrend,
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
  redisNodeCompareBar: RedisNodeCompareBar,
  mongodbKpiCard: MongodbKpiCard,
  mongodbBarLine: MongodbBarLine,
  mongodbBar: MongodbBar,
  mongodbPie: MongodbPie,
  mongodbTable: MongodbTable,
  mongodbTrend: MongodbTrend,
  kafkaKpiCard: KafkaKpiCard,
  kafkaBarLine: KafkaBarLine,
  kafkaBar: KafkaBar,
  kafkaPie: KafkaPie,
  kafkaTable: KafkaTable,
  kafkaTrend: KafkaTrend,
  elasticsearchKpiCard: ElasticsearchKpiCard,
  elasticsearchPie: ElasticsearchPie,
  elasticsearchTable: ElasticsearchTable,
  elasticsearchTrend: ElasticsearchTrend,
  syslogKpiCard: SyslogKpiCard,
  syslogPie: SyslogPie,
  syslogTable: SyslogTable,
  syslogTrend: SyslogTrend,
  apacheKpiCard: ApacheKpiCard,
  apachePie: ApachePie,
  apacheTable: ApacheTable,
  apacheTrend: ApacheTrend,
  postgresqlKpiCard: PostgresqlKpiCard,
  postgresqlPie: PostgresqlPie,
  postgresqlTable: PostgresqlTable,
  postgresqlTrend: PostgresqlTrend,
  nginxKpiCard: NginxKpiCard,
  nginxPie: NginxPie,
  nginxTable: NginxTable,
  nginxTrend: NginxTrend,
  fileIntegrityKpiCard: FileIntegrityKpiCard,
  fileIntegrityPie: FileIntegrityPie,
  fileIntegrityTable: FileIntegrityTable,
  fileIntegrityTrend: FileIntegrityTrend,
  rabbitmqBar: RabbitmqBar,
  rabbitmqKpiCard: RabbitmqKpiCard,
  rabbitmqPie: RabbitmqPie,
  rabbitmqTable: RabbitmqTable,
  rabbitmqTrend: RabbitmqTrend,
  windowsEventBar: WindowsEventBar,
  windowsEventKpiCard: WindowsEventKpiCard,
  windowsEventPie: WindowsEventPie,
  windowsEventTable: WindowsEventTable,
  windowsEventTrend: WindowsEventTrend
};

const formatRatio = (value: number) => `${value.toFixed(1)}%`;

const withTopRatios = (rows: any[], countField = 'count') => {
  if (!Array.isArray(rows) || !rows.length) return rows;
  const total = rows.reduce(
    (sum, item) => sum + Number(item?.[countField] || 0),
    0
  );
  if (!total) {
    return rows.map((item) => ({ ...item, ratio: '0.0%' }));
  }
  return rows.map((item) => ({
    ...item,
    ratio: formatRatio((Number(item?.[countField] || 0) / total) * 100)
  }));
};

const WINDOWS_EVENT_NAMES: Record<string, string> = {
  '4624': '成功登录',
  '4625': '登录失败',
  '7031': '服务异常终止',
  '1000': '应用程序错误',
  '1102': '安全日志已清除'
};

const transformDataByMode = (data: any, config: any) => {
  const mode = config?.dataSourceParams?.transformMode;
  if (!mode) return data;

  if (mode === 'esNodes') {
    const serverRows = Array.isArray(data?.serverRows) ? data.serverRows : [];
    const slowRows = Array.isArray(data?.slowRows) ? data.slowRows : [];
    const slowCountMap = new Map(
      slowRows.map((row: any) => [row.instance_id, Number(row.slow_count || 0)])
    );

    return serverRows.map((row: any) => ({
      ...row,
      slow_count:
        slowCountMap.get(row['elasticsearch.server.node.name']) ||
        slowCountMap.get(row.instance_id) ||
        0,
      gc_count: 0,
      ratio: '0.0%'
    }));
  }

  if (mode === 'mongoTopComponents' || mode === 'mongoTopMessages') {
    return withTopRatios(data, 'count');
  }

  if (mode === 'mongoTopContexts') {
    return withTopRatios(data, 'count');
  }

  if (mode === 'esTopComponents') {
    const rows = Array.isArray(data) ? data : [];
    const total = rows.reduce(
      (sum, item) =>
        sum + Number(item?.error_count || 0) + Number(item?.warn_count || 0),
      0
    );
    if (!total) {
      return rows.map((item) => ({ ...item, ratio: '0.0%' }));
    }
    return rows.map((item) => ({
      ...item,
      ratio: formatRatio(
        ((Number(item?.error_count || 0) + Number(item?.warn_count || 0)) /
          total) *
          100
      )
    }));
  }

  if (mode === 'topRatios') {
    const countField = config?.dataSourceParams?.countField || 'count';
    return withTopRatios(data, countField);
  }

  if (mode === 'windowsEventIds') {
    const rows = withTopRatios(Array.isArray(data) ? data : [], 'count');
    return rows.map((item: any) => {
      const eventId = String(item?.['winlog.event_id'] || item?.event_id || '');
      return {
        ...item,
        event_id: eventId,
        event_name: WINDOWS_EVENT_NAMES[eventId] || '其他事件'
      };
    });
  }

  if (mode === 'rabbitmqKeywordCounts') {
    return Object.entries(data || {})
      .map(([keyword_type, rows]) => {
        const firstRow = Array.isArray(rows) ? rows[0] : null;
        return {
          keyword_type,
          count: Number(firstRow?.count || 0)
        };
      })
      .filter((item) => item.count > 0)
      .sort((a, b) => b.count - a.count);
  }

  if (mode === 'rabbitmqRecentEvents') {
    const rows = Array.isArray(data) ? data : [];
    return rows.map((item) => {
      const message = String(item?.['rabbitmq.log.message'] || item?._msg || '').toLowerCase();
      const keyword =
        (message.includes('access_refused') || message.includes('credential'))
          ? 'auth'
          : message.includes('connection')
            ? 'connection'
            : message.includes('channel')
              ? 'channel'
              : message.includes('queue')
                ? 'queue'
                : message.includes('heartbeat')
                  ? 'heartbeat'
                  : message.includes('memory')
                    ? 'memory'
                    : message.includes('cluster')
                      ? 'cluster'
                      : 'connection';
      return {
        ...item,
        keyword_type: keyword
      };
    });
  }

  if (mode === 'statusGroupCounts') {
    const labelMap: Record<string, string> = {
      '2xx': '2xx',
      '4xx': '4xx',
      '5xx': '5xx'
    };

    return Object.entries(data || {})
      .map(([key, rows]) => {
        const firstRow = Array.isArray(rows) ? rows[0] : null;
        return {
          status_group: labelMap[key] || key,
          count: Number(firstRow?.count || 0)
        };
      })
      .filter((item) => item.count > 0)
      .sort((a, b) => b.count - a.count);
  }

  if (mode === 'highRiskRatio') {
    const rows = Array.isArray(data) ? data : [];
    return rows.map((item) => {
      const total = Number(item?.total_count || 0);
      const high = Number(item?.high_count || 0);
      return {
        ...item,
        ratio: total ? formatRatio((high / total) * 100) : '0.0%'
      };
    });
  }

  return data;
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
    'redisKpiCard',
    'mongodbKpiCard',
    'kafkaKpiCard',
    'elasticsearchKpiCard',
    'syslogKpiCard',
    'apacheKpiCard',
    'postgresqlKpiCard',
    'nginxKpiCard',
    'fileIntegrityKpiCard',
    'rabbitmqKpiCard',
    'windowsEventKpiCard'
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
    if (
      config?.dataSource &&
      !isLoading &&
      otherConfig.groupIds
    ) {
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

  const buildSingleParams = (
    queryText: string,
    times: number[],
    logGroups: React.Key[]
  ): SearchParams => {
    const startTime = times[0] ? new Date(times[0]).toISOString() : '';
    const endTime = times[1] ? new Date(times[1]).toISOString() : '';

    let query = queryText || '*';
    let timeInterval = '';
    if (query.includes('${_time}') && startTime && endTime) {
      timeInterval = calculateLogTimeInterval(times[0], times[1]);
      query = query.replace(/\$\{_time\}/g, timeInterval);
    }
    query = buildInstanceFilterQuery(query, otherConfig.instanceIds);
    query = buildContainerFilterQuery(query, otherConfig.containerNames);

    const params: SearchParams = {
      start_time: startTime,
      end_time: endTime,
      field: '_stream',
      fields_limit: 5,
      log_groups: logGroups,
      query: query,
      limit: getDashboardQueryLimit(queryText)
    };
    params.step =
      timeInterval || Math.round((times[1] - times[0]) / 100) + 'ms';
    return params;
  };

  const isMultiQuery = !!(config?.dataSourceParams?.queries?.length);

  const getParams = (extra: {
    config: any;
    times: number[];
    logGroups: React.Key[];
  }) => {
    return buildSingleParams(
      extra.config.dataSourceParams.query,
      extra.times,
      extra.logGroups
    );
  };

  const getMultiQueryParamsList = (extra: {
    config: any;
    times: number[];
    logGroups: React.Key[];
  }): { key: string; params: SearchParams }[] => {
    const queries: { key: string; query: string; searchQuery?: string }[] =
      extra.config.dataSourceParams.queries;
    return queries.map((entry) => ({
      key: entry.key,
      params: buildSingleParams(entry.query, extra.times, extra.logGroups)
    }));
  };

  const fetchMultiQueryData = async (
    configObj: any,
    times: number[],
    logGroups: React.Key[],
    signal: AbortSignal
  ): Promise<Record<string, any>> => {
    const paramsList = getMultiQueryParamsList({
      config: configObj,
      times,
      logGroups
    });
    const results = await Promise.all(
      paramsList.map((entry) =>
        getLogs(entry.params, { signal }).then((data) => ({
          key: entry.key,
          data
        }))
      )
    );
    const merged: Record<string, any> = {};
    for (const r of results) {
      merged[r.key] = r.data;
    }
    return merged;
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

      let data: any;
      if (isMultiQuery) {
        data = await fetchMultiQueryData(
          config,
          times,
          otherConfig.groupIds,
          abortController.signal
        );
      } else {
        const params = getParams({
          config,
          times,
          logGroups: otherConfig.groupIds
        });
        data = await getLogs(params, { signal: abortController.signal });
      }
      setRawData(transformDataByMode(data, config));

      // KPI 卡片额外拉上一周期数据
      if (isKpiCard && times?.length === 2 && times[0] && times[1]) {
        prevAbortControllerRef.current?.abort();
        const prevAbortController = new AbortController();
        prevAbortControllerRef.current = prevAbortController;

        try {
          const [prevStart, prevEnd] = getPrevTimeRange(times);
          let prevResult: any;
          if (isMultiQuery) {
            prevResult = await fetchMultiQueryData(
              config,
              [prevStart, prevEnd],
              otherConfig.groupIds,
              prevAbortController.signal
            );
          } else {
            const prevParams = getParams({
              config,
              times: [prevStart, prevEnd],
              logGroups: otherConfig.groupIds
            });
            prevResult = await getLogs(prevParams, {
              signal: prevAbortController.signal
            });
          }
          setPrevData(transformDataByMode(prevResult, config));
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
      otherConfig={otherConfig}
      globalTimeRange={globalTimeRange}
      refreshKey={refreshKey}
      onReady={onReady}
      editable={editable}
      {...otherProps}
    />
  );
};

export default WidgetWrapper;
