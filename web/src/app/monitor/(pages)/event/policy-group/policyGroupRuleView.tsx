import React from 'react';
import { Button, Tag } from 'antd';
import { StatusToneBadge } from '@/app/monitor/utils/statusTone';
import { ColumnItem } from '@/app/monitor/types';

export interface PolicyGroupRule {
  id: number;
  name: string;
  plugin_name: string;
  threshold: Array<{ level?: string; method?: string; value?: number }>;
  query_type?: string;
  condition_thresholds?: Record<string, Array<{ level?: string; method?: string; value?: number | null }>>;
  alert_name?: string;
  trigger_count?: number;
  recovery_condition?: number;
  recovery_threshold?: { method?: string; value?: number | null };
  no_data_enabled?: boolean;
  policy_id?: number;
  open_alert_count?: number;
  unit?: string;
  source_template_id?: number | null;
}

export const VIEW_MODE_OPTIONS = [
  { label: '工作台', value: 'workbench' },
  { label: '策略组列表', value: 'groupList' },
] as const;

const METHOD_OPERATOR_MAP: Record<string, string> = {
  gt: '>',
  gte: '>=',
  lt: '<',
  lte: '<=',
  eq: '=',
  ne: '!=',
  '>': '>',
  '>=': '>=',
  '<': '<',
  '<=': '<=',
  '=': '=',
  '!=': '!=',
};

const PLUGIN_TAG: Record<string, { color: string; label: string }> = {
  Host: { color: 'blue', label: 'Host (Linux Agent)' },
  'Host Remote': { color: 'warning', label: 'Host Remote (SSH远程)' },
  'Windows WMI': { color: 'purple', label: 'Windows WMI' },
};

export const templateIdsFromRules = (
  rules: Array<{ source_template_id?: number | null }>
): number[] => {
  const ids: number[] = [];
  const seen = new Set<number>();
  for (const rule of rules) {
    const id = Number(rule.source_template_id);
    if (!Number.isFinite(id) || id <= 0 || seen.has(id)) continue;
    seen.add(id);
    ids.push(id);
  }
  return ids;
};

export const diffGroupTemplates = (existingIds: number[], selectedIds: number[]) => {
  const existing = new Set(existingIds);
  const selected = new Set(selectedIds);
  return {
    addedIds: selectedIds.filter((id) => !existing.has(id)),
    removedIds: existingIds.filter((id) => !selected.has(id)),
  };
};

export const rulesForTemplateIds = (rules: PolicyGroupRule[], templateIds: number[]) => {
  const wanted = new Set(templateIds);
  return rules.filter((rule) => wanted.has(Number(rule.source_template_id)));
};

export interface PolicyGroupMemberPlugin {
  id: number;
  name: string;
}

export interface PolicyGroupMemberTemplate {
  id?: number | null;
  rule_id: number;
  name: string;
  plugin_name: string;
}

export interface PolicyGroupMember {
  instance_id: string;
  name: string;
  plugins?: PolicyGroupMemberPlugin[];
  templates?: PolicyGroupMemberTemplate[];
}

export const memberTemplateFilterOptions = (rules: PolicyGroupRule[]) => {
  const groups = new Map<string, PolicyGroupRule[]>();
  for (const rule of rules) {
    const plugin = rule.plugin_name || '其他';
    const list = groups.get(plugin) || [];
    list.push(rule);
    groups.set(plugin, list);
  }
  return Array.from(groups.entries()).map(([plugin, items]) => {
    const pluginLabel = PLUGIN_TAG[plugin]?.label || plugin;
    return {
      label: pluginLabel,
      options: [
        { label: `${pluginLabel} 全部对象`, value: `plugin:${plugin}` },
        ...items.map((item) => ({
          label: item.name,
          value: item.source_template_id
            ? `template:${item.source_template_id}`
            : `rule:${item.id}`,
        })),
      ],
    };
  });
};

export const filterPolicyGroupMembers = (
  members: PolicyGroupMember[],
  opts: { keyword: string; filter: string | null }
) => {
  const keyword = opts.keyword.trim().toLowerCase();
  const filter = opts.filter || '';
  return members.filter((item) => {
    if (keyword && !String(item.name || '').toLowerCase().includes(keyword)) return false;
    if (!filter) return true;
    if (filter.startsWith('plugin:')) {
      const name = filter.slice('plugin:'.length);
      return (item.plugins || []).some((plugin) => plugin.name === name);
    }
    if (filter.startsWith('template:')) {
      const id = Number(filter.slice('template:'.length));
      return (item.templates || []).some((template) => Number(template.id) === id);
    }
    if (filter.startsWith('rule:')) {
      const id = Number(filter.slice('rule:'.length));
      return (item.templates || []).some((template) => Number(template.rule_id) === id);
    }
    return true;
  });
};

export const pluginCounts = (rules: Array<{ plugin_name?: string }>) => {
  const counts: Record<string, number> = {};
  rules.forEach((item) => {
    const name = item.plugin_name || '其他';
    counts[name] = (counts[name] || 0) + 1;
  });
  return Object.entries(counts).map(([name, count]) => ({ name, count }));
};

export const pluginColumnFilters = (plugins: Array<{ name: string; count: number }>) =>
  [...plugins]
    .sort((a, b) => a.name.localeCompare(b.name, 'zh'))
    .map((item) => ({
      text: `${item.name} (${item.count})`,
      value: item.name,
    }));

export const columnFilterValue = (selected: unknown) => {
  if (!Array.isArray(selected) || selected.length === 0) return '';
  return String(selected[0]);
};

export const readRuleTableFilters = (filters?: {
  no_data_enabled?: unknown;
  plugin_name?: unknown;
} | null) => {
  const noData = columnFilterValue(filters?.no_data_enabled);
  const plugin = columnFilterValue(filters?.plugin_name);
  return {
    noData: noData === 'on' || noData === 'off' ? noData : null,
    plugin: plugin || 'all',
  } as const;
};

export const filterAndSortRules = (
  rules: PolicyGroupRule[],
  opts: { pluginFilter: string; noData: string | null; keyword: string }
) => {
  const keyword = opts.keyword.trim().toLowerCase();
  const list = rules.filter((item) => {
    if (opts.pluginFilter !== 'all' && (item.plugin_name || '其他') !== opts.pluginFilter) {
      return false;
    }
    if (opts.noData === 'on' && !item.no_data_enabled) return false;
    if (opts.noData === 'off' && item.no_data_enabled) return false;
    if (!keyword) return true;
    const name = String(item.name || '').toLowerCase();
    const plugin = String(item.plugin_name || '').toLowerCase();
    return name.includes(keyword) || plugin.includes(keyword);
  });
  return list.sort((a, b) => {
    const pluginA = String(a.plugin_name || '');
    const pluginB = String(b.plugin_name || '');
    if (pluginA !== pluginB) return pluginA.localeCompare(pluginB);
    return String(a.name || '').localeCompare(String(b.name || ''));
  });
};

export const renderPluginTag = (pluginName?: string) => {
  const name = pluginName || '--';
  const meta = PLUGIN_TAG[name];
  if (!meta) return <Tag>{name}</Tag>;
  return <Tag color={meta.color}>{meta.label}</Tag>;
};

export const renderOpenAlertCount = (count: number) => {
  if (count > 0) {
    return (
      <span className="inline-flex items-center px-1.5 py-0.2 rounded font-bold text-[11px] bg-red-50 text-red-600 border border-red-200">
        {count} 条
      </span>
    );
  }
  return <span className="text-[var(--color-text-3)]">--</span>;
};

export const formatRuleThreshold = (
  record: PolicyGroupRule,
  unitLabel: (unitId: string) => string
): React.ReactElement => {
  const list = record.threshold || [];
  if (!list.length) {
    if (record.condition_thresholds && Object.keys(record.condition_thresholds).length > 0) {
      return <span className="font-mono text-[12px] text-[var(--color-text-3)]">多条件组合</span>;
    }
    return <span className="text-[var(--color-text-3)]">--</span>;
  }

  const displayUnit = unitLabel(record.unit || '');
  const unitSuffix = displayUnit ? ` ${displayUnit}` : '';
  const parts = list.map((item) => {
    const op = METHOD_OPERATOR_MAP[item.method || ''] || item.method || '>';
    const valText = item.value != null ? `${item.value}${unitSuffix}` : '--';
    const levelLabel = item.level === 'critical' ? '致命' : item.level === 'warning' ? '警告' : item.level === 'info' ? '提醒' : '';
    return `${levelLabel ? `${levelLabel} ` : ''}${op} ${valText}`;
  });
  const triggerSuffix = record.trigger_count && record.trigger_count > 1 ? ` (连续${record.trigger_count}次)` : '';

  return (
    <span className="inline-block rounded bg-[var(--color-fill-1)] px-1.5 py-0.5 font-mono text-[12px] text-[var(--color-text-2)]">
      {parts.join(' | ')}{triggerSuffix}
    </span>
  );
};

export const buildPolicyGroupRuleColumns = ({
  t,
  unitLabel,
  noDataFilter,
  plugins,
  pluginFilter,
  onEdit,
  nameClassName,
}: {
  t: (key: string) => string;
  unitLabel: (unitId: string) => string;
  noDataFilter: string | null;
  plugins: Array<{ name: string; count: number }>;
  pluginFilter: string;
  onEdit: (record: PolicyGroupRule) => void;
  nameClassName?: string;
}): ColumnItem[] => [
  {
    title: t('common.name'),
    dataIndex: 'name',
    key: 'name',
    render: (_, record) => (
      <span className={nameClassName}>{record.name || '--'}</span>
    ),
  },
  {
    title: '模板',
    dataIndex: 'plugin_name',
    key: 'plugin_name',
    width: 180,
    ...(plugins.length > 1
      ? {
        filters: pluginColumnFilters(plugins),
        filterMultiple: false,
        filterSearch: (input: string, record: { value?: string | number }) =>
          String(record.value ?? '').toLowerCase().includes(input.trim().toLowerCase()),
        filteredValue: pluginFilter && pluginFilter !== 'all' ? [pluginFilter] : null,
      }
      : {}),
    render: (_, record) => renderPluginTag(record.plugin_name),
  },
  {
    title: '触发条件',
    dataIndex: 'threshold',
    key: 'threshold',
    width: 240,
    render: (_, record) => formatRuleThreshold(record as PolicyGroupRule, unitLabel),
  },
  {
    title: '活动告警',
    dataIndex: 'open_alert_count',
    key: 'open_alert_count',
    width: 90,
    align: 'center',
    render: (_, record) => renderOpenAlertCount(record.open_alert_count || 0),
  },
  {
    title: '无数据',
    dataIndex: 'no_data_enabled',
    key: 'no_data_enabled',
    width: 100,
    filters: [
      { text: '已开启', value: 'on' },
      { text: '未开启', value: 'off' },
    ],
    filterMultiple: false,
    filteredValue: noDataFilter ? [noDataFilter] : null,
    render: (_, record) => (
      <StatusToneBadge
        tone={record.no_data_enabled ? 'success' : 'neutral'}
        label={record.no_data_enabled ? '已开启' : '未开启'}
      />
    ),
  },
  {
    title: t('common.action'),
    dataIndex: 'action',
    key: 'action',
    width: 80,
    render: (_, record) => (
      <Button type="link" className="px-0" onClick={() => onEdit(record as PolicyGroupRule)}>
        修改
      </Button>
    ),
  },
];
