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
        h: 3,
        w: 9,
        x: 0,
        y: 0,
        i: uuidv4(),
        name: t('log.analysis.http.requestVolumeTrend'),
        moved: false,
        static: false,
        description: t('log.analysis.http.requestVolumeTrendDesc'),
        valueConfig: {
          chartType: 'line',
          dataSource: 1,
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
        h: 3,
        w: 3,
        x: 9,
        y: 0,
        i: uuidv4(),
        name: t('log.analysis.http.totalRequestCount'),
        moved: false,
        static: false,
        description: t('log.analysis.http.totalRequestCountDesc'),
        valueConfig: {
          chartType: 'single',
          dataSource: 1,
          displayMaps: {
            type: 'single',
            key: 'reqcount',
            value: 'reqcount',
            tooltipField: 'reqcount'
          },
          dataSourceParams: {
            query: 'collect_type:"http" | stats count() as reqcount'
          }
        }
      },
      {
        h: 3,
        w: 6,
        x: 0,
        y: 3,
        i: uuidv4(),
        name: t('log.analysis.http.statusCodeDistribution'),
        moved: false,
        static: false,
        description: t('log.analysis.http.statusCodeDistributionDesc'),
        valueConfig: {
          chartType: 'pie',
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
        w: 6,
        x: 6,
        y: 3,
        i: uuidv4(),
        name: t('log.analysis.http.methodDistribution'),
        moved: false,
        static: false,
        description: t('log.analysis.http.methodDistributionDesc'),
        valueConfig: {
          chartType: 'pie',
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
        w: 12,
        x: 0,
        y: 6,
        i: uuidv4(),
        name: t('log.analysis.http.responseTimeTrend'),
        moved: false,
        static: false,
        description: t('log.analysis.http.responseTimeTrendDesc'),
        valueConfig: {
          chartType: 'line',
          dataSource: 1,
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
        h: 4,
        w: 6,
        x: 0,
        y: 9,
        i: uuidv4(),
        name: t('log.analysis.http.topSourceIPs'),
        moved: false,
        static: false,
        description: t('log.analysis.http.topSourceIPsDesc'),
        valueConfig: {
          chartType: 'table',
          dataSource: 1,
          showIndex: true,
          columns: [
            {
              title: t('log.analysis.http.sourceIP'),
              dataIndex: 'source.ip',
              key: 'source.ip'
            },
            {
              title: t('log.analysis.http.requestCount'),
              dataIndex: 'reqcount',
              key: 'reqcount'
            }
          ],
          dataSourceParams: {
            query:
              'collect_type:"http" | stats by (source.ip) count() as reqcount | sort by (reqcount desc) | limit 20'
          }
        }
      },
      {
        h: 4,
        w: 6,
        x: 6,
        y: 9,
        i: uuidv4(),
        name: t('log.analysis.http.topURLs'),
        moved: false,
        static: false,
        description: t('log.analysis.http.topURLsDesc'),
        valueConfig: {
          chartType: 'table',
          dataSource: 1,
          showIndex: true,
          columns: [
            {
              title: t('log.analysis.http.urlPath'),
              dataIndex: 'url.path',
              key: 'url.path'
            },
            {
              title: t('log.analysis.http.requestCount'),
              dataIndex: 'reqcount',
              key: 'reqcount'
            }
          ],
          dataSourceParams: {
            query:
              'collect_type:"http" | stats by (url.path) count() as reqcount | sort by (reqcount desc) | limit 20'
          }
        }
      },
      {
        h: 4,
        w: 12,
        x: 0,
        y: 13,
        i: uuidv4(),
        name: t('log.analysis.http.topSlowRequests'),
        moved: false,
        static: false,
        description: t('log.analysis.http.topSlowRequestsDesc'),
        valueConfig: {
          chartType: 'table',
          dataSource: 1,
          showIndex: true,
          columns: [
            {
              title: t('log.analysis.http.sourceIP'),
              dataIndex: 'source.ip',
              key: 'source.ip'
            },
            {
              title: t('log.analysis.http.destinationIP'),
              dataIndex: 'destination.ip',
              key: 'destination.ip'
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
              'collect_type:"http" event.duration:>0 | math event.duration / 1000000 as duration_ms | sort by (duration_ms desc) | limit 20'
          }
        }
      }
    ]
  };
};
