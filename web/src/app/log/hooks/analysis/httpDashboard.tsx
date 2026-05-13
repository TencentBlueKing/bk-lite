import { useTranslation } from '@/utils/i18n';
import { v4 as uuidv4 } from 'uuid';

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
    view_sets: [
      {
        h: 2,
        w: 3,
        x: 0,
        y: 0,
        i: uuidv4(),
        name: t('log.analysis.http.totalRequestCount'),
        moved: false,
        static: false,
        description: t('log.analysis.http.totalRequestCountDesc'),
        valueConfig: {
          chartType: 'httpKpiCard',
          dataSource: 1,
          icon: 'log',
          metricLabel: t('log.analysis.http.totalRequestCount'),
          displayMaps: {
            type: 'single',
            key: 'reqcount',
            value: 'reqcount',
            tooltipField: 'reqcount'
          },
          dataSourceParams: {
            query:
              'collect_type:"http" | stats by (_time:${_time}) count() as reqcount'
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 3,
        y: 0,
        i: uuidv4(),
        name: t('log.analysis.http.avgResponseTime'),
        moved: false,
        static: false,
        description: t('log.analysis.http.avgResponseTimeDesc'),
        valueConfig: {
          chartType: 'httpKpiCard',
          dataSource: 1,
          icon: 'clock-circle',
          color: '#155AEF',
          metricLabel: t('log.analysis.http.avgResponseTime'),
          displayMaps: {
            type: 'single',
            key: 'avg_duration',
            value: 'avg_duration',
            tooltipField: 'avg_duration'
          },
          dataSourceParams: {
            query:
              'collect_type:"http" event.duration:>0 | stats by (_time:${_time}) avg(event.duration) as avg_duration | math avg_duration / 1000000 as avg_duration'
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 6,
        y: 0,
        i: uuidv4(),
        name: t('log.analysis.http.totalTraffic'),
        moved: false,
        static: false,
        description: t('log.analysis.http.totalTrafficDesc'),
        valueConfig: {
          chartType: 'httpKpiCard',
          dataSource: 1,
          icon: 'swap',
          color: '#15B77E',
          metricLabel: t('log.analysis.http.totalTraffic'),
          displayMaps: {
            type: 'single',
            key: 'network_bytes',
            value: 'network_bytes',
            tooltipField: 'network_bytes'
          },
          dataSourceParams: {
            query:
              'collect_type:"http" | stats by (_time:${_time}) sum(network.bytes) as network_bytes | math network_bytes / 1024 as network_bytes'
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 9,
        y: 0,
        i: uuidv4(),
        name: t('log.analysis.http.captureErrors'),
        moved: false,
        static: false,
        description: t('log.analysis.http.captureErrorsDesc'),
        valueConfig: {
          chartType: 'httpKpiCard',
          dataSource: 1,
          icon: 'warning',
          color: '#f5222d',
          metricLabel: t('log.analysis.http.captureErrors'),
          displayMaps: {
            type: 'single',
            key: 'error_count',
            value: 'error_count',
            tooltipField: 'error_count'
          },
          dataSourceParams: {
            query:
              'collect_type:"http" | stats by (_time:${_time}) count() if (error.message:!="") as error_count'
          }
        }
      },
      {
        h: 3,
        w: 8,
        x: 0,
        y: 2,
        i: uuidv4(),
        name: t('log.analysis.http.requestLatencyTrend'),
        moved: false,
        static: false,
        description: t('log.analysis.http.requestLatencyTrendDesc'),
        valueConfig: {
          chartType: 'httpBarLine',
          dataSource: 1,
          displayMaps: {
            type: 'dual',
            key: 'reqcount',
            value: 'reqcount',
            barField: 'reqcount',
            lineField: 'avg_duration',
            barLabel: t('log.analysis.http.requestCount'),
            lineLabel: t('log.analysis.http.avgResponseTime')
          },
          dataSourceParams: {
            query:
              'collect_type:"http" | stats by (_time:${_time}) count() as reqcount, avg(event.duration) as avg_duration | math avg_duration / 1000000 as avg_duration'
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 8,
        y: 2,
        i: uuidv4(),
        name: t('log.analysis.http.statusCodeDistribution'),
        moved: false,
        static: false,
        description: t('log.analysis.http.statusCodeDistributionDesc'),
        valueConfig: {
          chartType: 'httpDonut',
          dataSource: 1,
          displayMaps: {
            type: 'single',
            key: 'http.response.status_code',
            value: 'reqcount',
            tooltipField: 'http.response.status_code'
          },
          dataSourceParams: {
            query:
              'collect_type:"http" | stats by (http.response.status_code) count() as reqcount | sort by (reqcount desc)'
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 0,
        y: 5,
        i: uuidv4(),
        name: t('log.analysis.http.methodDistribution'),
        moved: false,
        static: false,
        description: t('log.analysis.http.methodDistributionDesc'),
        valueConfig: {
          chartType: 'httpDonut',
          dataSource: 1,
          displayMaps: {
            type: 'single',
            key: 'http.request.method',
            value: 'reqcount',
            tooltipField: 'http.request.method'
          },
          dataSourceParams: {
            query:
              'collect_type:"http" | stats by (http.request.method) count() as reqcount | sort by (reqcount desc)'
          }
        }
      },
      {
        h: 3,
        w: 8,
        x: 4,
        y: 5,
        i: uuidv4(),
        name: t('log.analysis.http.topURLs'),
        moved: false,
        static: false,
        description: t('log.analysis.http.topURLsDesc'),
        valueConfig: {
          chartType: 'httpRequestTable',
          dataSource: 1,
          showIndex: true,
          columns: [
            {
              title: t('log.analysis.http.urlPath'),
              dataIndex: 'url.path',
              key: 'url.path'
            },
            {
              title: t('log.analysis.http.method'),
              dataIndex: 'http.request.method',
              key: 'http.request.method'
            },
            {
              title: t('log.analysis.http.requestCount'),
              dataIndex: 'reqcount',
              key: 'reqcount'
            },
            {
              title: t('log.analysis.http.avgResponseTime'),
              dataIndex: 'avg_duration',
              key: 'avg_duration'
            }
          ],
          dataSourceParams: {
            query:
              'collect_type:"http" | stats by (url.path,http.request.method) count() as reqcount, avg(event.duration) as avg_duration | math avg_duration / 1000000 as avg_duration | sort by (reqcount desc) | limit 15'
          }
        }
      },
      {
        h: 4,
        w: 6,
        x: 0,
        y: 8,
        i: uuidv4(),
        name: t('log.analysis.http.topSlowRequests'),
        moved: false,
        static: false,
        description: t('log.analysis.http.topSlowRequestsDesc'),
        valueConfig: {
          chartType: 'httpRequestTable',
          dataSource: 1,
          showIndex: true,
          columns: [
            {
              title: t('log.analysis.http.urlPath'),
              dataIndex: 'url.path',
              key: 'url.path'
            },
            {
              title: t('log.analysis.http.method'),
              dataIndex: 'http.request.method',
              key: 'http.request.method'
            },
            {
              title: t('log.analysis.http.statusCode'),
              dataIndex: 'http.response.status_code',
              key: 'http.response.status_code'
            },
            {
              title: t('log.analysis.http.responseTimeMs'),
              dataIndex: 'duration_ms',
              key: 'duration_ms'
            }
          ],
          dataSourceParams: {
            query:
              'collect_type:"http" event.duration:>0 | math event.duration / 1000000 as duration_ms | sort by (duration_ms desc) | limit 15'
          }
        }
      },
      {
        h: 4,
        w: 6,
        x: 6,
        y: 8,
        i: uuidv4(),
        name: t('log.analysis.http.captureIssueDetails'),
        moved: false,
        static: false,
        description: t('log.analysis.http.captureIssueDetailsDesc'),
        valueConfig: {
          chartType: 'httpRequestTable',
          dataSource: 1,
          showIndex: true,
          columns: [
            {
              title: t('log.analysis.http.timestamp'),
              dataIndex: '_time',
              key: '_time'
            },
            {
              title: t('log.analysis.http.urlPath'),
              dataIndex: 'url.path',
              key: 'url.path'
            },
            {
              title: t('log.analysis.http.method'),
              dataIndex: 'http.request.method',
              key: 'http.request.method'
            },
            {
              title: t('log.analysis.http.captureIssue'),
              dataIndex: 'error.message',
              key: 'error.message'
            }
          ],
          dataSourceParams: {
            query:
              'collect_type:"http" error.message:!="" | sort by (_time desc) | limit 15'
          }
        }
      }
    ]
  };
};
