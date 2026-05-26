import { useTranslation } from '@/utils/i18n';
import { LayoutItem } from '@/app/log/types/analysis';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';

export interface HttpDashboardSection extends LayoutItem {
  colSpan: number;
  minHeight: number;
  compact?: boolean;
  showDescription?: boolean;
}

const trimTrailingZeros = (value: string) =>
  value.replace(/\.0+$|(?<=\.\d*[1-9])0+$/g, '');

const formatCompactNumber = (value: number) => {
  if (!Number.isFinite(value)) return '--';

  const absValue = Math.abs(value);
  const units = [
    { threshold: 1_000_000_000, suffix: 'B' },
    { threshold: 1_000_000, suffix: 'M' },
    { threshold: 1_000, suffix: 'k' }
  ];

  for (const unit of units) {
    if (absValue >= unit.threshold) {
      const scaled = value / unit.threshold;
      return `${trimTrailingZeros(scaled.toFixed(Math.abs(scaled) >= 100 ? 0 : 1))}${unit.suffix}`;
    }
  }

  return trimTrailingZeros(value.toFixed(value >= 100 ? 0 : 1));
};

const formatInteger = (value: number) => formatCompactNumber(Math.round(value));

const formatCount = (value: number) =>
  Number.isFinite(value) ? Math.round(value).toLocaleString() : '--';

const formatRatioValue = (value: number) =>
  Number.isFinite(value) ? `${trimTrailingZeros(value.toFixed(1))}%` : '--';

const formatPercent = (value: number) =>
  Number.isFinite(value) ? `${trimTrailingZeros(value.toFixed(1))}%` : '--';

const formatMs = (value: number) => {
  if (!Number.isFinite(value)) return '--';

  if (Math.abs(value) >= 1000) {
    return `${trimTrailingZeros((value / 1000).toFixed(1))}s`;
  }

  return `${trimTrailingZeros(value.toFixed(value >= 100 ? 0 : 1))}ms`;
};

const formatMsValue = (value: number) => {
  if (!Number.isFinite(value)) return '--';

  return Math.round(value).toLocaleString();
};

const formatTraffic = (value: number) => {
  if (!Number.isFinite(value)) return '--';

  const units = [
    { threshold: 1024 * 1024, suffix: 'TB' },
    { threshold: 1024, suffix: 'GB' },
    { threshold: 1, suffix: 'MB' }
  ];

  for (const unit of units) {
    if (Math.abs(value) >= unit.threshold) {
      const scaled = value / unit.threshold;
      return `${trimTrailingZeros(scaled.toFixed(Math.abs(scaled) >= 100 ? 0 : 1))}${unit.suffix}`;
    }
  }

  return `${trimTrailingZeros((value * 1024).toFixed(value * 1024 >= 100 ? 0 : 1))}KB`;
};

const toDisplay = (value: unknown, fallback = '--') => {
  const text = String(value ?? '').trim();
  return text || fallback;
};

export const getHttpDashboardSections = (
  t: (key: string) => string
): HttpDashboardSection[] => {
  const baseQuery = 'collect_type:"http"';
  const urlScopedQuery = 'collect_type:"http" url.path:*';
  const durationQuery = 'collect_type:"http" event.duration:>0';
  const urlScopedDurationQuery =
    'collect_type:"http" url.path:* event.duration:>0';
  const createMetricColumn = (
    title: string,
    dataIndex: string,
    key: string,
    width: number,
    render: (value: unknown) => React.ReactNode
  ) => ({
    title,
    dataIndex,
    key,
    width,
    render
  });
  const urlPathColumn = {
    title: t('log.analysis.http.urlPath'),
    dataIndex: 'url.path',
    key: 'url.path',
    width: 168,
    render: (value: unknown) => {
      const text = toDisplay(value);

      return (
        <EllipsisWithTooltip text={text} className="max-w-[168px] truncate" />
      );
    }
  };

  return [
    {
      i: 'http-total-requests',
      x: 0,
      y: 0,
      w: 2,
      h: 2,
      colSpan: 2,
      minHeight: 176,
      compact: false,
      showDescription: true,
      name: t('log.analysis.http.totalRequestCount'),
      description: t('log.analysis.http.totalRequestCountDesc'),
      valueConfig: {
        chartType: 'httpKpiCard',
        dataSource: 1,
        color: 'primary',
        calculation: 'sum',
        valueField: 'reqcount',
        valueFormatter: formatInteger,
        dataSourceParams: {
          searchQuery: baseQuery,
          query: `${baseQuery} | stats by (_time:\${_time}) count() as reqcount`
        }
      }
    },
    {
      i: 'http-success-rate',
      x: 2,
      y: 0,
      w: 2,
      h: 2,
      colSpan: 2,
      minHeight: 176,
      compact: false,
      showDescription: true,
      name: t('log.analysis.http.successRate'),
      description: t('log.analysis.http.successRateDesc'),
      valueConfig: {
        chartType: 'httpKpiCard',
        dataSource: 1,
        color: 'success',
        calculation: 'ratio',
        numeratorField: 'success_count',
        denominatorField: 'total_count',
        multiplier: 100,
        valueFormatter: formatPercent,
        dataSourceParams: {
          searchQuery: baseQuery,
          query:
            `${baseQuery} | stats by (_time:\${_time}) count() as total_count, ` +
            `count() if (status:"OK") as success_count`
        }
      }
    },
    {
      i: 'http-error-rate',
      x: 4,
      y: 0,
      w: 2,
      h: 2,
      colSpan: 2,
      minHeight: 176,
      compact: false,
      showDescription: true,
      name: t('log.analysis.http.errorRate'),
      description: t('log.analysis.http.errorRateDesc'),
      valueConfig: {
        chartType: 'httpKpiCard',
        dataSource: 1,
        color: 'danger',
        calculation: 'ratio',
        numeratorField: 'error_count',
        denominatorField: 'total_count',
        multiplier: 100,
        valueFormatter: formatPercent,
        dataSourceParams: {
          searchQuery: baseQuery,
          query:
            `${baseQuery} | stats by (_time:\${_time}) count() as total_count, ` +
            `count() if (status:"Error") as error_count`
        }
      }
    },
    {
      i: 'http-p95-latency',
      x: 6,
      y: 0,
      w: 2,
      h: 2,
      colSpan: 2,
      minHeight: 176,
      compact: false,
      showDescription: true,
      name: t('log.analysis.http.p95ResponseTime'),
      description: t('log.analysis.http.p95ResponseTimeDesc'),
      valueConfig: {
        chartType: 'httpKpiCard',
        dataSource: 1,
        color: 'accent',
        calculation: 'weightedAverage',
        valueField: 'p95_duration',
        weightField: 'reqcount',
        valueFormatter: formatMs,
        dataSourceParams: {
          searchQuery: durationQuery,
          queries: [
            {
              key: 'count',
              query: `${durationQuery} | stats by (_time:\${_time}) count() as reqcount`
            },
            {
              key: 'p95',
              query:
                `${durationQuery} | stats by (_time:\${_time}) quantile(0.95, event.duration) if (event.duration:*) as p95_duration ` +
                `| math p95_duration / 1000000 as p95_duration`
            }
          ]
        }
      }
    },
    {
      i: 'http-total-traffic',
      x: 8,
      y: 0,
      w: 2,
      h: 2,
      colSpan: 2,
      minHeight: 176,
      compact: false,
      showDescription: true,
      name: t('log.analysis.http.totalTraffic'),
      description: t('log.analysis.http.totalTrafficMbDesc'),
      valueConfig: {
        chartType: 'httpKpiCard',
        dataSource: 1,
        color: 'info',
        calculation: 'sum',
        valueField: 'total_traffic_mb',
        valueFormatter: formatTraffic,
        dataSourceParams: {
          searchQuery: baseQuery,
          query:
            `${baseQuery} | stats by (_time:\${_time}) sum(network.bytes) as total_traffic_mb ` +
            `| math total_traffic_mb / 1024 / 1024 as total_traffic_mb`
        }
      }
    },
    {
      i: 'http-avg-response-time',
      x: 10,
      y: 0,
      w: 2,
      h: 2,
      colSpan: 2,
      minHeight: 176,
      compact: false,
      showDescription: true,
      name: t('log.analysis.http.avgResponseTime'),
      description: t('log.analysis.http.avgResponseTimeDesc'),
      valueConfig: {
        chartType: 'httpKpiCard',
        dataSource: 1,
        color: 'warning',
        calculation: 'weightedAverage',
        valueField: 'avg_duration',
        weightField: 'reqcount',
        valueFormatter: formatMs,
        dataSourceParams: {
          searchQuery: durationQuery,
          query:
            `${durationQuery} | stats by (_time:\${_time}) count() as reqcount, avg(event.duration) as avg_duration ` +
            `| math avg_duration / 1000000 as avg_duration`
        }
      }
    },
    {
      i: 'http-request-trend',
      x: 0,
      y: 2,
      w: 8,
      h: 3,
      colSpan: 8,
      minHeight: 300,
      name: t('log.analysis.http.requestTrendTitle'),
      valueConfig: {
        chartType: 'httpRequestTrend',
        dataSource: 1,
        displayMaps: {
          barField: 'reqcount',
          avgField: 'avg_duration',
          p95Field: 'p95_duration',
          barLabel: t('log.analysis.http.requestCount'),
          avgLabel: t('log.analysis.http.avgResponseTime'),
          p95Label: t('log.analysis.http.p95ResponseTime')
        },
        dataSourceParams: {
          searchQuery: durationQuery,
          query:
            `${durationQuery} | stats by (_time:\${_time}) count() as reqcount, avg(event.duration) as avg_duration, quantile(0.95, event.duration) if (event.duration:*) as p95_duration ` +
            `| math avg_duration / 1000000 as avg_duration | math p95_duration / 1000000 as p95_duration`
        }
      }
    },
    {
      i: 'http-status-distribution',
      x: 8,
      y: 2,
      w: 4,
      h: 3,
      colSpan: 4,
      minHeight: 300,
      name: t('log.analysis.http.statusCodeCategoryDistribution'),
      valueConfig: {
        chartType: 'httpStatusCategoryDonut',
        dataSource: 1,
        displayMaps: {
          labels: {
            status_2xx: t('log.analysis.http.status2xxSuccess'),
            status_3xx: t('log.analysis.http.status3xxRedirect'),
            status_4xx: t('log.analysis.http.status4xxClientError'),
            status_5xx: t('log.analysis.http.status5xxServerError'),
            status_other: t('log.analysis.http.otherUnknown')
          }
        },
        dataSourceParams: {
          searchQuery: baseQuery,
          query: `${baseQuery} | stats by (http.response.status_code) count() as reqcount | sort by (reqcount desc)`
        }
      }
    },
    {
      i: 'http-top-urls',
      x: 0,
      y: 6,
      w: 4,
      h: 3,
      colSpan: 4,
      minHeight: 296,
      name: t('log.analysis.http.topFrequentUrls'),
      valueConfig: {
        chartType: 'httpRequestTable',
        dataSource: 1,
        showIndex: true,
        columns: [
          urlPathColumn,
          createMetricColumn(
            t('log.analysis.http.requestCountTimes'),
            'reqcount',
            'reqcount',
            108,
            (value: unknown) => formatCount(Number(value || 0))
          ),
          createMetricColumn(
            t('log.analysis.http.share'),
            'req_ratio',
            'req_ratio',
            72,
            (value: unknown) => formatRatioValue(Number(value || 0))
          ),
          createMetricColumn(
            t('log.analysis.http.avgResponseTimeMs'),
            'avg_duration',
            'avg_duration',
            156,
            (value: unknown) => formatMsValue(Number(value || 0))
          ),
          createMetricColumn(
            t('log.analysis.http.p95ResponseTimeMs'),
            'p95_duration',
            'p95_duration',
            148,
            (value: unknown) => formatMsValue(Number(value || 0))
          )
        ],
        dataSourceParams: {
          searchQuery: urlScopedQuery,
          queries: [
            {
              key: 'detail',
              query:
                `${urlScopedQuery} | stats by (url.path) count() as reqcount, avg(event.duration) as avg_duration, quantile(0.95, event.duration) if (event.duration:*) as p95_duration ` +
                `| math avg_duration / 1000000 as avg_duration | math p95_duration / 1000000 as p95_duration ` +
                `| sort by (reqcount desc) | limit 10`
            },
            {
              key: 'total',
              query: `${urlScopedQuery} | stats count() as total_reqcount`
            }
          ]
        }
      }
    },
    {
      i: 'http-slow-urls',
      x: 4,
      y: 6,
      w: 4,
      h: 3,
      colSpan: 4,
      minHeight: 296,
      name: t('log.analysis.http.topSlowUrls'),
      valueConfig: {
        chartType: 'httpRequestTable',
        dataSource: 1,
        showIndex: true,
        columns: [
          urlPathColumn,
          createMetricColumn(
            t('log.analysis.http.requestCountTimes'),
            'reqcount',
            'reqcount',
            108,
            (value: unknown) => formatCount(Number(value || 0))
          ),
          createMetricColumn(
            t('log.analysis.http.avgResponseTimeMs'),
            'avg_duration',
            'avg_duration',
            156,
            (value: unknown) => formatMsValue(Number(value || 0))
          ),
          createMetricColumn(
            t('log.analysis.http.p95ResponseTimeMs'),
            'p95_duration',
            'p95_duration',
            148,
            (value: unknown) => formatMsValue(Number(value || 0))
          )
        ],
        dataSourceParams: {
          searchQuery: urlScopedDurationQuery,
          queries: [
            {
              key: 'base',
              query:
                `${urlScopedDurationQuery} | stats by (url.path) count() as reqcount, avg(event.duration) as avg_duration ` +
                `| math avg_duration / 1000000 as avg_duration ` +
                `| sort by (avg_duration desc) | limit 20`
            },
            {
              key: 'p95',
              query:
                `${urlScopedDurationQuery} | stats by (url.path) quantile(0.95, event.duration) as p95_duration ` +
                `| math p95_duration / 1000000 as p95_duration ` +
                `| sort by (p95_duration desc) | limit 20`
            }
          ]
        }
      }
    },
    {
      i: 'http-error-urls',
      x: 8,
      y: 6,
      w: 4,
      h: 3,
      colSpan: 4,
      minHeight: 296,
      name: t('log.analysis.http.topErrorUrls'),
      valueConfig: {
        chartType: 'httpRequestTable',
        dataSource: 1,
        showIndex: true,
        columns: [
          urlPathColumn,
          createMetricColumn(
            t('log.analysis.http.requestCountTimes'),
            'reqcount',
            'reqcount',
            108,
            (value: unknown) => formatCount(Number(value || 0))
          ),
          createMetricColumn(
            t('log.analysis.http.errorCountTimes'),
            'error_count',
            'error_count',
            104,
            (value: unknown) => formatCount(Number(value || 0))
          ),
          createMetricColumn(
            t('log.analysis.http.errorRateSimple'),
            'error_rate',
            'error_rate',
            92,
            (value: unknown) => formatRatioValue(Number(value || 0))
          ),
          createMetricColumn(
            t('log.analysis.http.primaryStatusCode'),
            'primary_status_code',
            'primary_status_code',
            168,
            (value: unknown) => toDisplay(value)
          )
        ],
        dataSourceParams: {
          searchQuery: `${urlScopedQuery} status:"Error"`,
          queries: [
            {
              key: 'errors',
              query:
                `${urlScopedQuery} | stats by (url.path) count() as reqcount, count() if (status:"Error") as error_count ` +
                `| filter error_count:>0 | math error_count / reqcount * 100 as error_rate ` +
                `| sort by (error_rate desc) | limit 10`
            },
            {
              key: 'status',
              query:
                `${urlScopedQuery} status:"Error" http.response.status_code:* ` +
                `| stats by (url.path, http.response.status_code) count() as status_count ` +
                `| sort by (status_count desc)`
            }
          ]
        }
      }
    },
    {
      i: 'http-method-distribution',
      x: 0,
      y: 10,
      w: 4,
      h: 3,
      colSpan: 4,
      minHeight: 288,
      name: t('log.analysis.http.methodDistribution'),
      valueConfig: {
        chartType: 'httpDonut',
        dataSource: 1,
        displayMaps: {
          key: 'http.request.method',
          value: 'reqcount',
          tooltipField: 'http.request.method',
          emptyLabel: t('log.analysis.http.unknown')
        },
        dataSourceParams: {
          searchQuery: baseQuery,
          query: `${baseQuery} | stats by (http.request.method) count() as reqcount | sort by (reqcount desc)`
        }
      }
    },
    {
      i: 'http-latency-distribution',
      x: 4,
      y: 10,
      w: 3,
      h: 3,
      colSpan: 3,
      minHeight: 288,
      name: t('log.analysis.http.responseTimeDistribution'),
      valueConfig: {
        chartType: 'httpLatencyBar',
        dataSource: 1,
        displayMaps: {
          key: 'bucket',
          value: 'count',
          buckets: [
            { field: 'bucket_lt50', label: '0-50ms' },
            { field: 'bucket_50_100', label: '50-100ms' },
            { field: 'bucket_100_200', label: '100-200ms' },
            { field: 'bucket_200_500', label: '200-500ms' },
            { field: 'bucket_500_1000', label: '500ms-1s' },
            { field: 'bucket_1000_2000', label: '1-2s' },
            { field: 'bucket_2000_5000', label: '2-5s' },
            { field: 'bucket_gt5000', label: '>5s' }
          ]
        },
        dataSourceParams: {
          searchQuery: durationQuery,
          query:
            `${durationQuery} | math event.duration / 1000000 as duration_ms | stats ` +
            `count() if (duration_ms:<50) as bucket_lt50, ` +
            `count() if (duration_ms:>=50 duration_ms:<100) as bucket_50_100, ` +
            `count() if (duration_ms:>=100 duration_ms:<200) as bucket_100_200, ` +
            `count() if (duration_ms:>=200 duration_ms:<500) as bucket_200_500, ` +
            `count() if (duration_ms:>=500 duration_ms:<1000) as bucket_500_1000, ` +
            `count() if (duration_ms:>=1000 duration_ms:<2000) as bucket_1000_2000, ` +
            `count() if (duration_ms:>=2000 duration_ms:<5000) as bucket_2000_5000, ` +
            `count() if (duration_ms:>=5000) as bucket_gt5000`
        }
      }
    },
    {
      i: 'http-status-trend',
      x: 7,
      y: 10,
      w: 5,
      h: 3,
      colSpan: 5,
      minHeight: 288,
      name: t('log.analysis.http.statusCodeTrend'),
      valueConfig: {
        chartType: 'httpStatusTrend',
        dataSource: 1,
        displayMaps: {
          labels: {
            status_2xx: t('log.analysis.http.status2xxSuccess'),
            status_3xx: t('log.analysis.http.status3xxRedirect'),
            status_4xx: t('log.analysis.http.status4xxClientError'),
            status_5xx: t('log.analysis.http.status5xxServerError'),
            status_other: t('log.analysis.http.otherUnknown')
          }
        },
        dataSourceParams: {
          searchQuery: baseQuery,
          query: `${baseQuery} | stats by (_time:\${_time},http.response.status_code) count() as reqcount | sort by (_time asc)`
        }
      }
    }
  ];
};

export const useHttpDashboard = () => {
  const { t } = useTranslation();

  return {
    name: t('log.analysis.http.dashboardName'),
    desc: '',
    id: '4',
    category: 'network',
    categoryName: t('log.analysis.category.network'),
    collectTypeName: 'http',
    filters: {},
    other: {},
    view_sets: getHttpDashboardSections(t)
  };
};
