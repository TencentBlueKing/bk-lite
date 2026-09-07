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

export interface OpsAnalysisDashboardStamp {
  canvasId: string;
  dashboardName: string;
  filterText: string;
  valueFingerprint: string;
  loadingCount: number;
}

const readFilterControlValue = (group: HTMLElement, label: Element): string => {
  const select = cleanLabel(group.querySelector('.ant-select-selection-item')?.textContent || '');
  if (select) return select;

  const checkedRadio = group.querySelector('.ant-radio-button-wrapper-checked, .ant-radio-wrapper-checked');
  const radioText = cleanLabel(checkedRadio?.textContent || '');
  if (radioText) return radioText;

  const typedInput = Array.from(group.querySelectorAll('input')).find((node) => {
    if (!(node instanceof HTMLInputElement)) return false;
    return node.type !== 'radio' && node.type !== 'checkbox' && node.type !== 'hidden';
  });
  if (typedInput instanceof HTMLInputElement) {
    return cleanLabel(typedInput.value || '');
  }

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
  Boolean(widget.querySelector('.h-2\\.5.w-full.overflow-hidden.rounded-full, .rounded-full.h-2\\.5'));

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

const readSingleValue = (widget: Element) => {
  if (isTopNWidget(widget) || isTableWidget(widget)) return '';
  const metric = widget.querySelector('.font-semibold');
  return cleanLabel(metric?.textContent || '');
};

export const isDecorativeOpsAnalysisChart = (dom: HTMLElement): boolean => {
  const widget = widgetShell(dom);
  if (widget && (isWidgetLoading(widget) || isWidgetCollapsed(widget))) return true;
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

export const readOpsAnalysisDashboardStamp = (): OpsAnalysisDashboardStamp => {
  const widgets = visibleWidgets();
  const loadingCount = widgets.filter(isWidgetLoading).length;
  const readyWidgets = widgets.filter((widget) => !isWidgetLoading(widget));
  const valueFingerprint = readyWidgets
    .map((widget) => {
      const title = widgetTitle(widget);
      if (isTopNWidget(widget)) return `${title}:${readTopNRows(widget).join('|')}`;
      if (isTableWidget(widget)) return `${title}:${readTableRows(widget).slice(0, 3).join('|')}`;
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
  ].filter(Boolean);

  const widgets = visibleWidgets();
  const cardLines = widgets.flatMap((widget) => {
    const title = widgetTitle(widget);
    if (!title) return [];
    if (isWidgetLoading(widget)) return [title];
    const single = readSingleValue(widget);
    return [single ? `${title}: ${single}` : title];
  });

  const tableLines = widgets.flatMap((widget) => {
    if (isWidgetLoading(widget)) return [];
    const title = widgetTitle(widget);
    if (isTopNWidget(widget)) {
      const rows = readTopNRows(widget);
      return rows.length ? [`${title}`, ...rows] : [];
    }
    if (isTableWidget(widget)) {
      const rows = readTableRows(widget);
      return rows.length ? [`${title}`, ...rows] : [];
    }
    return [];
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
        caption: title ? (shot.caption && shot.caption !== '图表' ? `${title}；${shot.caption}` : title) : shot.caption,
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
