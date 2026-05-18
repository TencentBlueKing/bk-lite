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
      // ── Row 1: KPI ×4 (y=0, h=2) ──────────────────────────────────────
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
            searchQuery: 'collect_type:"docker"',
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
            searchQuery: 'collect_type:"docker" stream:"stderr"',
            query:
              'collect_type:"docker" | extract "(?P<level>ERROR|FATAL)" from _msg | stats by (_time:${_time}) count() as errcount'
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
            searchQuery: 'collect_type:"docker"',
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
            searchQuery: 'collect_type:"docker" stream:"stderr"',
            query:
              'collect_type:"docker" | stats by (_time:${_time}) count() as total, count() if (stream:="stderr") as errors | math errors / total * 100 as error_rate'
          }
        }
      },

      // ── Row 2: 趋势图 ×2 (y=2, h=3) ───────────────────────────────────
      {
        h: 3,
        w: 6,
        x: 0,
        y: 2,
        i: uuidv4(),
        name: t('log.analysis.docker.logVsErrorTrend'),
        moved: false,
        static: false,
        valueConfig: {
          chartType: 'dockerDualLine',
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
            searchQuery: 'collect_type:"docker"',
            query:
              'collect_type:"docker" | stats by (_time:${_time}) count() as logcount, count() if (stream:="stderr") as errcount'
          }
        }
      },
      {
        h: 3,
        w: 6,
        x: 6,
        y: 2,
        i: uuidv4(),
        name: t('log.analysis.docker.streamDistribution'),
        moved: false,
        static: false,
        valueConfig: {
          chartType: 'dockerDualLine',
          dataSource: 1,
          displayMaps: {
            type: 'dual',
            key: 'stdout',
            value: 'stdout',
            barField: 'stdout',
            lineField: 'stderr',
            barLabel: 'stdout',
            lineLabel: 'stderr'
          },
          dataSourceParams: {
            searchQuery: 'collect_type:"docker"',
            query:
              'collect_type:"docker" | stats by (_time:${_time}) count() if (stream:="stdout") as stdout, count() if (stream:="stderr") as stderr'
          }
        }
      },

      // ── Row 3: 分布+柱状 ×3 (y=5, h=3) ───────────────────────────────
      {
        h: 3,
        w: 4,
        x: 0,
        y: 5,
        i: uuidv4(),
        name: t('log.analysis.docker.severityDistribution'),
        moved: false,
        static: false,
        valueConfig: {
          chartType: 'dockerSeverityDonut',
          dataSource: 1,
          displayMaps: {
            type: 'single',
            key: 'level',
            value: 'cnt',
            tooltipField: 'level'
          },
          dataSourceParams: {
            searchQuery: 'collect_type:"docker"',
            query:
              'collect_type:"docker" | stats count() as total_count, count() if (_msg:"ERROR" OR _msg:"FATAL" OR _msg:"Error") as error_count, count() if (_msg:"WARN" OR _msg:"WARNING" OR _msg:"DEPRECATION") as warn_count, count() if (_msg:"INFO" OR _msg:"LOG:" OR _msg:" I  ") as info_count, count() if (_msg:"DEBUG") as debug_count'
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 4,
        y: 5,
        i: uuidv4(),
        name: 'Top 容器错误日志行数',
        moved: false,
        static: false,
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
            searchQuery: 'collect_type:"docker" stream:"stderr"',
            query:
              'collect_type:"docker" stream:"stderr" | stats by (container_name) count() as errcount | sort by (errcount desc) | limit 10'
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 8,
        y: 5,
        i: uuidv4(),
        name: 'Top 服务日志行数',
        moved: false,
        static: false,
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
            searchQuery: 'collect_type:"docker"',
            query:
              'collect_type:"docker" | stats by ("label.com.docker.compose.service") count() as logcount | sort by (logcount desc) | limit 10'
          }
        }
      },
      // ── Row 4: 镜像柱 + 最近日志表 (y=8, h=3) ───────────────────────
      {
        h: 3,
        w: 6,
        x: 0,
        y: 8,
        i: uuidv4(),
        name: 'Top 镜像错误日志行数',
        moved: false,
        static: false,
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
            searchQuery: 'collect_type:"docker" stream:"stderr"',
            query:
              'collect_type:"docker" stream:"stderr" | stats by (image) count() as errcount | sort by (errcount desc) | limit 10'
          }
        }
      },
      {
        h: 3,
        w: 6,
        x: 6,
        y: 8,
        i: uuidv4(),
        name: t('log.analysis.docker.recentErrorLogs'),
        moved: false,
        static: false,
        valueConfig: {
          chartType: 'dockerLogTail',
          dataSource: 1,
          dataSourceParams: {
            searchQuery: 'collect_type:"docker" stream:"stderr"',
            query:
              'collect_type:"docker" stream:"stderr" | extract "(?P<level>ERROR|FATAL|WARN|INFO)" from _msg | sort by (_time desc) | limit 50'
          }
        }
      }
    ]
  };
};
