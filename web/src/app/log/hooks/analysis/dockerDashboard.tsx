import { useTranslation } from '@/utils/i18n';
import { v4 as uuidv4 } from 'uuid';

export const useDockerDashboard = () => {
  const { t } = useTranslation();

  return {
    name: t('log.analysis.docker.dashboardName'),
    desc: '',
    id: '6',
    category: 'container',
    categoryName: t('log.analysis.category.container'),
    collectTypeName: 'docker',
    filters: {},
    other: {},
    view_sets: [
      {
        h: 2,
        w: 3,
        x: 0,
        y: 0,
        i: uuidv4(),
        name: t('log.analysis.docker.totalLogCount'),
        moved: false,
        static: false,
        description: t('log.analysis.docker.totalLogCountDesc'),
        valueConfig: {
          chartType: 'dockerKpiCard',
          dataSource: 1,
          icon: 'log',
          metricLabel: t('log.analysis.docker.totalLogCount'),
          displayMaps: {
            type: 'single',
            key: 'logcount',
            value: 'logcount',
            tooltipField: 'logcount'
          },
          dataSourceParams: {
            query:
              'collect_type:"docker" | stats by (_time:${_time}) count() as logcount'
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 3,
        y: 0,
        i: uuidv4(),
        name: t('log.analysis.docker.errorFatalLines'),
        moved: false,
        static: false,
        description: t('log.analysis.docker.errorFatalLinesDesc'),
        valueConfig: {
          chartType: 'dockerKpiCard',
          dataSource: 1,
          icon: 'error',
          color: '#f5222d',
          metricLabel: t('log.analysis.docker.errorFatalLines'),
          displayMaps: {
            type: 'single',
            key: 'errcount',
            value: 'errcount',
            tooltipField: 'errcount'
          },
          dataSourceParams: {
            query:
              'collect_type:"docker" (ERROR OR FATAL) | stats by (_time:${_time}) count() as errcount'
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 6,
        y: 0,
        i: uuidv4(),
        name: t('log.analysis.docker.containerCount'),
        moved: false,
        static: false,
        description: t('log.analysis.docker.containerCountDesc'),
        valueConfig: {
          chartType: 'dockerKpiCard',
          dataSource: 1,
          icon: 'docker',
          color: '#155AEF',
          metricLabel: t('log.analysis.docker.containerCount'),
          displayMaps: {
            type: 'single',
            key: 'container_count',
            value: 'container_count',
            tooltipField: 'container_count'
          },
          dataSourceParams: {
            query:
              'collect_type:"docker" | stats by (_time:${_time},container_name) count() as cnt | stats by (_time) count() as container_count'
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 9,
        y: 0,
        i: uuidv4(),
        name: t('log.analysis.docker.stderrRatio'),
        moved: false,
        static: false,
        description: t('log.analysis.docker.stderrRatioDesc'),
        valueConfig: {
          chartType: 'dockerKpiCard',
          dataSource: 1,
          icon: 'percent',
          color: '#faad14',
          metricLabel: t('log.analysis.docker.stderrRatio'),
          displayMaps: {
            type: 'single',
            key: 'error_rate',
            value: 'error_rate',
            tooltipField: 'error_rate'
          },
          dataSourceParams: {
            query:
              'collect_type:"docker" | stats by (_time:${_time}) count() as total, count() if (stream:="stderr") as errors | math errors / total * 100 as error_rate'
          }
        }
      },
      {
        h: 2,
        w: 8,
        x: 0,
        y: 2,
        i: uuidv4(),
        name: t('log.analysis.docker.logVsErrorTrend'),
        moved: false,
        static: false,
        description: t('log.analysis.docker.logVsErrorTrendDesc'),
        valueConfig: {
          chartType: 'dockerArea',
          dataSource: 1,
          displayMaps: {
            type: 'dual',
            key: 'logcount',
            value: 'logcount',
            barField: 'logcount',
            lineField: 'errcount',
            barLabel: t('log.analysis.docker.logCount'),
            lineLabel: t('log.analysis.docker.errorCount')
          },
          dataSourceParams: {
            query:
              'collect_type:"docker" | stats by (_time:${_time}) count() as logcount, count() if (stream:="stderr") as errcount'
          }
        }
      },
      {
        h: 2,
        w: 4,
        x: 8,
        y: 2,
        i: uuidv4(),
        name: t('log.analysis.docker.streamDistribution'),
        moved: false,
        static: false,
        description: t('log.analysis.docker.streamDistributionDesc'),
        valueConfig: {
          chartType: 'line',
          dataSource: 1,
          displayMaps: {
            type: 'multiple',
            key: 'stream',
            value: 'logcount',
            tooltipField: 'stream'
          },
          dataSourceParams: {
            query:
              'collect_type:"docker" | stats by (_time:${_time},stream) count() as logcount | sort by (_time asc, stream asc)'
          }
        }
      },
      {
        h: 2,
        w: 4,
        x: 0,
        y: 4,
        i: uuidv4(),
        name: t('log.analysis.docker.severityDistribution'),
        moved: false,
        static: false,
        description: t('log.analysis.docker.severityDistributionDesc'),
        valueConfig: {
          chartType: 'dockerDonut',
          dataSource: 1,
          displayMaps: {
            type: 'single',
            key: 'level',
            value: 'cnt',
            tooltipField: 'level'
          },
          dataSourceParams: {
            query:
              'collect_type:"docker" | extract "(?P<level>ERROR|FATAL|WARN|WARNING|INFO|DEBUG)" from _msg | stats by (level) count() as cnt | sort by (cnt desc)'
          }
        }
      },
      {
        h: 2,
        w: 8,
        x: 4,
        y: 4,
        i: uuidv4(),
        name: t('log.analysis.docker.topContainerErrors'),
        moved: false,
        static: false,
        description: t('log.analysis.docker.topContainerErrorsDesc'),
        valueConfig: {
          chartType: 'dockerBar',
          dataSource: 1,
          barColor: '#f5222d',
          displayMaps: {
            type: 'single',
            key: 'container_name',
            value: 'errcount',
            tooltipField: 'container_name'
          },
          dataSourceParams: {
            query:
              'collect_type:"docker" stream:"stderr" | stats by (container_name) count() as errcount | sort by (errcount desc) | limit 10'
          }
        }
      },
      {
        h: 2,
        w: 6,
        x: 0,
        y: 6,
        i: uuidv4(),
        name: t('log.analysis.docker.topImageErrors'),
        moved: false,
        static: false,
        description: t('log.analysis.docker.topImageErrorsDesc'),
        valueConfig: {
          chartType: 'dockerBar',
          dataSource: 1,
          barColor: '#f5222d',
          displayMaps: {
            type: 'single',
            key: 'image',
            value: 'errcount',
            tooltipField: 'image'
          },
          dataSourceParams: {
            query:
              'collect_type:"docker" stream:"stderr" | stats by (image) count() as errcount | sort by (errcount desc) | limit 10'
          }
        }
      },
      {
        h: 2,
        w: 6,
        x: 6,
        y: 6,
        i: uuidv4(),
        name: t('log.analysis.docker.topServices'),
        moved: false,
        static: false,
        description: t('log.analysis.docker.topServicesDesc'),
        valueConfig: {
          chartType: 'dockerBar',
          dataSource: 1,
          barColor: '#15B77E',
          displayMaps: {
            type: 'single',
            key: '"label.com.docker.compose.service"',
            value: 'logcount',
            tooltipField: '"label.com.docker.compose.service"'
          },
          dataSourceParams: {
            query:
              'collect_type:"docker" | stats by ("label.com.docker.compose.service") count() as logcount | sort by (logcount desc) | limit 10'
          }
        }
      },
      {
        h: 3,
        w: 12,
        x: 0,
        y: 8,
        i: uuidv4(),
        name: t('log.analysis.docker.topContainerErrors'),
        moved: false,
        static: false,
        description: t('log.analysis.docker.topContainerErrorsTableDesc'),
        valueConfig: {
          chartType: 'dockerErrorTable',
          dataSource: 1,
          displayMaps: {
            type: 'single',
            key: 'container_name',
            value: 'errcount',
            imageField: 'image',
            timeField: 'last_time'
          },
          dataSourceParams: {
            query:
              'collect_type:"docker" stream:"stderr" | stats by (container_name,image) count() as errcount, max(_time) as last_time | sort by (errcount desc) | limit 10'
          }
        }
      },
      {
        h: 3,
        w: 6,
        x: 0,
        y: 11,
        i: uuidv4(),
        name: t('log.analysis.docker.errorHeatmap'),
        moved: false,
        static: false,
        description: t('log.analysis.docker.errorHeatmapDesc'),
        valueConfig: {
          chartType: 'heatmap',
          dataSource: 1,
          limit: 8,
          displayMaps: {
            time: '_time',
            category: 'container_name',
            value: 'errcount'
          },
          dataSourceParams: {
            query:
              'collect_type:"docker" stream:"stderr" | stats by (_time:${_time},container_name) count() as errcount | sort by (errcount desc)'
          }
        }
      },
      {
        h: 3,
        w: 6,
        x: 6,
        y: 11,
        i: uuidv4(),
        name: t('log.analysis.docker.recentErrorLogs'),
        moved: false,
        static: false,
        description: t('log.analysis.docker.recentErrorLogsDesc'),
        valueConfig: {
          chartType: 'dockerLogTail',
          dataSource: 1,
          dataSourceParams: {
            query:
              'collect_type:"docker" stream:"stderr" | sort by (_time desc) | limit 50'
          }
        }
      }
    ]
  };
};
