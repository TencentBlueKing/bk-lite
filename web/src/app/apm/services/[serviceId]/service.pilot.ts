import type { ChartSnapshot } from '@/components/chart-snapshot';
import type {
  AiContextSection,
  AiPageContext,
  PageContextMessage,
  PageContextToolkit,
} from '@/components/ai-page-context/types';
import { redactSensitiveText } from '@/components/ai-page-context/redact-sensitive-text';

const TITLE_PREFIX = 'apm-service:';
const OVERVIEW_TAB = 'overview';
const ERRORS_TAB = 'errors';
const KNOWN_TABS = new Set(['overview', 'traces', 'errors', 'runtime', 'deployments', 'slo']);
const OVERVIEW_CHART_LIMIT = 3;
const ERROR_CHART_LIMIT = 1;
const ENDPOINT_LIMIT = 10;
const TRACE_ROW_LIMIT = 20;
const ERROR_TYPE_LIMIT = 8;
const ERROR_ENDPOINT_LIMIT = 8;
const ERROR_SAMPLE_LIMIT = 8;
const DEPLOYMENT_ROW_LIMIT = 15;
const SLO_ROW_LIMIT = 10;
const CELL_CHAR_LIMIT = 160;
const KPI_VALUE_SELECTOR = '.text-2xl.font-bold.tabular-nums';
const HEADING_SELECTOR = 'strong, h1, h2, h3, h4, .ant-typography';
const OPERATION_HEADER = /^(操作|Actions?)$/i;

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

const visibleText = (node: Element | null): string => {
  if (!node) return '';
  const pieces: string[] = [];
  const walk = (current: Node) => {
    if (current.nodeType === Node.TEXT_NODE) {
      const text = cleanLabel(current.textContent || '');
      if (text) pieces.push(text);
      return;
    }
    current.childNodes.forEach(walk);
  };
  walk(node);
  return pieces.join(' ');
};

const sanitizeLine = (value: string): string => {
  const redacted = redactSensitiveText(cleanLabel(value));
  if (redacted.length <= CELL_CHAR_LIMIT) return redacted;
  return `${redacted.slice(0, CELL_CHAR_LIMIT)}…`;
};

const sanitizeNode = (node: Element | null): string => sanitizeLine(visibleText(node));

const normalizedPathname = (pathname = typeof window === 'undefined' ? '' : window.location.pathname) =>
  pathname.endsWith('/') ? pathname : `${pathname}/`;

const serviceIdFromPath = (pathname = typeof window === 'undefined' ? '' : window.location.pathname) => {
  const match = normalizedPathname(pathname).match(/\/apm\/services\/([^/]+)\//);
  if (!match) return '';
  const id = match[1];
  if (['slo', 'topology', 'applications'].includes(id)) return '';
  return id;
};

const activeServiceTab = (): string =>
  document.querySelector('.ant-tabs-tab-active')?.getAttribute('data-node-key') || '';

const activePane = (): HTMLElement | null => {
  const pane = document.querySelector<HTMLElement>('.ant-tabs-tabpane-active');
  if (!pane || isHidden(pane)) return null;
  return pane;
};

const readTimeRange = (): string =>
  cleanLabel(document.querySelector('.ant-segmented-item-selected .ant-segmented-item-label')?.textContent || '');

const readEnvironment = (): string => {
  const labeled = document.querySelector<HTMLElement>(
    '[aria-label*="选择环境"], [aria-label*="Environment"], [aria-label*="environment" i]',
  );
  const fromSelect = cleanLabel(labeled?.querySelector('.ant-select-selection-item')?.textContent || '');
  if (fromSelect) return fromSelect;
  return typeof window === 'undefined' ? '' : new URLSearchParams(window.location.search).get('environment') || '';
};

const readServiceName = (): string => {
  const heading = Array.from(document.querySelectorAll('h1, h2')).find((node) => {
    if (!(node instanceof HTMLElement)) return false;
    if (node.classList.contains('sr-only')) return false;
    return Boolean(cleanLabel(node.textContent || ''));
  });
  return cleanLabel(heading?.textContent || '');
};

const kpiCardRoot = (valueNode: Element): HTMLElement | null => {
  let node = valueNode.parentElement;
  for (let depth = 0; depth < 5 && node; depth += 1) {
    if (node.querySelector('.text-xs.font-medium')) return node;
    node = node.parentElement;
  }
  return valueNode.parentElement;
};

const readKpiCards = (root: ParentNode, options?: { excludeTabs?: boolean }): string[] =>
  Array.from(root.querySelectorAll(KPI_VALUE_SELECTOR))
    .filter((valueNode) => {
      if (!(valueNode instanceof HTMLElement) || isHidden(valueNode)) return false;
      if (options?.excludeTabs && valueNode.closest('.ant-tabs')) return false;
      return true;
    })
    .map((valueNode) => {
      const card = kpiCardRoot(valueNode);
      const label = cleanLabel(card?.querySelector('.text-xs.font-medium')?.textContent || '');
      const value = cleanLabel(valueNode.textContent || '');
      const unit = cleanLabel(valueNode.nextElementSibling?.textContent || '');
      return label && value ? `${label}: ${[value, unit].filter(Boolean).join(' ')}` : '';
    })
    .filter(Boolean);

const readServiceKpiReadings = (): string[] => readKpiCards(document, { excludeTabs: true });

const listChartsIn = (root: HTMLElement): HTMLElement[] => {
  const self = root.hasAttribute('_echarts_instance_') && !isHidden(root) ? [root] : [];
  const nested = Array.from(root.querySelectorAll<HTMLElement>('[_echarts_instance_]')).filter((dom) => !isHidden(dom));
  const seen = new Set<HTMLElement>();
  return [...self, ...nested].filter((dom) => {
    if (seen.has(dom)) return false;
    seen.add(dom);
    return true;
  });
};

const listErrorTrendChartDoms = (pane: HTMLElement): HTMLElement[] => {
  const labeled = Array.from(pane.querySelectorAll<HTMLElement>('[aria-label]')).find((node) =>
    /错误率趋势|error rate trend/i.test(node.getAttribute('aria-label') || ''),
  );
  const scope = labeled || pane;
  return listChartsIn(scope).slice(0, ERROR_CHART_LIMIT);
};

const listActiveTabChartDoms = (): HTMLElement[] => {
  const pane = activePane();
  if (!pane) return [];
  const tab = activeServiceTab();
  if (tab === OVERVIEW_TAB) return listChartsIn(pane).slice(0, OVERVIEW_CHART_LIMIT);
  if (tab === ERRORS_TAB) return listErrorTrendChartDoms(pane);
  return [];
};

const chartTitleNear = (dom: HTMLElement): string => {
  const labeled = dom.closest('[role="img"]') || (dom.hasAttribute('aria-label') ? dom : null);
  const fromAria = cleanLabel(labeled?.getAttribute('aria-label') || '');
  if (fromAria) return fromAria;
  let node: HTMLElement | null = dom;
  for (let depth = 0; depth < 6 && node; depth += 1) {
    let sibling: Element | null = node.previousElementSibling;
    while (sibling) {
      const heading = sibling.matches(HEADING_SELECTOR)
        ? sibling
        : sibling.querySelector(HEADING_SELECTOR);
      const title = cleanLabel(heading?.textContent || '');
      if (title && !heading?.closest('[_echarts_instance_]')) return title;
      const plain = sibling instanceof HTMLElement
        ? cleanLabel(sibling.querySelector('.text-sm.font-semibold')?.textContent || sibling.textContent || '')
        : '';
      if (plain && /趋势|吞吐|错误率|延迟|throughput|error|latency|trend/i.test(plain) && plain.length < 40) {
        return cleanLabel(sibling.querySelector('.text-sm.font-semibold')?.textContent || plain);
      }
      sibling = sibling.previousElementSibling;
    }
    node = node.parentElement;
  }
  return '';
};

const mergeServiceChartCaption = (title: string, shotCaption = ''): string => {
  if (!title) return shotCaption;
  const rest = shotCaption.split('；').slice(1);
  return [title, ...rest].filter(Boolean).join('；');
};

const headingRoot = (
  scope: ParentNode,
  pattern: RegExp,
  hasContent: (node: HTMLElement) => boolean,
): HTMLElement | null => {
  const heading = Array.from(scope.querySelectorAll(HEADING_SELECTOR)).find((node) =>
    pattern.test(cleanLabel(node.textContent || '')),
  );
  if (!(heading instanceof HTMLElement)) return null;
  let node: HTMLElement | null = heading;
  for (let depth = 0; depth < 8 && node; depth += 1) {
    if (hasContent(node)) return node;
    if (node === scope) return node;
    node = node.parentElement;
  }
  return heading.parentElement;
};

const readEmptyCopy = (root: ParentNode): string[] => {
  const loading = Array.from(root.querySelectorAll('[aria-busy="true"]'))
    .filter((node) => node instanceof HTMLElement && !isHidden(node))
    .map((node) => cleanLabel(node.getAttribute('aria-label') || ''))
    .filter(Boolean);
  if (loading.length) return loading;
  const empty = Array.from(root.querySelectorAll('.ant-empty-description'))
    .filter((node) => node instanceof HTMLElement && !isHidden(node))
    .map((node) => sanitizeLine(node.textContent || ''))
    .filter(Boolean);
  const result = Array.from(root.querySelectorAll('.ant-result-title, .ant-result-subtitle'))
    .filter((node) => node instanceof HTMLElement && !isHidden(node))
    .map((node) => sanitizeLine(node.textContent || ''))
    .filter(Boolean);
  return [...empty, ...result];
};

const readTableRows = (root: ParentNode, limit: number): string[] => {
  const table = root.querySelector('table');
  if (!table) return [];
  const headers = Array.from(table.querySelectorAll('thead th')).map((th) => cleanLabel(th.textContent || ''));
  const skip = new Set(
    headers.map((header, index) => (OPERATION_HEADER.test(header) ? index : -1)).filter((index) => index >= 0),
  );
  return Array.from(table.querySelectorAll('tbody tr'))
    .filter((row) => {
      if (!(row instanceof HTMLElement) || isHidden(row)) return false;
      if (row.classList.contains('ant-table-measure-row') || row.classList.contains('ant-table-placeholder')) {
        return false;
      }
      return Boolean(row.querySelector('td'));
    })
    .slice(0, limit)
    .map((row) => Array.from(row.querySelectorAll('td'))
      .map((cell, index) => (skip.has(index) ? '' : sanitizeNode(cell)))
      .filter(Boolean)
      .join(' · '))
    .filter(Boolean);
};

const section = (id: string, label: string, lines: string[], priority: number): AiContextSection[] =>
  lines.length
    ? [{ id, label, content: lines.join('\n'), priority }]
    : [];

const readOverviewEndpoints = (pane: HTMLElement): string[] => {
  const root = headingRoot(
    pane,
    /Top 端点|Top endpoints/i,
    (node) => Boolean(
      node.querySelector('.ant-list-item, .ant-empty-description, .ant-list-empty-text'),
    ),
  );
  if (!root) return [];
  const rows = Array.from(root.querySelectorAll('.ant-list-item'))
    .filter((item) => item instanceof HTMLElement && !isHidden(item))
    .map((item) => {
      const path = sanitizeLine(item.querySelector('a')?.textContent || '');
      const meta = sanitizeLine(item.querySelector('.tabular-nums')?.textContent || '');
      return [path, meta].filter(Boolean).join(' · ');
    })
    .filter(Boolean)
    .slice(0, ENDPOINT_LIMIT);
  return rows.length ? rows : readEmptyCopy(root);
};

const readOverviewDependencies = (pane: HTMLElement): string[] => {
  const root = headingRoot(
    pane,
    /依赖关系|Dependencies/i,
    (node) => {
      const text = node.textContent || '';
      return Boolean(node.querySelector('.ant-tag'))
        || /上游|下游|upstream|downstream|无上游|无向下|no upstream|no downstream/i.test(text);
    },
  );
  if (!root) return [];
  const lines: string[] = [];
  const seen = new Set<string>();
  Array.from(root.querySelectorAll('.ant-typography, .ant-tag')).forEach((node) => {
    const text = sanitizeLine(node.textContent || '');
    if (!text || /依赖关系|Dependencies/i.test(text) || seen.has(text)) return;
    if (
      node instanceof HTMLElement && node.matches('.ant-tag')
      || /上游|下游|upstream|downstream|无上游|无向下|no upstream|no downstream/i.test(text)
    ) {
      seen.add(text);
      lines.push(text);
    }
  });
  return lines;
};

const overviewSections = (pane: HTMLElement): AiContextSection[] => {
  const collected = [
    ...section('apm-service-endpoints', 'Top 端点', readOverviewEndpoints(pane), 8),
    ...section('apm-service-dependencies', '依赖关系', readOverviewDependencies(pane), 8),
  ];
  if (collected.length) return collected;
  return section('apm-service-overview', '概览', readEmptyCopy(pane), 8);
};

const tracesSections = (pane: HTMLElement): AiContextSection[] => {
  const root = headingRoot(
    pane,
    /近窗调用链样本|Recent-window trace samples|recent traces/i,
    (node) => Boolean(node.querySelector('table, .ant-empty-description, [aria-busy="true"]')),
  ) || pane;
  const rows = readTableRows(root, TRACE_ROW_LIMIT);
  return section('apm-service-traces', '近窗调用链样本', rows.length ? rows : readEmptyCopy(root), 8);
};

const readFailedEndpoints = (pane: HTMLElement): string[] => {
  const root = headingRoot(
    pane,
    /失败端点|Failed endpoints/i,
    (node) => Boolean(node.querySelector('button')),
  );
  if (!root) return [];
  return Array.from(root.querySelectorAll('button'))
    .filter((button) => button instanceof HTMLElement && !isHidden(button))
    .map((button) => sanitizeNode(button))
    .filter(Boolean)
    .slice(0, ERROR_ENDPOINT_LIMIT);
};

const errorsSections = (pane: HTMLElement): AiContextSection[] => {
  const kpi = readKpiCards(pane);
  const typeRoot = headingRoot(
    pane,
    /错误原因|Error causes|Error reasons/i,
    (node) => Boolean(node.querySelector('table, .ant-empty-description')),
  );
  const sampleRoot = headingRoot(
    pane,
    /最近\s*\d+\s*条|Latest\s+\d+/i,
    (node) => Boolean(node.querySelector('table, .ant-empty-description')),
  );
  const filtered = Array.from(pane.querySelectorAll('button')).some((button) =>
    /清除端点筛选|Clear endpoint filter/i.test(button.textContent || ''),
  );
  const typeRows = typeRoot ? readTableRows(typeRoot, ERROR_TYPE_LIMIT) : [];
  const sampleRows = sampleRoot ? readTableRows(sampleRoot, ERROR_SAMPLE_LIMIT) : [];
  const sampleLines = [
    ...(filtered ? ['已按端点过滤'] : []),
    ...(sampleRows.length ? sampleRows : (sampleRoot ? readEmptyCopy(sampleRoot) : [])),
  ];
  const fallback = !kpi.length && !typeRows.length && !sampleRows.length ? readEmptyCopy(pane) : [];
  return [
    ...section('apm-service-error-kpi', '错误概览', kpi, 9),
    ...section('apm-service-error-types', '错误原因', typeRows.length ? typeRows : (typeRoot ? readEmptyCopy(typeRoot) : []), 8),
    ...section('apm-service-error-endpoints', '失败端点', readFailedEndpoints(pane), 8),
    ...section('apm-service-error-samples', '最近失败', sampleLines, 4),
    ...section('apm-service-errors', '错误', fallback, 8),
  ];
};

const runtimeSections = (pane: HTMLElement): AiContextSection[] => {
  const empty = readEmptyCopy(pane);
  const lines = empty.length
    ? empty
    : Array.from(pane.querySelectorAll('.ant-typography'))
      .filter((node) => node instanceof HTMLElement && !isHidden(node))
      .map((node) => sanitizeLine(node.textContent || ''))
      .filter(Boolean);
  return section('apm-service-runtime', '运行时', lines, 8);
};

const deploymentsSections = (pane: HTMLElement): AiContextSection[] => {
  const rows = readTableRows(pane, DEPLOYMENT_ROW_LIMIT);
  return section('apm-service-deployments', '部署', rows.length ? rows : readEmptyCopy(pane), 4);
};

const sloSections = (pane: HTMLElement): AiContextSection[] => {
  const rows = readTableRows(pane, SLO_ROW_LIMIT);
  return section('apm-service-slo', 'SLO', rows.length ? rows : readEmptyCopy(pane), 8);
};

const tabBodySections = (tab: string): AiContextSection[] => {
  if (!KNOWN_TABS.has(tab)) return [];
  const pane = activePane();
  if (!pane) return [];
  if (tab === 'overview') return overviewSections(pane);
  if (tab === 'traces') return tracesSections(pane);
  if (tab === 'errors') return errorsSections(pane);
  if (tab === 'runtime') return runtimeSections(pane);
  if (tab === 'deployments') return deploymentsSections(pane);
  if (tab === 'slo') return sloSections(pane);
  return [];
};

const fingerprintSections = (sections: AiContextSection[]): string =>
  sections.map((item) => item.content).join('|');

interface ServiceDetailStamp {
  serviceId: string;
  serviceName: string;
  environment: string;
  timeRange: string;
  tab: string;
  kpiFingerprint: string;
  bodyFingerprint: string;
}

const readServiceDetailStamp = (): ServiceDetailStamp => {
  const readings = readServiceKpiReadings();
  const tab = activeServiceTab();
  return {
    serviceId: serviceIdFromPath(),
    serviceName: readServiceName(),
    environment: readEnvironment(),
    timeRange: readTimeRange(),
    tab,
    kpiFingerprint: readings.join('|'),
    bodyFingerprint: fingerprintSections(tabBodySections(tab)),
  };
};

const buildServiceCurrentTime = (stamp: ServiceDetailStamp): string =>
  [stamp.environment, stamp.timeRange, stamp.tab, stamp.kpiFingerprint, stamp.bodyFingerprint]
    .filter(Boolean)
    .join('::');

const shellSections = (stamp: ServiceDetailStamp): AiContextSection[] => {
  const readings = readServiceKpiReadings();
  return [
    {
      id: 'apm-service-identity',
      label: '当前服务',
      content: [
        '正在查看 APM 服务详情',
        stamp.serviceName ? `服务: ${stamp.serviceName}` : '',
        stamp.serviceId ? `serviceId: ${stamp.serviceId}` : '',
        stamp.environment ? `环境: ${stamp.environment}` : '',
        stamp.timeRange ? `时间窗: ${stamp.timeRange}` : '',
        stamp.tab ? `当前 Tab: ${stamp.tab}` : '',
      ].filter(Boolean).join('\n'),
      priority: 10,
    },
    ...(readings.length
      ? [{
        id: 'apm-service-kpi',
        label: 'KPI 快照',
        content: readings.join('\n'),
        priority: 9,
      }]
      : []),
  ];
};

const visibleChartSection = (captions: string[]): AiContextSection[] =>
  captions.length
    ? [{
      id: 'visible-charts',
      label: '可见图表',
      content: captions.map((caption, index) => `${index + 1}. ${caption}`).join('\n'),
      priority: 9,
    }]
    : [];

export function getMessage(): PageContextMessage {
  const stamp = readServiceDetailStamp();
  if (!stamp.serviceId) return { title: '' };
  const title = `${TITLE_PREFIX}${stamp.serviceId}`;
  const currentTime = buildServiceCurrentTime(stamp);
  return currentTime ? { title, currentTime } : { title };
}

export function getTextContext(): Partial<AiPageContext> {
  const stamp = readServiceDetailStamp();
  if (!stamp.serviceId) return { sections: [], images: [] };
  return {
    url: typeof window === 'undefined' ? '' : window.location.href,
    app: 'apm',
    title: document.title || stamp.serviceName || '服务详情',
    sections: [...shellSections(stamp), ...tabBodySections(stamp.tab)],
    images: [],
  };
}

export async function getContext(toolkit: PageContextToolkit): Promise<Partial<AiPageContext>> {
  const stamp = readServiceDetailStamp();
  const base = getTextContext();
  if (!stamp.serviceId) return base;

  const ordered = listActiveTabChartDoms();
  const captured = await Promise.all(
    ordered.map(async (dom): Promise<ChartSnapshot | null> => {
      const [shot] = await toolkit.captureEchartsFromDoms([dom], 1);
      if (!shot) return null;
      return {
        ...shot,
        caption: mergeServiceChartCaption(chartTitleNear(dom), shot.caption),
      };
    }),
  );
  const images = captured.filter((item): item is ChartSnapshot => Boolean(item));
  const captions = images.map((image) => image.caption).filter(Boolean) as string[];
  console.info('[ai-page-context] page data updated at', [stamp.environment, stamp.timeRange, stamp.tab].filter(Boolean).join('::'), {
    timeRange: stamp.timeRange || '(none)',
    tab: stamp.tab,
    environment: stamp.environment,
    charts: captions,
  });
  return {
    ...base,
    sections: [
      ...(base.sections || []),
      ...visibleChartSection(captions),
    ],
    images,
  };
}
