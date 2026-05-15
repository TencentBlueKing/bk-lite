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
        name: '日志总量',
        moved: false,
        static: false,
        description: 'Redis 日志总条数',
        valueConfig: {
          chartType: 'redisKpiCard',
          dataSource: 1,
          displayMaps: { type: 'single', key: '_time', value: 'total_count' },
          dataSourceParams: {
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
        name: 'ERR 错误数',
        moved: false,
        static: false,
        description: '_msg 以 ERR 开头的协议错误',
        valueConfig: {
          chartType: 'redisKpiCard',
          dataSource: 1,
          color: '#EF4444',
          displayMaps: { type: 'single', key: '_time', value: 'err_count' },
          dataSourceParams: {
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
        name: '类型 / 集群错误',
        moved: false,
        static: false,
        description: 'WRONGTYPE 数据类型错误与 CLUSTERDOWN 集群宕机',
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
        name: '认证失败数',
        moved: false,
        static: false,
        description: 'WRONGPASS / NOAUTH / AUTH failed 安全事件',
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
        name: '日志量趋势（总量 & 错误）',
        moved: false,
        static: false,
        description: '',
        valueConfig: {
          chartType: 'redisTrendLine',
          dataSource: 1,
          displayMaps: {
            key: '_time',
            totalField: 'total_count',
            errField: 'err_count',
            totalLabel: '日志总量',
            errLabel: 'ERR 错误'
          },
          dataSourceParams: {
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
        name: '日志事件类型分布',
        moved: false,
        static: false,
        description: '',
        valueConfig: {
          chartType: 'redisDonut',
          dataSource: 1,
          dataSourceParams: {
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
        name: 'Top 触发命令',
        moved: false,
        static: false,
        description: '',
        valueConfig: {
          chartType: 'redisInstanceBar',
          dataSource: 1,
          displayMaps: { key: 'redis_cmd', value: 'cmd_count' },
          dataSourceParams: {
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
        name: 'Top 错误 case',
        moved: false,
        static: false,
        description: '',
        valueConfig: {
          chartType: 'redisInstanceBar',
          dataSource: 1,
          displayMaps: { key: 'err_case', value: 'case_count' },
          dataSourceParams: {
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
        name: '节点日志量 vs 错误数',
        moved: false,
        static: false,
        description: '',
        valueConfig: {
          chartType: 'redisNodeCompareBar',
          dataSource: 1,
          dataSourceParams: {
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
        name: '部署类型分布',
        moved: false,
        static: false,
        description: '',
        valueConfig: {
          chartType: 'redisInstanceBar',
          dataSource: 1,
          displayMaps: { key: 'deploy_path', value: 'log_count' },
          dataSourceParams: {
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
        name: '最近 Redis 日志明细',
        moved: false,
        static: false,
        valueConfig: {
          chartType: 'redisLogTable',
          dataSource: 1,
          dataSourceParams: {
            query: `${REDIS_BASE} | sort by (_time desc) | limit 30`
          }
        }
      }
    ]
  };
};
