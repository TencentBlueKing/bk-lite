import { useTranslation } from '@/utils/i18n';
import { v4 as uuidv4 } from 'uuid';

const FIM_BASE =
  'collect_type:"file_integrity" service.name:"bk-lite-analysis-sample" event.dataset:"file_integrity"';
const FIM_ACTION = 'file_action';
const FIM_PATH = 'file_path';
const FIM_HOST = 'host.name';
const TIME_BUCKET = '${_time}';

const renderTag = (
  label: unknown,
  textColor: string,
  backgroundColor: string,
  minWidth?: number
) => (
  <span
    className="inline-flex items-center justify-center rounded px-2 py-0.5 text-xs font-medium"
    style={{ color: textColor, backgroundColor, minWidth }}
  >
    {String(label || '--')}
  </span>
);

const renderActionTag = (value: unknown) => {
  const key = String(value || '').trim().toLowerCase();
  const metaMap: Record<string, { label: string; text: string; background: string }> = {
    created: { label: '新增', text: '#52c41a', background: 'rgba(82, 196, 26, 0.12)' },
    updated: { label: '修改', text: '#722ed1', background: 'rgba(114, 46, 209, 0.12)' },
    deleted: { label: '删除', text: '#f5222d', background: 'rgba(245, 34, 45, 0.12)' },
    permission_changed: {
      label: '权限变更',
      text: '#fa8c16',
      background: 'rgba(250, 140, 22, 0.12)'
    }
  };
  const meta = metaMap[key] || {
    label: String(value || '--'),
    text: '#5a6d7f',
    background: 'rgba(90, 109, 127, 0.12)'
  };

  return renderTag(meta.label, meta.text, meta.background, 60);
};

export const useFileIntegrityDashboard = () => {
  const { t } = useTranslation();

  return {
    name: '文件完整性监控',
    desc: '',
    id: 'mock-file-integrity',
    category: 'middleware',
    categoryName: t('log.analysis.category.middleware'),
    collectTypeName: 'file_integrity',
    filters: { group: true, instance: true },
    other: {},
    view_sets: [
      {
        h: 2,
        w: 3,
        x: 0,
        y: 0,
        i: uuidv4(),
        name: '总变更数',
        description: '总变更次数（次）',
        valueConfig: {
          chartType: 'fileIntegrityKpiCard',
          dataSource: 1,
          color: 'primary',
          displayMaps: { type: 'single', key: '_time', value: 'total_count' },
          dataSourceParams: {
            searchQuery: FIM_BASE,
            query: `${FIM_BASE} | stats by (_time:${TIME_BUCKET}) count() as total_count`
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 3,
        y: 0,
        i: uuidv4(),
        name: '新增文件数',
        description: '新增文件数量（次）',
        valueConfig: {
          chartType: 'fileIntegrityKpiCard',
          dataSource: 1,
          color: 'success',
          displayMaps: { type: 'single', key: '_time', value: 'created_count' },
          dataSourceParams: {
            searchQuery: `${FIM_BASE} ${FIM_ACTION}:"created"`,
            query: `${FIM_BASE} | stats by (_time:${TIME_BUCKET}) count() if (${FIM_ACTION}:"created") as created_count`
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 6,
        y: 0,
        i: uuidv4(),
        name: '修改文件数',
        description: '修改文件数量（次）',
        valueConfig: {
          chartType: 'fileIntegrityKpiCard',
          dataSource: 1,
          color: 'accent',
          displayMaps: { type: 'single', key: '_time', value: 'updated_count' },
          dataSourceParams: {
            searchQuery: `${FIM_BASE} ${FIM_ACTION}:"updated"`,
            query: `${FIM_BASE} | stats by (_time:${TIME_BUCKET}) count() if (${FIM_ACTION}:"updated") as updated_count`
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 9,
        y: 0,
        i: uuidv4(),
        name: '删除文件数',
        description: '删除文件数量（次）',
        valueConfig: {
          chartType: 'fileIntegrityKpiCard',
          dataSource: 1,
          color: 'danger',
          displayMaps: { type: 'single', key: '_time', value: 'deleted_count' },
          dataSourceParams: {
            searchQuery: `${FIM_BASE} ${FIM_ACTION}:"deleted"`,
            query: `${FIM_BASE} | stats by (_time:${TIME_BUCKET}) count() if (${FIM_ACTION}:"deleted") as deleted_count`
          }
        }
      },
      {
        h: 3,
        w: 8,
        x: 0,
        y: 2,
        i: uuidv4(),
        name: '文件变更趋势',
        valueConfig: {
          chartType: 'fileIntegrityTrend',
          dataSource: 1,
          dataSourceParams: {
            searchQuery: FIM_BASE,
            query:
              `${FIM_BASE} | stats by (_time:${TIME_BUCKET}) count() if (${FIM_ACTION}:"created") as created_count, count() if (${FIM_ACTION}:"updated") as updated_count, count() if (${FIM_ACTION}:"deleted") as deleted_count, count() if (${FIM_ACTION}:"permission_changed") as permission_count`
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 8,
        y: 2,
        i: uuidv4(),
        name: '变更类型分布',
        valueConfig: {
          chartType: 'fileIntegrityPie',
          dataSource: 1,
          displayMaps: { key: 'file_action', value: 'count' },
          dataSourceParams: {
            searchQuery: `${FIM_BASE} ${FIM_ACTION}:*`,
            query: `${FIM_BASE} ${FIM_ACTION}:* | stats by (${FIM_ACTION}) count() as count | sort by (count desc)`
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 0,
        y: 5,
        i: uuidv4(),
        name: 'Top 高频变更路径',
        valueConfig: {
          chartType: 'fileIntegrityTable',
          dataSource: 1,
          showIndex: true,
          columns: [
            { title: '路径', dataIndex: 'file_path', key: 'file_path', width: 210 },
            { title: '变更次数（次）', dataIndex: 'change_count', key: 'change_count', width: 110 },
            { title: '占比', dataIndex: 'ratio', key: 'ratio', width: 86 }
          ],
          dataSourceParams: {
            searchQuery: `${FIM_BASE} ${FIM_PATH}:*`,
            query: `${FIM_BASE} ${FIM_PATH}:* | stats by (${FIM_PATH}) count() as change_count | sort by (change_count desc) | limit 10`,
            transformMode: 'topRatios',
            countField: 'change_count'
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 4,
        y: 5,
        i: uuidv4(),
        name: 'Top 变更主机',
        valueConfig: {
          chartType: 'fileIntegrityTable',
          dataSource: 1,
          showIndex: true,
          columns: [
            { title: '主机', dataIndex: 'host.name', key: 'host.name', width: 140 },
            { title: '变更次数（次）', dataIndex: 'change_count', key: 'change_count', width: 110 },
            { title: '占比', dataIndex: 'ratio', key: 'ratio', width: 86 }
          ],
          dataSourceParams: {
            searchQuery: `${FIM_BASE} ${FIM_HOST}:*`,
            query: `${FIM_BASE} ${FIM_HOST}:* | stats by (${FIM_HOST}) count() as change_count | sort by (change_count desc) | limit 10`,
            transformMode: 'topRatios',
            countField: 'change_count'
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 8,
        y: 5,
        i: uuidv4(),
        name: 'Top 删除文件路径',
        valueConfig: {
          chartType: 'fileIntegrityTable',
          dataSource: 1,
          showIndex: true,
          columns: [
            { title: '路径', dataIndex: 'file_path', key: 'file_path', width: 210 },
            { title: '删除次数（次）', dataIndex: 'deleted_count', key: 'deleted_count', width: 120 },
            { title: '最近删除时间', dataIndex: 'last_change_time', key: 'last_change_time', width: 166 }
          ],
          dataSourceParams: {
            searchQuery: `${FIM_BASE} ${FIM_ACTION}:"deleted" ${FIM_PATH}:*`,
            query:
              `${FIM_BASE} ${FIM_ACTION}:"deleted" ${FIM_PATH}:* | stats by (${FIM_PATH}) count() as deleted_count, max(_time) as last_change_time | sort by (deleted_count desc) | limit 10`
          }
        }
      },
      {
        h: 4,
        w: 6,
        x: 0,
        y: 8,
        i: uuidv4(),
        name: '最近文件变更明细',
        valueConfig: {
          chartType: 'fileIntegrityTable',
          dataSource: 1,
          showIndex: false,
          columns: [
            { title: '时间', dataIndex: '@timestamp', key: '@timestamp', width: 166 },
            { title: '主机', dataIndex: 'host.name', key: 'host.name', width: 82 },
            { title: '动作', dataIndex: 'file_action', key: 'file_action', width: 88, render: renderActionTag },
            { title: '路径', dataIndex: 'file_path', key: 'file_path', width: 210 },
            { title: 'owner', dataIndex: 'user.name', key: 'user.name', width: 88 },
            { title: 'group', dataIndex: 'group.name', key: 'group.name', width: 88 },
            { title: 'mode', dataIndex: 'file.mode', key: 'file.mode', width: 96 },
            { title: 'mtime', dataIndex: 'mtime', key: 'mtime', width: 166 },
            { title: 'hash', dataIndex: 'hash.sha256', key: 'hash.sha256', width: 150 }
          ],
          dataSourceParams: {
            searchQuery: FIM_BASE,
            query: `${FIM_BASE} | sort by (_time desc) | limit 20`
          }
        }
      },
      {
        h: 4,
        w: 6,
        x: 6,
        y: 8,
        i: uuidv4(),
        name: '最近删除/修改明细',
        valueConfig: {
          chartType: 'fileIntegrityTable',
          dataSource: 1,
          showIndex: false,
          columns: [
            { title: '时间', dataIndex: '@timestamp', key: '@timestamp', width: 166 },
            { title: '主机', dataIndex: 'host.name', key: 'host.name', width: 82 },
            { title: '动作', dataIndex: 'file_action', key: 'file_action', width: 88, render: renderActionTag },
            { title: '路径', dataIndex: 'file_path', key: 'file_path', width: 180 },
            { title: 'owner', dataIndex: 'user.name', key: 'user.name', width: 88 },
            { title: 'group', dataIndex: 'group.name', key: 'group.name', width: 88 },
            { title: 'mode', dataIndex: 'file.mode', key: 'file.mode', width: 96 },
            { title: 'hash', dataIndex: 'hash.sha256', key: 'hash.sha256', width: 140 }
          ],
          dataSourceParams: {
            searchQuery: `${FIM_BASE} (${FIM_ACTION}:"deleted" OR ${FIM_ACTION}:"updated")`,
            query: `${FIM_BASE} (${FIM_ACTION}:"deleted" OR ${FIM_ACTION}:"updated") | sort by (_time desc) | limit 20`
          }
        }
      }
    ]
  };
};
