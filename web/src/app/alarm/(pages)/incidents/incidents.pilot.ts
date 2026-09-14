import type {
  AiContextSection,
  AiPageContext,
  PageContextMessage,
  PageContextToolkit,
} from '@/components/ai-page-context/types';

const TITLE = 'alarm-incident:list';
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

export const isIncidentListView = (
  pathname = typeof window === 'undefined' ? '' : window.location.pathname,
): boolean => {
  const path = normalizedPathname(pathname);
  return path.includes('/alarm/incidents/') && !path.includes('/alarm/incidents/detail/');
};

const listRoot = (): HTMLElement | null => {
  const filters = Array.from(document.querySelectorAll<HTMLElement>('[class*="filters"]'))
    .find((node) => !isHidden(node) && /过滤项|Filter/i.test(node.textContent || ''));
  return filters?.parentElement || null;
};

export interface IncidentListStamp {
  filterText: string;
  rangeText: string;
  rowFingerprint: string;
  loading: boolean;
  emptyText: string;
}

const readCheckboxGroups = (filterRoot: Element | null): string[] => {
  if (!filterRoot) return [];
  const groups = Array.from(filterRoot.querySelectorAll('[class*="item"]'));
  const blocks = groups.length
    ? groups
    : Array.from(filterRoot.querySelectorAll('.collapse-title')).map((title) =>
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
  const search = root?.querySelector<HTMLInputElement>('[class*="content"] input.ant-input');
  if (search?.value) lines.push(`搜索: ${cleanLabel(search.value)}`);
  return lines;
};

const readTableRows = (): string[] => {
  const table = listRoot()?.querySelector('[class*="content"] .ant-table, [class*="content"] table');
  if (!table) return [];
  const headerCells = Array.from(table.querySelectorAll('thead th')).map((cell, index, all) => {
    if (index === all.length - 1 && /详情|Detail|操作/.test(cell.textContent || '')) return '';
    return cleanLabel(cell.textContent || '');
  });
  const header = headerCells.filter(Boolean).join(' | ');
  const bodyRows = Array.from(table.querySelectorAll('.ant-table-tbody tr.ant-table-row, .ant-table-tbody tr, tbody tr'))
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
  const content = listRoot()?.querySelector('[class*="content"]');
  const total = cleanLabel(content?.querySelector('.ant-pagination-total-text')?.textContent || '');
  const page = cleanLabel(content?.querySelector('.ant-pagination-item-active')?.textContent || '');
  return [total, page ? `当前第 ${page} 页` : ''].filter(Boolean).join('；');
};

export const readIncidentListStamp = (): IncidentListStamp => {
  const rows = readTableRows();
  const content = listRoot()?.querySelector('[class*="content"]');
  return {
    filterText: readFilterFields().join('；'),
    rangeText: readRangeText(),
    rowFingerprint: rows.slice(0, 4).join('|'),
    loading: Boolean(content?.querySelector('.ant-spin-spinning')),
    emptyText: cleanLabel(content?.querySelector('.ant-empty-description')?.textContent || '')
      || (rows.length <= 1 ? (Array.from(content?.querySelectorAll('span') || [])
        .map((node) => cleanLabel(node.textContent || ''))
        .find((text) => EMPTY_HINT.test(text)) || '') : ''),
  };
};

export const buildIncidentListCurrentTime = (stamp: IncidentListStamp): string =>
  [stamp.filterText, stamp.rangeText, stamp.rowFingerprint, stamp.loading ? 'loading' : '']
    .filter(Boolean)
    .join('::');

const listTextSections = (stamp: IncidentListStamp): AiContextSection[] => {
  const identity = [
    '正在查看事故列表',
    stamp.filterText ? `当前筛选: ${stamp.filterText}` : '',
    stamp.loading ? '表格加载中' : '',
    stamp.emptyText ? `空态: ${stamp.emptyText}` : '',
  ].filter(Boolean);
  const rows = stamp.loading ? [] : readTableRows();
  return [
    {
      id: 'incident-list-identity',
      label: '当前事故列表',
      content: identity.join('\n'),
      priority: 10,
    },
    ...(stamp.rangeText
      ? [{
        id: 'incident-list-range',
        label: '结果范围',
        content: stamp.rangeText,
        priority: 8,
      }]
      : []),
    ...(rows.length
      ? [{
        id: 'incident-list-table',
        label: '当前页事故',
        content: rows.join('\n'),
        priority: 4,
      }]
      : []),
  ];
};

export function getMessage(): PageContextMessage {
  if (!isIncidentListView()) return { title: '' };
  const stamp = readIncidentListStamp();
  const currentTime = buildIncidentListCurrentTime(stamp);
  return currentTime ? { title: TITLE, currentTime } : { title: TITLE };
}

export function getTextContext(): Partial<AiPageContext> {
  if (!isIncidentListView()) return { sections: [], images: [] };
  const stamp = readIncidentListStamp();
  return {
    url: typeof window === 'undefined' ? '' : window.location.href,
    app: 'alarm',
    title: document.title || '事故列表',
    sections: listTextSections(stamp),
    images: [],
  };
}

export async function getContext(toolkit: PageContextToolkit): Promise<Partial<AiPageContext>> {
  void toolkit;
  if (!isIncidentListView()) return getTextContext();
  const base = getTextContext();
  const stamp = readIncidentListStamp();
  console.info('[ai-page-context] page data updated at', buildIncidentListCurrentTime(stamp), {
    range: stamp.rangeText,
  });
  return base;
}
