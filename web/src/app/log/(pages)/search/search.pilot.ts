import type {
  AiContextSection,
  AiPageContext,
  PageContextMessage,
  PageContextToolkit,
} from '@/components/ai-page-context/types';
import { redactSensitiveText } from '@/components/ai-page-context/redact-sensitive-text';

const TITLE_PREFIX = 'log-search:';
/** 与 `page.tsx` Segmented options 顺序一致：list / overview(终端)。 */
const LOG_SEARCH_VIEW_VALUES = ['list', 'overview'] as const;

const cleanLabel = (value: string) => value.replace(/\s+/g, ' ').trim();

const selectedSegmentedValue = (values: readonly string[]): string => {
  const inputs = Array.from(document.querySelectorAll<HTMLInputElement>('.ant-segmented-item-input'));
  const index = inputs.findIndex((input) => input.checked);
  if (index < 0) return '';
  return values[index] || '';
};

const activeLogSearchView = (): string => selectedSegmentedValue(LOG_SEARCH_VIEW_VALUES);

const isLogSearchPath = (pathname = typeof window === 'undefined' ? '' : window.location.pathname) => {
  const normalized = pathname.endsWith('/') ? pathname : `${pathname}/`;
  return normalized.includes('/log/search/');
};

const isLogSearchListView = (): boolean => isLogSearchPath() && activeLogSearchView() === 'list';

const searchCondition = () => document.querySelector<HTMLElement>('[class*="searchCondition"]');

const readQuery = (): string => {
  const root = searchCondition();
  const wrapped = root?.querySelector<HTMLInputElement>('.ant-input-affix-wrapper input.ant-input');
  if (wrapped?.value) return wrapped.value;
  const inputs = Array.from(root?.querySelectorAll<HTMLInputElement>('input.ant-input') || []).filter(
    (input) => !input.classList.contains('ant-select-selection-search-input'),
  );
  return inputs[0]?.value || '';
};

const readLogGroups = (): string => {
  const items = Array.from(
    searchCondition()?.querySelectorAll('.ant-select-multiple .ant-select-selection-item') || [],
  )
    .map((node) => cleanLabel(node.textContent || ''))
    .filter(Boolean);
  return [...new Set(items)].join('、');
};

const readTimeRange = (): string => {
  const selector = document.querySelector<HTMLElement>('[class*="timeSelector"]');
  const custom = selector?.querySelector<HTMLElement>('[class*="customSlect"]');
  if (!custom) return '';
  const range = Array.from(custom.querySelectorAll<HTMLInputElement>('.ant-picker-input input'))
    .map((input) => cleanLabel(input.value || ''))
    .filter(Boolean);
  if (range.length >= 2) return range.join(' ~ ');
  const relative = cleanLabel(custom.querySelector('.ant-select-selection-item')?.textContent || '');
  return relative;
};

const readResultRange = (): string =>
  cleanLabel(document.querySelector('.collapse-title')?.textContent || '');

const headerIndex = (headers: string[], name: string) =>
  headers.findIndex((header) => header.toLowerCase() === name);

const rowCells = (row: Element): HTMLElement[] =>
  Array.from(row.children).filter((node): node is HTMLElement =>
    node instanceof HTMLElement && (node.matches('td') || node.classList.contains('ant-table-cell')),
  );

const isCollectableLogRow = (row: Element): boolean => {
  if (row.classList.contains('ant-table-measure-row')) return false;
  if (row.classList.contains('ant-table-expanded-row')) return false;
  if (row.closest('.ant-table-expanded-row')) return false;
  return rowCells(row).length > 0;
};

const readVisibleLogRows = (): string[] => {
  const tableArea = document.querySelector('[class*="tableArea"]');
  const table = tableArea?.querySelector('table');
  if (!tableArea || !table) return [];
  const headers = Array.from(table.querySelectorAll('thead th')).map((cell) =>
    cleanLabel(cell.textContent || ''),
  );
  const timeIdx = headerIndex(headers, 'timestamp');
  const messageIdx = headerIndex(headers, 'message');
  if (timeIdx < 0 || messageIdx < 0) return [];
  const virtualRows = Array.from(tableArea.querySelectorAll('.ant-table-tbody-virtual .ant-table-row'));
  const rows = virtualRows.length
    ? virtualRows
    : Array.from(table.querySelectorAll('tbody tr.ant-table-row, tbody tr'));
  return rows
    .filter(isCollectableLogRow)
    .map((row) => {
      const cells = rowCells(row);
      const time = cleanLabel(cells[timeIdx]?.textContent || '');
      const message = redactSensitiveText(cleanLabel(cells[messageIdx]?.textContent || ''));
      return [time, message].filter(Boolean).join(' | ');
    })
    .filter(Boolean);
};

interface LogSearchStamp {
  view: string;
  query: string;
  timeRange: string;
  groups: string;
  resultRange: string;
  rowFingerprint: string;
  loading: boolean;
}

export const readLogSearchStamp = (): LogSearchStamp => {
  const tableArea = document.querySelector('[class*="tableArea"]');
  const tableSpinRoot = tableArea?.querySelector('.ant-table')?.closest('.ant-spin-nested-loading');
  const loading = Boolean(tableSpinRoot?.querySelector('.ant-spin-spinning'));
  const rows = loading ? [] : readVisibleLogRows();
  return {
    view: activeLogSearchView(),
    query: readQuery(),
    timeRange: readTimeRange(),
    groups: readLogGroups(),
    resultRange: readResultRange(),
    rowFingerprint: rows.join('|'),
    loading,
  };
};

export const buildLogSearchCurrentTime = (stamp: LogSearchStamp): string =>
  [stamp.query, stamp.timeRange, stamp.groups, stamp.resultRange, stamp.rowFingerprint, stamp.loading ? 'loading' : '']
    .filter(Boolean)
    .join('::');

const listTextSections = (stamp: LogSearchStamp): AiContextSection[] => {
  const identity = [
    '正在查看日志搜索',
    stamp.query ? `查询: ${stamp.query}` : '',
    stamp.timeRange ? `时间筛选: ${stamp.timeRange}` : '',
    stamp.groups ? `日志分组: ${stamp.groups}` : '',
    stamp.loading ? '表格加载中' : '',
  ].filter(Boolean);
  const rows = stamp.loading ? [] : readVisibleLogRows();
  return [
    {
      id: 'log-search-identity',
      label: '当前日志搜索',
      content: identity.join('\n'),
      priority: 10,
    },
    ...(stamp.resultRange
      ? [{
        id: 'log-search-range',
        label: '结果范围',
        content: stamp.resultRange,
        priority: 8,
      }]
      : []),
    ...(rows.length
      ? [{
        id: 'log-search-messages',
        label: '可见日志',
        content: rows.join('\n'),
        priority: 4,
      }]
      : []),
  ];
};

export function getMessage(): PageContextMessage {
  if (!isLogSearchListView()) return { title: '' };
  const stamp = readLogSearchStamp();
  const title = `${TITLE_PREFIX}${stamp.view}`;
  const currentTime = buildLogSearchCurrentTime(stamp);
  return currentTime ? { title, currentTime } : { title };
}

export function getTextContext(): Partial<AiPageContext> {
  if (!isLogSearchListView()) return { sections: [], images: [] };
  const stamp = readLogSearchStamp();
  return {
    url: typeof window === 'undefined' ? '' : window.location.href,
    app: 'log',
    title: document.title || '日志搜索',
    sections: listTextSections(stamp),
    images: [],
  };
}

export async function getContext(toolkit: PageContextToolkit): Promise<Partial<AiPageContext>> {
  void toolkit;
  if (!isLogSearchListView()) return getTextContext();
  const stamp = readLogSearchStamp();
  const base = getTextContext();
  console.info('[ai-page-context] page data updated at', {
    view: stamp.view,
    timeRange: stamp.timeRange || '(none)',
    groups: stamp.groups,
  });
  return base;
}
