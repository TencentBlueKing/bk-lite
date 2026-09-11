import type {
  AiContextSection,
  AiPageContext,
  PageContextMessage,
  PageContextToolkit,
} from '@/components/ai-page-context/types';
import { fingerprintAlertListRows } from './alertListStamp';

const TITLE_PREFIX = 'monitor-alert:';
const HOST_TABS = new Set(['activeAlarms', 'historicalAlarms']);
const COUNT_PLACEHOLDER = /已选\s*\d+\s*项/;
const EMPTY_HINT = /暂无数据|无数据|No [Dd]ata/;

const cleanLabel = (value: string) => value.replace(/\s+/g, ' ').trim();
const listRoot = () => document.querySelector<HTMLElement>('[class*="alarmList"]');

const activeHostTab = (): string => {
  const active = listRoot()?.querySelector('.ant-tabs-tab-active');
  const key = active?.getAttribute('data-node-key') || '';
  return HOST_TABS.has(key) ? key : '';
};

export const isHostAlertListView = (): boolean => Boolean(activeHostTab());

const objIdFromSearch = (search = typeof window === 'undefined' ? '' : window.location.search) =>
  new URLSearchParams(search).get('objId') || 'all';

export interface AlertListStamp {
  tab: string;
  objId: string;
  objectLabel: string;
  filterText: string;
  rangeText: string;
  rowFingerprint: string;
  chartText: string;
  loading: boolean;
  emptyText: string;
}

const titledNames = (root: Element | null): string => {
  if (!root) return '';
  const titled = [root, ...Array.from(root.querySelectorAll('[title]'))].find(
    (node) => node instanceof HTMLElement && node.title && !COUNT_PLACEHOLDER.test(node.title),
  );
  return titled instanceof HTMLElement ? cleanLabel(titled.title) : '';
};

const readSelectValue = (group: Element): string => {
  const items = Array.from(group.querySelectorAll('.ant-select-selection-item'))
    .filter((node) => !node.closest('[class*="refreshBox"]'))
    .map((node) => {
      const visible = cleanLabel(node.textContent || '');
      if (COUNT_PLACEHOLDER.test(visible)) {
        const names = titledNames(node);
        return names ? `${visible}（${names}）` : visible;
      }
      return visible;
    })
    .filter(Boolean);
  return [...new Set(items)].join('、');
};

const readFilterFields = (): string[] => {
  const condition = listRoot()?.querySelector('[class*="searchCondition"] [class*="condition"]');
  if (!condition) return [];
  const lines: string[] = [];
  Array.from(condition.querySelectorAll('ul > li')).forEach((item) => {
    const label = cleanLabel(item.querySelector('span')?.textContent || '').replace(/[:：]\s*$/, '');
    const value = readSelectValue(item);
    if (label) lines.push(value ? `${label}: ${value}` : `${label}:`);
  });
  const rangeRoot = condition.querySelector('[class*="customSlect"]');
  if (rangeRoot) {
    const range = readSelectValue(rangeRoot)
      || Array.from(rangeRoot.querySelectorAll<HTMLInputElement>('.ant-picker-input input'))
        .map((node) => cleanLabel(node.value || ''))
        .filter(Boolean)
        .join(' ~ ');
    lines.push(range ? `时间筛选: ${range}` : '时间筛选:');
  } else if (activeHostTab() === 'activeAlarms') {
    lines.push('活跃告警不按时间窗过滤');
  }
  const search = listRoot()?.querySelector<HTMLInputElement>('[class*="table"] input.ant-input');
  if (search?.value) lines.push(`搜索: ${cleanLabel(search.value)}`);
  return lines;
};

const readTableRows = (): string[] => {
  const table = listRoot()?.querySelector('[class*="table"]');
  if (!table) return [];
  const headerCells = Array.from(table.querySelectorAll('thead th')).map((cell, index, all) => {
    if (index === all.length - 1 && /详情|关闭|Detail|Close|操作/.test(cell.textContent || '')) return '';
    return cleanLabel(cell.textContent || '');
  });
  const header = headerCells.filter(Boolean).join(' | ');
  const bodyRows = Array.from(table.querySelectorAll('.ant-table-tbody tr.ant-table-row, .ant-table-tbody tr'))
    .filter((row) => !row.classList.contains('ant-table-measure-row'))
    .map((row) => {
      const cells = Array.from(row.querySelectorAll('td'));
      const usable = cells.filter((cell) => !cell.querySelector('button, .ant-btn'));
      return usable.map((cell) => cleanLabel(cell.textContent || '')).filter(Boolean).join(' | ');
    })
    .filter(Boolean);
  return [header, ...bodyRows].filter(Boolean);
};

const readRangeText = (): string => {
  const table = listRoot()?.querySelector('[class*="table"]');
  const total = cleanLabel(table?.querySelector('.ant-pagination-total-text')?.textContent || '');
  const page = cleanLabel(table?.querySelector('.ant-pagination-item-active')?.textContent || '');
  return [total, page ? `当前第 ${page} 页` : ''].filter(Boolean).join('；');
};

export const readAlertListStamp = (): AlertListStamp => {
  const tab = activeHostTab();
  const rows = readTableRows();
  const table = listRoot()?.querySelector('[class*="table"]');
  return {
    tab,
    objId: objIdFromSearch(),
    objectLabel: cleanLabel(document.querySelector('[class*="filters"] .ant-tree-node-selected')?.textContent || ''),
    filterText: readFilterFields().join('；'),
    rangeText: readRangeText(),
    rowFingerprint: fingerprintAlertListRows(rows),
    chartText: '',
    loading: Boolean(table?.querySelector('.ant-spin-spinning')),
    emptyText: cleanLabel(table?.querySelector('.ant-empty-description')?.textContent || '')
      || (rows.length <= 1 ? (Array.from(table?.querySelectorAll('span') || [])
        .map((node) => cleanLabel(node.textContent || ''))
        .find((text) => EMPTY_HINT.test(text)) || '') : ''),
  };
};

export const buildAlertListCurrentTime = (stamp: AlertListStamp): string =>
  [stamp.tab, stamp.objId, stamp.filterText, stamp.rangeText, stamp.rowFingerprint, stamp.loading ? 'loading' : '']
    .filter(Boolean)
    .join('::');

const listTextSections = (stamp: AlertListStamp): AiContextSection[] => {
  const identity = [
    '正在查看告警列表',
    stamp.tab === 'historicalAlarms' ? '视图: 历史告警' : stamp.tab ? '视图: 活跃告警' : '',
    stamp.objectLabel ? `对象: ${stamp.objectLabel}` : '',
    stamp.objId ? `objId: ${stamp.objId}` : '',
    stamp.filterText ? `当前筛选: ${stamp.filterText}` : '',
    stamp.loading ? '表格加载中' : '',
    stamp.emptyText ? `空态: ${stamp.emptyText}` : '',
  ].filter(Boolean);
  const rows = stamp.loading ? [] : readTableRows();
  return [
    {
      id: 'alert-list-identity',
      label: '当前告警列表',
      content: identity.join('\n'),
      priority: 10,
    },
    ...(stamp.rangeText
      ? [{
        id: 'alert-list-range',
        label: '结果范围',
        content: stamp.rangeText,
        priority: 8,
      }]
      : []),
    ...(stamp.chartText
      ? [{
        id: 'alert-list-chart',
        label: '分布图',
        content: stamp.chartText,
        priority: 6,
      }]
      : []),
    ...(rows.length
      ? [{
        id: 'alert-list-table',
        label: '当前页告警',
        content: rows.join('\n'),
        priority: 4,
      }]
      : []),
  ];
};

export function getMessage(): PageContextMessage {
  if (!isHostAlertListView()) return { title: '' };
  const stamp = readAlertListStamp();
  const title = `${TITLE_PREFIX}${stamp.tab}:${stamp.objId}`;
  const currentTime = buildAlertListCurrentTime(stamp);
  return currentTime ? { title, currentTime } : { title };
}

export function getTextContext(): Partial<AiPageContext> {
  if (!isHostAlertListView()) return { sections: [], images: [] };
  const stamp = readAlertListStamp();
  return {
    url: typeof window === 'undefined' ? '' : window.location.href,
    app: 'monitor',
    title: document.title || '告警列表',
    sections: listTextSections(stamp),
    images: [],
  };
}

export async function getContext(toolkit: PageContextToolkit): Promise<Partial<AiPageContext>> {
  void toolkit;
  if (!isHostAlertListView()) {
    return getTextContext();
  }
  const base = getTextContext();
  const stamp = readAlertListStamp();
  console.info('[ai-page-context] page data updated at', buildAlertListCurrentTime(stamp), {
    tab: stamp.tab,
    objId: stamp.objId,
    timeRange: stamp.filterText || '(none)',
    range: stamp.rangeText,
  });
  return base;
}
