import type {
  AiContextSection,
  AiPageContext,
  PageContextMessage,
  PageContextToolkit,
} from '@/components/ai-page-context/types';

const TITLE_PREFIX = 'alarm-center:';
const LIST_TABS = new Set(['activeAlarms', 'historicalAlarms']);
const EMPTY_HINT = /暂无数据|无数据|No [Dd]ata/;

const cleanLabel = (value: string) => value.replace(/\s+/g, ' ').trim();

const isHidden = (element: Element | null): boolean => {
  for (let node: Element | null = element; node; node = node.parentElement) {
    if (!(node instanceof HTMLElement)) continue;
    if (node.hidden || node.getAttribute('aria-hidden') === 'true') return true;
    const display = node.style.display || (typeof getComputedStyle === 'function' ? getComputedStyle(node).display : '');
    if (display === 'none') return true;
  }
  return false;
};

const normalizedPathname = (pathname = typeof window === 'undefined' ? '' : window.location.pathname) =>
  pathname.endsWith('/') ? pathname : `${pathname}/`;

export const isAlarmCenterListView = (
  pathname = typeof window === 'undefined' ? '' : window.location.pathname,
): boolean => normalizedPathname(pathname).includes('/alarm/alarms/');

const listRoot = (): HTMLElement | null => {
  const content = Array.from(document.querySelectorAll<HTMLElement>('[class*="alertContent"]'))
    .find((node) => !isHidden(node));
  return content?.parentElement || null;
};

const activeListTab = (): string => {
  const active = listRoot()?.querySelector('.ant-tabs-tab-active');
  const key = active?.getAttribute('data-node-key') || '';
  return LIST_TABS.has(key) ? key : '';
};

export interface AlarmCenterListStamp {
  tab: string;
  filterText: string;
  rangeText: string;
  rowFingerprint: string;
  loading: boolean;
  emptyText: string;
}

const readCheckboxGroups = (filterRoot: Element | null): string[] => {
  if (!filterRoot) return [];
  const groups = Array.from(filterRoot.querySelectorAll('[class*="item"]'));
  const blocks = groups.length ? groups : Array.from(filterRoot.querySelectorAll('.collapse-title')).map((title) =>
    title.closest('div')?.parentElement || title.parentElement,
  );
  const lines: string[] = [];
  (blocks.filter(Boolean) as Element[]).forEach((group) => {
    const title = cleanLabel(
      group.querySelector('.collapse-title .title, [class*="header"] span')?.textContent || '',
    );
    const values = Array.from(group.querySelectorAll('.ant-checkbox-wrapper-checked'))
      .map((node) => cleanLabel(node.textContent || ''))
      .filter(Boolean);
    if (title) lines.push(values.length ? `${title}: ${values.join('、')}` : `${title}: 未选`);
  });
  return lines;
};

const readFilterFields = (): string[] => {
  const root = listRoot();
  const filterRoot = root?.querySelector('[class*="filters"]') || null;
  const lines = readCheckboxGroups(filterRoot);
  const myAlarms = Array.from(root?.querySelectorAll('.ant-checkbox-wrapper') || [])
    .find((node) => /我的告警|My Alarms/i.test(node.textContent || ''));
  if (myAlarms) {
    lines.push(myAlarms.classList.contains('ant-checkbox-wrapper-checked') ? '我的告警: 是' : '我的告警: 否');
  }
  const search = root?.querySelector<HTMLInputElement>('[class*="table"] input.ant-input, [class*="alertContent"] input.ant-input');
  if (search?.value) lines.push(`搜索: ${cleanLabel(search.value)}`);
  const rangeRoot = root?.querySelector('[class*="customSlect"]');
  if (rangeRoot && activeListTab() === 'historicalAlarms') {
    const range = Array.from(rangeRoot.querySelectorAll('.ant-select-selection-item'))
      .filter((node) => !node.closest('[class*="refreshBox"]'))
      .map((node) => cleanLabel(node.textContent || ''))
      .filter(Boolean)
      .join('、')
      || Array.from(rangeRoot.querySelectorAll<HTMLInputElement>('.ant-picker-input input'))
        .map((node) => cleanLabel(node.value || ''))
        .filter(Boolean)
        .join(' ~ ');
    lines.push(range ? `时间筛选: ${range}` : '时间筛选:');
  } else if (activeListTab() === 'activeAlarms') {
    lines.push('活跃告警不按时间窗过滤');
  }
  return lines;
};

const readTableRows = (): string[] => {
  const table = listRoot()?.querySelector('[class*="table"] table, [class*="alertContent"] .ant-table');
  if (!table) return [];
  const headerCells = Array.from(table.querySelectorAll('thead th')).map((cell, index, all) => {
    if (index === all.length - 1 && /详情|关闭|Detail|Close|操作/.test(cell.textContent || '')) return '';
    return cleanLabel(cell.textContent || '');
  });
  const header = headerCells.filter(Boolean).join(' | ');
  const bodyRows = Array.from(table.querySelectorAll('.ant-table-tbody tr.ant-table-row, .ant-table-tbody tr, tbody tr'))
    .filter((row) => !row.classList.contains('ant-table-measure-row'))
    .map((row) => {
      const cells = Array.from(row.querySelectorAll('td'));
      const usable = cells.filter((cell) => !cell.querySelector('button, .ant-btn, .ant-dropdown-trigger'));
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

export const readAlarmCenterListStamp = (): AlarmCenterListStamp => {
  const tab = activeListTab();
  const rows = readTableRows();
  const table = listRoot()?.querySelector('[class*="table"]');
  return {
    tab,
    filterText: readFilterFields().join('；'),
    rangeText: readRangeText(),
    rowFingerprint: rows.slice(0, 4).join('|'),
    loading: Boolean(table?.querySelector('.ant-spin-spinning')),
    emptyText: cleanLabel(table?.querySelector('.ant-empty-description')?.textContent || '')
      || (rows.length <= 1 ? (Array.from(table?.querySelectorAll('span') || [])
        .map((node) => cleanLabel(node.textContent || ''))
        .find((text) => EMPTY_HINT.test(text)) || '') : ''),
  };
};

export const buildAlarmCenterCurrentTime = (stamp: AlarmCenterListStamp): string =>
  [stamp.tab, stamp.filterText, stamp.rangeText, stamp.rowFingerprint, stamp.loading ? 'loading' : '']
    .filter(Boolean)
    .join('::');

const listTextSections = (stamp: AlarmCenterListStamp): AiContextSection[] => {
  const identity = [
    '正在查看告警中心列表',
    stamp.tab === 'historicalAlarms' ? '视图: 所有告警' : stamp.tab ? '视图: 活跃告警' : '',
    stamp.filterText ? `当前筛选: ${stamp.filterText}` : '',
    stamp.loading ? '表格加载中' : '',
    stamp.emptyText ? `空态: ${stamp.emptyText}` : '',
  ].filter(Boolean);
  const rows = stamp.loading ? [] : readTableRows();
  return [
    {
      id: 'alarm-center-list-identity',
      label: '当前告警列表',
      content: identity.join('\n'),
      priority: 10,
    },
    ...(stamp.rangeText
      ? [{
        id: 'alarm-center-list-range',
        label: '结果范围',
        content: stamp.rangeText,
        priority: 8,
      }]
      : []),
    ...(rows.length
      ? [{
        id: 'alarm-center-list-table',
        label: '当前页告警',
        content: rows.join('\n'),
        priority: 4,
      }]
      : []),
  ];
};

export function getMessage(): PageContextMessage {
  if (!isAlarmCenterListView() || !activeListTab()) return { title: '' };
  const stamp = readAlarmCenterListStamp();
  const title = `${TITLE_PREFIX}${stamp.tab}`;
  const currentTime = buildAlarmCenterCurrentTime(stamp);
  return currentTime ? { title, currentTime } : { title };
}

export function getTextContext(): Partial<AiPageContext> {
  if (!isAlarmCenterListView() || !activeListTab()) return { sections: [], images: [] };
  const stamp = readAlarmCenterListStamp();
  return {
    url: typeof window === 'undefined' ? '' : window.location.href,
    app: 'alarm',
    title: document.title || '告警中心',
    sections: listTextSections(stamp),
    images: [],
  };
}

export async function getContext(toolkit: PageContextToolkit): Promise<Partial<AiPageContext>> {
  void toolkit;
  if (!isAlarmCenterListView() || !activeListTab()) {
    return getTextContext();
  }
  const base = getTextContext();
  const stamp = readAlarmCenterListStamp();
  console.info('[ai-page-context] page data updated at', buildAlarmCenterCurrentTime(stamp), {
    tab: stamp.tab,
    range: stamp.rangeText,
  });
  return base;
}
