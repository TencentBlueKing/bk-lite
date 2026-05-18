import { useTranslation } from '@/utils/i18n';
import { v4 as uuidv4 } from 'uuid';

const REDIS_BASE = 'collect_type:"redis" event.dataset:"redis.log"';

export const useRedisDashboard = () => {
  const { t } = useTranslation();

  return {
    name: t('log.analysis.redis.dashboardName'),
    desc: '',
    id: '8',
    category: 'middleware',
    categoryName: t('log.analysis.category.middleware'),
    collectTypeName: 'redis',
    filters: {},
    other: {},
    view_sets: [
      // ─── ROW 1 (y=0, h=2): 4 个 KPI，每个 w=3 ───────────────────────────────
      {
        h: 2,
        w: 3,
        x: 0,
        y: 0,
        i: uuidv4(),
        name: t('log.analysis.redis.totalLogCount'),
        moved: false,
        static: false,
        description: t('log.analysis.redis.totalLogCountDesc'),
        valueConfig: {
          chartType: 'redisKpiCard',
          dataSource: 1,
          displayMaps: { type: 'single', key: '_time', value: 'total_count' },
          dataSourceParams: {
            searchQuery: `${REDIS_BASE}`,
            query: `${REDIS_BASE} | stats by (_time:\${_time}) count() as total_count`
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 3,
        y: 0,
        i: uuidv4(),
        name: t('log.analysis.redis.errCount'),
        moved: false,
        static: false,
        description: t('log.analysis.redis.errCountDesc'),
        valueConfig: {
          chartType: 'redisKpiCard',
          dataSource: 1,
          color: '#EF4444',
          displayMaps: { type: 'single', key: '_time', value: 'err_count' },
          dataSourceParams: {
            searchQuery: `${REDIS_BASE} _msg:"ERR "`,
            query: `${REDIS_BASE} | stats by (_time:\${_time}) count() if (_msg:"ERR ") as err_count`
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 6,
        y: 0,
        i: uuidv4(),
        name: t('log.analysis.redis.typeClusterErrors'),
        moved: false,
        static: false,
        description: t('log.analysis.redis.typeClusterErrorsDesc'),
        valueConfig: {
          chartType: 'redisKpiCard',
          dataSource: 1,
          color: '#F97316',
          displayMaps: {
            type: 'single',
            key: '_time',
            value: 'type_err_count'
          },
          dataSourceParams: {
            searchQuery: `${REDIS_BASE} (_msg:"WRONGTYPE " OR _msg:"CLUSTERDOWN ")`,
            query: `${REDIS_BASE} | stats by (_time:\${_time}) count() if (_msg:"WRONGTYPE " OR _msg:"CLUSTERDOWN ") as type_err_count`
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 9,
        y: 0,
        i: uuidv4(),
        name: t('log.analysis.redis.authFailures'),
        moved: false,
        static: false,
        description: t('log.analysis.redis.authFailuresDesc'),
        valueConfig: {
          chartType: 'redisKpiCard',
          dataSource: 1,
          color: '#8B5CF6',
          displayMaps: {
            type: 'single',
            key: '_time',
            value: 'auth_err_count'
          },
          dataSourceParams: {
            searchQuery: `${REDIS_BASE} (_msg:"WRONGPASS " OR _msg:"NOAUTH " OR _msg:"AUTH failed")`,
            query: `${REDIS_BASE} | stats by (_time:\${_time}) count() if (_msg:"WRONGPASS " OR _msg:"NOAUTH " OR _msg:"AUTH failed") as auth_err_count`
          }
        }
      },

      // ─── ROW 2 (y=2, h=3): 趋势折线 + 事件类型分布环形图 ──────────────────────
      {
        h: 3,
        w: 7,
        x: 0,
        y: 2,
        i: uuidv4(),
        name: t('log.analysis.redis.logTrend'),
        moved: false,
        static: false,
        description: t('log.analysis.redis.logTrendDesc'),
        valueConfig: {
          chartType: 'redisTrendLine',
          dataSource: 1,
          displayMaps: {
            key: '_time',
            totalField: 'total_count',
            errField: 'err_count',
            totalLabel: t('log.analysis.redis.totalLogSeries'),
            errLabel: t('log.analysis.redis.errSeries')
          },
          dataSourceParams: {
            searchQuery: `${REDIS_BASE}`,
            query: `${REDIS_BASE} | stats by (_time:\${_time}) count() as total_count, count() if (_msg:"ERR ") as err_count`
          }
        }
      },
      {
        h: 3,
        w: 5,
        x: 7,
        y: 2,
        i: uuidv4(),
        name: t('log.analysis.redis.eventTypeDistribution'),
        moved: false,
        static: false,
        description: t('log.analysis.redis.eventTypeDistributionDesc'),
        valueConfig: {
          chartType: 'redisDonut',
          dataSource: 1,
          dataSourceParams: {
            searchQuery: `${REDIS_BASE}`,
            query: `${REDIS_BASE} | stats count() as total_count, count() if (_msg:"ERR ") as err_count, count() if (_msg:"WRONGTYPE " OR _msg:"CLUSTERDOWN ") as type_err_count, count() if (_msg:"WRONGPASS " OR _msg:"NOAUTH " OR _msg:"AUTH failed") as auth_err_count, count() if (_msg:"command: ") as cmd_count`
          }
        }
      },

      // ─── ROW 3 (y=5, h=3): Top 命令 + Top case + 节点对比（双系列）────────────
      {
        h: 3,
        w: 4,
        x: 0,
        y: 5,
        i: uuidv4(),
        name: t('log.analysis.redis.topCommands'),
        moved: false,
        static: false,
        description: t('log.analysis.redis.topCommandsDesc'),
        valueConfig: {
          chartType: 'redisInstanceBar',
          dataSource: 1,
          displayMaps: { key: 'redis_cmd', value: 'cmd_count' },
          dataSourceParams: {
            searchQuery: `${REDIS_BASE} _msg:"command: "`,
            query: `${REDIS_BASE} _msg:"command: " | extract "command: <redis_cmd>" from _msg | stats by (redis_cmd) count() as cmd_count | sort by (cmd_count desc) | limit 10`
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 4,
        y: 5,
        i: uuidv4(),
        name: t('log.analysis.redis.topErrorCases'),
        moved: false,
        static: false,
        description: t('log.analysis.redis.topErrorCasesDesc'),
        valueConfig: {
          chartType: 'redisInstanceBar',
          dataSource: 1,
          displayMaps: { key: 'err_case', value: 'case_count' },
          dataSourceParams: {
            searchQuery: `${REDIS_BASE} _msg:"case="`,
            query: `${REDIS_BASE} _msg:"case=" | extract "case=<err_case>" from _msg | stats by (err_case) count() as case_count | sort by (case_count desc) | limit 10`
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 8,
        y: 5,
        i: uuidv4(),
        name: t('log.analysis.redis.nodeLogVsError'),
        moved: false,
        static: false,
        description: t('log.analysis.redis.nodeLogVsErrorDesc'),
        valueConfig: {
          chartType: 'redisNodeCompareBar',
          dataSource: 1,
          dataSourceParams: {
            searchQuery: `${REDIS_BASE}`,
            query: `${REDIS_BASE} node_ip:* | stats by (node_ip) count() as log_count, count() if (_msg:"ERR ") as err_count | sort by (log_count desc) | limit 10`
          }
        }
      },

      // ─── ROW 4 (y=8, h=3): 部署类型分布 + 最近日志明细 ──────────────────────
      {
        h: 3,
        w: 4,
        x: 0,
        y: 8,
        i: uuidv4(),
        name: t('log.analysis.redis.deploymentDistribution'),
        moved: false,
        static: false,
        description: t('log.analysis.redis.deploymentDistributionDesc'),
        valueConfig: {
          chartType: 'redisInstanceBar',
          dataSource: 1,
          displayMaps: { key: 'deploy_path', value: 'log_count' },
          dataSourceParams: {
            searchQuery: `${REDIS_BASE}`,
            query: `${REDIS_BASE} | extract "redis/<deploy_path>/" from "log.file.path" | stats by (deploy_path) count() as log_count | sort by (log_count desc) | limit 10`
          }
        }
      },
      {
        h: 3,
        w: 8,
        x: 4,
        y: 8,
        i: uuidv4(),
        name: t('log.analysis.redis.recentLogs'),
        moved: false,
        static: false,
        description: t('log.analysis.redis.recentLogsDesc'),
        valueConfig: {
          chartType: 'redisLogTable',
          dataSource: 1,
          dataSourceParams: {
            searchQuery: `${REDIS_BASE}`,
            query: `${REDIS_BASE} | sort by (_time desc) | limit 30`
          }
        }
      }
    ]
  };
};
