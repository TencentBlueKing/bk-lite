import type { ChartSnapshot } from '@/components/chart-snapshot';
import type {
  AiContextSection,
  AiPageContext,
  PageContextMessage,
  PageContextToolkit,
} from '@/components/ai-page-context/types';
import { PAGE_CONTEXT_MAX_IMAGES } from '@/components/ai-page-context/types';

const DASHBOARD_TYPE = 'dashboard';
const TITLE_PREFIX = 'ops-analysis-dashboard:';
const DECORATIVE_CHART_MAX_HEIGHT = 72;
const TABLE_ROW_LIMIT = 10;
const COUNT_PLACEHOLDER = /已选\s*\d+\s*项/;
const EMPTY_HINT = /暂无数据|无数据|No [Dd]ata/;

const cleanLabel = (value: string) => value.replace(/\s+/g, ' ').trim();

export const isOpsAnalysisDashboardView = (search = typeof window === 'undefined' ? '' : window.location.search) =>
  new URLSearchParams(search).get('type') === DASHBOARD_TYPE;

export const canvasIdFromSearch = (search = typeof window === 'undefined' ? '' : window.location.search) =>
  new URLSearchParams(search).get('id') || '';

const isHidden = (element: Element | null): boolean => {
  for (let node: Element | null = element; node; node = node.parentElement) {
    if (!(node instanceof HTMLElement)) continue;
    if (node.hidden || node.getAttribute('aria-hidden') === 'true') return true;
    const display = node.style.display || (typeof getComputedStyle === 'function' ? getComputedStyle(node).display : '');
    if (display === 'none') return true;
  }
  return false;
};

const widgetShell = (node: Element | null) =>
  node?.closest<HTMLElement>('[data-node-kind="widget"]') || node?.closest<HTMLElement>('.widget');

const widgetBody = (widget: Element) =>
  widget.querySelector<HTMLElement>('.widget-body') || widget;

const widgetTitle = (widget: Element) =>
  cleanLabel(widget.querySelector('.widget-header h4, .widget-header h3, h4')?.textContent || '');

const isWidgetLoading = (widget: Element) =>
  Boolean(widgetBody(widget).querySelector('.ant-spin-spinning, .ant-spin.ant-spin-spinning'));

const isWidgetCollapsed = (widget: Element) => isHidden(widgetBody(widget)) || isHidden(widget);

const titledNames = (root: Element | null): string => {
  if (!root) return '';
  const titled = [root, ...Array.from(root.querySelectorAll('[title]'))].find(
    (node) => node instanceof HTMLElement && node.title && !COUNT_PLACEHOLDER.test(node.title),
  );
  return titled instanceof HTMLElement ? cleanLabel(titled.title) : '';
};

const readOpenTableSelectNames = (filterName: string): string => {
  const dialogs = Array.from(document.querySelectorAll<HTMLElement>('.ant-modal, [role="dialog"]'));
  for (const dialog of dialogs) {
    if (isHidden(dialog)) continue;
    const title = cleanLabel(dialog.querySelector('.ant-modal-title')?.textContent || '');
    if (title && title !== filterName) continue;
    const names = Array.from(dialog.querySelectorAll('tr.ant-table-row-selected, tr.ant-table-row-checked'))
      .map((row) => {
        const cells = Array.from(row.querySelectorAll('td')).filter(
          (cell) => !cell.querySelector('.ant-checkbox, input[type="checkbox"]'),
        );
        const texts = cells.map((cell) => cleanLabel(cell.textContent || '')).filter(Boolean);
        return texts[0] || '';
      })
      .filter(Boolean);
    if (names.length) return names.join('、');
  }
  return '';
};

const expandCountPlaceholder = (visible: string, group: HTMLElement, filterName: string): string => {
  if (!COUNT_PLACEHOLDER.test(visible)) return visible;
  const names = titledNames(group.querySelector('.ant-select-selection-item')) || readOpenTableSelectNames(filterName);
  return names ? `${visible}（${names}）` : visible;
};

const readPickerRange = (group: HTMLElement): string => {
  const values = Array.from(group.querySelectorAll<HTMLInputElement>('.ant-picker-input input'))
    .map((node) => cleanLabel(node.value || ''))
    .filter(Boolean);
  return values.join(' ~ ');
};

const readFilterControlValue = (group: HTMLElement, label: Element): string => {
  const filterName = cleanLabel(label.textContent || '').replace(/[:：]\s*$/, '');
  const selectItems = Array.from(group.querySelectorAll('.ant-select-selection-item'))
    .map((node) => cleanLabel(node.textContent || ''))
    .filter(Boolean);
  const select = [...new Set(selectItems)].join('、');
  const picker = readPickerRange(group);
  if (select) {
    const expanded = expandCountPlaceholder(select, group, filterName);
    return picker && /自定义/.test(select) ? `${expanded} ${picker}` : expanded;
  }
  if (picker) return picker;

  const checkedRadio = group.querySelector('.ant-radio-button-wrapper-checked, .ant-radio-wrapper-checked');
  const radioText = cleanLabel(checkedRadio?.textContent || '');
  if (radioText) return radioText;

  const typedInput = Array.from(group.querySelectorAll('input')).find((node) => {
    if (!(node instanceof HTMLInputElement)) return false;
    if (node.closest('.ant-picker')) return false;
    return node.type !== 'radio' && node.type !== 'checkbox' && node.type !== 'hidden';
  });
  if (typedInput instanceof HTMLInputElement) {
    return cleanLabel(typedInput.value || '');
  }

  if (group.querySelector('.ant-spin')) return '加载中';

  const control = label.nextElementSibling;
  if (control instanceof HTMLElement) {
    return cleanLabel(control.textContent || '');
  }
  return '';
};

const readFilterFields = (): string[] => {
  const labels = Array.from(document.querySelectorAll('span')).filter((node) => {
    if (node.closest('[data-export-hidden]')) return false;
    if (node.closest('[data-node-kind="widget"]')) return false;
    return /[:：]\s*$/.test(cleanLabel(node.textContent || ''));
  });
  const lines: string[] = [];
  for (const label of labels) {
    const group = label.parentElement;
    if (!(group instanceof HTMLElement)) continue;
    const name = cleanLabel(label.textContent || '').replace(/[:：]\s*$/, '');
    if (!name) continue;
    const value = readFilterControlValue(group, label);
    lines.push(value ? `${name}: ${value}` : `${name}:`);
  }
  return lines;
};

const readDashboardName = () => {
  const heading = Array.from(document.querySelectorAll('h2')).find((node) => !node.closest('[data-node-kind="widget"]'));
  return cleanLabel(heading?.textContent || '');
};

const visibleWidgets = () =>
  Array.from(document.querySelectorAll<HTMLElement>('[data-node-kind="widget"]')).filter(
    (widget) => !isWidgetCollapsed(widget),
  );

const isTopNWidget = (widget: Element) =>
  Boolean(widget.querySelector('.h-2\\.5.w-full.overflow-hidden.rounded-full'));

const isTableWidget = (widget: Element) =>
  Boolean(widget.querySelector('.ant-table-tbody, table'));

const isTopNValueCell = (cell: Element | undefined) => {
  const className = cell instanceof HTMLElement ? cell.className : '';
  return className.includes('tabular-nums') || className.includes('font-semibold');
};

const readTopNRows = (widget: Element): string[] => {
  const grids = Array.from(widget.querySelectorAll('.grid.items-center, .grid'));
  const rows: string[] = [];
  for (const grid of grids) {
    const cells = Array.from(grid.children);
    for (let index = 0; index < cells.length && rows.length < TABLE_ROW_LIMIT; index += 3) {
      const name = cleanLabel(cells[index]?.textContent || '');
      const value = cleanLabel(cells[index + 2]?.textContent || '');
      if (!name || !value || !isTopNValueCell(cells[index + 2])) continue;
      rows.push(`${name} ${value}`);
    }
    if (rows.length >= TABLE_ROW_LIMIT) break;
  }
  return rows;
};

const readTableRows = (widget: Element): string[] => {
  const headerCells = Array.from(widget.querySelectorAll('thead th, thead td')).map((cell) =>
    cleanLabel(cell.textContent || ''),
  );
  const header = headerCells.filter(Boolean).join(' | ');
  const bodyRows = Array.from(widget.querySelectorAll('.ant-table-tbody tr, tbody tr'))
    .map((row) =>
      Array.from(row.querySelectorAll('td'))
        .map((cell) => cleanLabel(cell.textContent || ''))
        .filter(Boolean)
        .join(' | '),
    )
    .filter(Boolean)
    .slice(0, TABLE_ROW_LIMIT);
  return [header, ...bodyRows].filter(Boolean);
};

const readMultiValueRows = (widget: Element): string[] => {
  if (isTopNWidget(widget) || isTableWidget(widget)) return [];
  const valueNodes = Array.from(widgetBody(widget).querySelectorAll('.font-semibold'));
  const rows: string[] = [];
  for (const valueNode of valueNodes) {
    const row = valueNode.parentElement;
    if (!row) continue;
    const value = cleanLabel(valueNode.textContent || '');
    const label = Array.from(row.children)
      .map((child) => cleanLabel(child.textContent || ''))
      .find((text) => text && text !== value);
    if (!label || !value) continue;
    rows.push(`${label} ${value}`);
    if (rows.length >= TABLE_ROW_LIMIT) break;
  }
  return rows.length > 1 ? rows : [];
};

const readCardListRows = (widget: Element): string[] =>
  Array.from(widgetBody(widget).querySelectorAll('article'))
    .map((article) => {
      const primary = cleanLabel(article.querySelector('.text-sm')?.textContent || '');
      const trailingNodes = Array.from(article.querySelectorAll('.text-xs.font-medium'));
      const trailing = cleanLabel(trailingNodes.at(-1)?.textContent || '');
      return [primary, trailing].filter(Boolean).join(' ');
    })
    .filter(Boolean)
    .slice(0, TABLE_ROW_LIMIT);

const listLikeRows = (widget: Element): string[] => {
  if (isTopNWidget(widget)) return readTopNRows(widget);
  if (isTableWidget(widget)) return readTableRows(widget);
  const multi = readMultiValueRows(widget);
  if (multi.length) return multi;
  return readCardListRows(widget);
};

const readSingleValue = (widget: Element) => {
  if (isTopNWidget(widget) || isTableWidget(widget)) return '';
  if (readMultiValueRows(widget).length) return '';
  const metric = widgetBody(widget).querySelector('.font-semibold');
  return cleanLabel(metric?.textContent || '');
};

const readWidgetError = (widget: Element): string => {
  const icon = widgetBody(widget).querySelector('.anticon-exclamation-circle, .anticon-exclamation-circle-outlined');
  if (!icon) return '';
  const holder = icon.parentElement;
  if (!holder) return '';
  const texts = Array.from(holder.querySelectorAll('span'))
    .map((node) => cleanLabel(node.textContent || ''))
    .filter((text) => text && !text.includes('exclamation'));
  return texts.at(-1) || '';
};

const readWidgetEmpty = (widget: Element): string => {
  const description = cleanLabel(widgetBody(widget).querySelector('.ant-empty-description')?.textContent || '');
  if (description) return description;
  if (readSingleValue(widget) || isTableWidget(widget) || isTopNWidget(widget)) return '';
  if (readMultiValueRows(widget).length || readCardListRows(widget).length) {
    return '';
  }
  const spans = Array.from(widgetBody(widget).querySelectorAll('span'))
    .map((node) => cleanLabel(node.textContent || ''))
    .filter(Boolean);
  return spans.find((text) => EMPTY_HINT.test(text)) || '';
};

export const isDecorativeOpsAnalysisChart = (dom: HTMLElement): boolean => {
  const widget = widgetShell(dom);
  if (widget && (isWidgetLoading(widget) || isWidgetCollapsed(widget) || readWidgetError(widget))) return true;
  const height = dom.getBoundingClientRect().height;
  if (height > 0 && height < DECORATIVE_CHART_MAX_HEIGHT) return true;
  if (widget && readSingleValue(widget) && !isTopNWidget(widget) && !isTableWidget(widget)) {
    return true;
  }
  return false;
};

const readingKey = (dom: HTMLElement) => {
  const rect = dom.getBoundingClientRect();
  return [rect.top, rect.left];
};

export const listScreenshotableChartDoms = (): HTMLElement[] => {
  if (!isOpsAnalysisDashboardView()) return [];
  const nodes = Array.from(document.querySelectorAll<HTMLElement>('[_echarts_instance_]')).filter(
    (dom) => !isDecorativeOpsAnalysisChart(dom),
  );
  return nodes
    .sort((left, right) => {
      const [topA, leftA] = readingKey(left);
      const [topB, leftB] = readingKey(right);
      if (topA !== topB) return topA - topB;
      return leftA - leftB;
    })
    .slice(0, PAGE_CONTEXT_MAX_IMAGES);
};

const captionFromWidget = (dom: HTMLElement) => {
  const widget = widgetShell(dom);
  return widget ? widgetTitle(widget) : '';
};

const optionCaptionWithoutGenericTitle = (caption = ''): string =>
  caption.replace(/^图表；/, '').replace(/^图表$/, '');

export const mergeOpsAnalysisChartCaption = (title: string, shotCaption = ''): string => {
  const rest = optionCaptionWithoutGenericTitle(shotCaption);
  if (!title) return rest || shotCaption;
  return rest && rest !== title ? `${title}；${rest}` : title;
};

export interface OpsAnalysisDashboardStamp {
  canvasId: string;
  dashboardName: string;
  filterText: string;
  valueFingerprint: string;
  loadingCount: number;
  errorCount: number;
}

export const readOpsAnalysisDashboardStamp = (): OpsAnalysisDashboardStamp => {
  const widgets = visibleWidgets();
  const loadingCount = widgets.filter(isWidgetLoading).length;
  const errorCount = widgets.filter((widget) => Boolean(readWidgetError(widget))).length;
  const readyWidgets = widgets.filter((widget) => !isWidgetLoading(widget));
  const valueFingerprint = readyWidgets
    .map((widget) => {
      const title = widgetTitle(widget);
      const error = readWidgetError(widget);
      if (error) return `${title}:${error}`;
      const rows = listLikeRows(widget);
      if (rows.length) return `${title}:${rows.slice(0, 3).join('|')}`;
      return `${title}:${readSingleValue(widget)}`;
    })
    .filter(Boolean)
    .join('||');
  return {
    canvasId: canvasIdFromSearch(),
    dashboardName: readDashboardName(),
    filterText: readFilterFields().join('；'),
    valueFingerprint,
    loadingCount,
    errorCount,
  };
};

export const buildOpsAnalysisCurrentTime = (stamp: OpsAnalysisDashboardStamp): string =>
  [stamp.filterText, stamp.valueFingerprint].filter(Boolean).join('::');

const dashboardTextSections = (stamp: OpsAnalysisDashboardStamp): AiContextSection[] => {
  const identityLines = [
    '正在查看运营分析仪表盘',
    stamp.dashboardName ? `盘名: ${stamp.dashboardName}` : '',
    stamp.canvasId ? `画布 id: ${stamp.canvasId}` : '',
    stamp.filterText ? `当前筛选: ${stamp.filterText}` : '',
    stamp.loadingCount > 0 ? `还有 ${stamp.loadingCount} 个组件未加载完` : '',
    stamp.errorCount > 0 ? `有 ${stamp.errorCount} 个组件查询失败` : '',
  ].filter(Boolean);

  const widgets = visibleWidgets();
  const cardLines = widgets.flatMap((widget) => {
    const title = widgetTitle(widget);
    if (!title) return [];
    if (isWidgetLoading(widget)) return [`${title}: 加载中`];
    const error = readWidgetError(widget);
    if (error) return [`${title}: ${error}`];
    const empty = readWidgetEmpty(widget);
    if (empty) return [`${title}: ${empty}`];
    const single = readSingleValue(widget);
    return [single ? `${title}: ${single}` : title];
  });

  const tableLines = widgets.flatMap((widget) => {
    if (isWidgetLoading(widget) || readWidgetError(widget)) return [];
    const title = widgetTitle(widget);
    const rows = listLikeRows(widget);
    return rows.length ? [`${title}`, ...rows] : [];
  });

  return [
    {
      id: 'dashboard-identity',
      label: '当前仪表盘',
      content: identityLines.join('\n'),
      priority: 10,
    },
    ...(cardLines.length
      ? [{
        id: 'dashboard-cards',
        label: '可见卡片',
        content: cardLines.join('\n'),
        priority: 8,
      }]
      : []),
    ...(tableLines.length
      ? [{
        id: 'dashboard-tables',
        label: '表与排行',
        content: tableLines.join('\n'),
        priority: 4,
      }]
      : []),
  ];
};

export function getMessage(): PageContextMessage {
  if (!isOpsAnalysisDashboardView()) return { title: '' };
  const title = `${TITLE_PREFIX}${canvasIdFromSearch()}`;
  const currentTime = buildOpsAnalysisCurrentTime(readOpsAnalysisDashboardStamp());
  return currentTime ? { title, currentTime } : { title };
}

export function getTextContext(): Partial<AiPageContext> {
  if (!isOpsAnalysisDashboardView()) {
    return { sections: [], images: [] };
  }
  const stamp = readOpsAnalysisDashboardStamp();
  return {
    url: typeof window === 'undefined' ? '' : window.location.href,
    app: 'ops-analysis',
    title: stamp.dashboardName || document.title || '运营分析仪表盘',
    sections: dashboardTextSections(stamp),
    images: [],
  };
}

export async function getContext(
  toolkit: PageContextToolkit,
): Promise<Partial<AiPageContext>> {
  if (!isOpsAnalysisDashboardView()) {
    return { sections: [], images: [] };
  }
  const stamp = readOpsAnalysisDashboardStamp();
  const base = getTextContext();
  const ordered = listScreenshotableChartDoms();
  const captured = await Promise.all(
    ordered.map(async (dom): Promise<ChartSnapshot | null> => {
      const [shot] = await toolkit.captureEchartsFromDoms([dom], 1);
      if (!shot) return null;
      const title = captionFromWidget(dom);
      return {
        ...shot,
        caption: mergeOpsAnalysisChartCaption(title, shot.caption),
      };
    }),
  );
  const images = captured.filter((item): item is ChartSnapshot => Boolean(item));
  const chartLines = images.map((image, index) => `${index + 1}. ${image.caption}`);
  const dataUpdatedAt = buildOpsAnalysisCurrentTime(stamp);
  console.info('[ai-page-context] page data updated at', dataUpdatedAt, {
    timeRange: stamp.filterText || '(none)',
    canvasId: stamp.canvasId,
    loadingCount: stamp.loadingCount,
    errorCount: stamp.errorCount,
    charts: chartLines,
  });
  return {
    ...base,
    sections: [
      ...(base.sections || []),
      ...(chartLines.length
        ? [{
          id: 'visible-charts',
          label: '可见图表',
          content: chartLines.join('\n'),
          priority: 6,
        }]
        : []),
    ],
    images,
  };
}
