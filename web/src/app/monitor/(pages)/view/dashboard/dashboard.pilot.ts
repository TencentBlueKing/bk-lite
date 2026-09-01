import type { ChartSnapshot } from '@/components/chart-snapshot';
import type {
  AiPageContext,
  PageContextMessage,
  PageContextToolkit,
} from '@/components/ai-page-context/types';
import { PAGE_CONTEXT_MAX_IMAGES } from '@/components/ai-page-context/types';

const searchValue = (params: URLSearchParams, keys: string[]) => {
  for (const key of keys) {
    const value = params.get(key);
    if (value) return value;
  }
  return '';
};

const cleanLabel = (value: string) => value.replace(/\s+/g, ' ').trim();

const DECORATIVE_CHART_MAX_HEIGHT = 72;

const isGenericChartTitle = (name: string) =>
  /^(value|series)\d*$/i.test(name.trim()) || name.trim() === '图表';

const chartTitleFromCaption = (caption: string) => (caption.split('；')[0] || '').trim();

/** KPI 火花图等装饰性 echarts，不应占仪表盘截图配额。 */
export const isDecorativeDashboardChart = (dom: HTMLElement): boolean => {
  if (dom.closest('[class*="miniTrend"]')) return true;
  const height = dom.getBoundingClientRect().height;
  return height > 0 && height < DECORATIVE_CHART_MAX_HEIGHT;
};

const titleFromNode = (node: Element): string => {
  const guided = node.querySelector('[class*="titleWithGuide"] > span');
  if (guided) return cleanLabel(guided.textContent || '');
  return cleanLabel(node.textContent || '');
};

export interface DashboardChartLabel {
  title: string;
  legends: string[];
  readings: string[];
}

/** 监控卡片标题在 echarts 画布外，只在本页 pilot 里回填，不影响通用采集器。 */
export const labelFromDashboardCard = (dom: HTMLElement): DashboardChartLabel => {
  let node: HTMLElement | null = dom.parentElement;
  for (let depth = 0; depth < 8 && node; depth += 1, node = node.parentElement) {
    const charts = node.querySelectorAll('[_echarts_instance_]');
    const ownsOnlyThisChart =
      charts.length === 1 && (charts[0] === dom || charts[0].contains(dom) || dom.contains(charts[0]));
    if (!ownsOnlyThisChart) continue;
    const heading = Array.from(node.querySelectorAll('h1, h2, h3, h4')).find(
      (item) => !item.closest('[_echarts_instance_]'),
    );
    const labeled = heading
      || Array.from(node.querySelectorAll('[class*="panelTitle"], [class*="statLabel"]')).find(
        (item) => !item.closest('[_echarts_instance_]'),
      );
    if (!labeled) continue;
    const title = titleFromNode(labeled);
    if (!title) continue;
    const readings = Array.from(node.querySelectorAll('[class*="metricRow"]'))
      .map((row) => {
        const name = cleanLabel(row.querySelector('[class*="metricName"]')?.textContent || '');
        const percent = cleanLabel(row.querySelector('[class*="metricPercent"]')?.textContent || '');
        const count = cleanLabel(row.querySelector('[class*="metricCount"]')?.textContent || '');
        return [name, percent, count].filter(Boolean).join(' ');
      })
      .filter(Boolean);
    const legends = readings.length
      ? readings
      : Array.from(node.querySelectorAll('[class*="LegendItem"], [class*="legendItem"], [class*="metricName"]'))
        .map((item) => cleanLabel(item.textContent || ''))
        .filter((label) => label && label !== title);
    return { title, legends, readings };
  }
  return { title: '', legends: [], readings: [] };
};

export const buildDashboardCaption = (
  image: ChartSnapshot,
  nearby: DashboardChartLabel,
): string => {
  if (!nearby.title) return image.caption || '';
  if (nearby.readings.length) {
    return [nearby.title, `序列: ${nearby.readings.join(', ')}`].join('；');
  }
  const generic = !image.caption || isGenericChartTitle(chartTitleFromCaption(image.caption));
  const legends = nearby.legends.length ? `序列: ${nearby.legends.join(', ')}` : '';
  const rest = (image.caption || '')
    .split('；')
    .slice(1)
    .filter((part) => !/^序列:/.test(part.trim()) || !nearby.legends.length);
  return [nearby.title, legends || (generic ? '' : ''), ...rest].filter(Boolean).join('；');
};

const overlayChartTitle = (dataUrl: string, title: string): Promise<string> =>
  new Promise((resolve) => {
    if (!title || !dataUrl) {
      resolve(dataUrl);
      return;
    }
    const image = new Image();
    image.onload = () => {
      const bar = 28;
      const canvas = document.createElement('canvas');
      canvas.width = image.width;
      canvas.height = image.height + bar;
      const ctx = canvas.getContext('2d');
      if (!ctx) {
        resolve(dataUrl);
        return;
      }
      ctx.fillStyle = '#fff';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#1d2129';
      ctx.font = '14px sans-serif';
      ctx.fillText(title, 8, 19);
      ctx.drawImage(image, 0, bar);
      resolve(canvas.toDataURL('image/jpeg', 0.72));
    };
    image.onerror = () => resolve(dataUrl);
    image.src = dataUrl;
  });

const applyDashboardLabel = async (
  image: ChartSnapshot,
  nearby: DashboardChartLabel,
): Promise<ChartSnapshot> => {
  if (!nearby.title) return image;
  return {
    ...image,
    caption: buildDashboardCaption(image, nearby),
    dataUrl: await overlayChartTitle(image.dataUrl, nearby.title),
  };
};

const dashboardIdentity = () => {
  const params = new URLSearchParams(window.location.search);
  const segments = window.location.pathname.split('/').filter(Boolean);
  const objectKey = segments[segments.length - 1] || '';
  const objectName = searchValue(params, ['name', 'monitorObjDisplayName']) || objectKey;
  const instanceName = searchValue(params, ['instance_name', 'instance_id']);
  const view = params.get('view') || 'dashboard';
  return { objectKey, objectName, instanceName, view, monitorObjId: params.get('monitorObjId') || '' };
};

export interface DashboardPageDataStamp {
  timeRangeLabel: string;
  kpiFingerprint: string;
  kpiReadings: string[];
  collectionStatus: string;
  uptimeState: string;
}

const cardValue = (card: Element): string =>
  cleanLabel(
    card.querySelector('[class*="statValue"]')?.textContent
    || card.querySelector('[class*="collectionStatusValue"]')?.textContent
    || '',
  );

/** 卡片「指标名: 数值」，避免模型只看到 82.9% 却不知道是磁盘使用率。 */
export const readDashboardKpiReadings = (): string[] =>
  Array.from(document.querySelectorAll('[class*="statCard"]'))
    .map((card) => {
      const labelNode = card.querySelector('[class*="statLabel"]');
      const label = labelNode ? titleFromNode(labelNode) : '';
      const value = cardValue(card);
      return label && value ? `${label}: ${value}` : '';
    })
    .filter(Boolean)
    .slice(0, 8);

/** 从仪表盘 DOM 读取时间筛选 + KPI 指纹，用于 currentTime 与 console 诊断。 */
export const readDashboardPageDataStamp = (): DashboardPageDataStamp => {
  const timeRangeLabel = cleanLabel(
    document.querySelector('[class*="toolbarTimeSelector"] .ant-select-selection-item')?.textContent || '',
  );
  const kpiFingerprint = Array.from(document.querySelectorAll('[class*="statCard"] [class*="statValue"]'))
    .map((node) => cleanLabel(node.textContent || ''))
    .filter(Boolean)
    .slice(0, 8)
    .join('|');
  const collectionStatus = cleanLabel(
    document.querySelector('[class*="collectionStatusValue"]')?.textContent || '',
  );
  const uptimeState = cleanLabel(
    document.querySelector('[class*="uptimeStatusMain"]')?.textContent || '',
  );
  return {
    timeRangeLabel,
    kpiFingerprint,
    kpiReadings: readDashboardKpiReadings(),
    collectionStatus,
    uptimeState,
  };
};

export const buildDashboardCurrentTime = (stamp: DashboardPageDataStamp): string =>
  [stamp.timeRangeLabel, stamp.kpiFingerprint, stamp.collectionStatus, stamp.uptimeState]
    .filter(Boolean)
    .join('::');

export function getMessage(): PageContextMessage {
  const { objectKey, instanceName, monitorObjId } = dashboardIdentity();
  const title = `monitor-dashboard:${objectKey}:${instanceName || monitorObjId || 'default'}`;
  const stamp = readDashboardPageDataStamp();
  const currentTime = buildDashboardCurrentTime(stamp);
  return currentTime ? { title, currentTime } : { title };
}

const dashboardTextSections = (
  stamp: DashboardPageDataStamp,
  identity: ReturnType<typeof dashboardIdentity>,
  dataUpdatedAt: string,
) => {
  const lines = [
    `正在查看监控专业仪表盘`,
    identity.objectName ? `对象: ${identity.objectName}` : '',
    identity.objectKey ? `objectKey: ${identity.objectKey}` : '',
    identity.monitorObjId ? `monitorObjId: ${identity.monitorObjId}` : '',
    identity.instanceName ? `实例: ${identity.instanceName}` : '',
    `视图: ${identity.view}`,
    stamp.timeRangeLabel ? `时间筛选: ${stamp.timeRangeLabel}` : '',
    dataUpdatedAt ? `页面数据指纹: ${dataUpdatedAt}` : '',
  ].filter(Boolean);
  return [
    {
      id: 'dashboard-identity',
      label: '当前仪表盘',
      content: lines.join('\n'),
      priority: 10,
    },
    ...(stamp.timeRangeLabel || stamp.kpiReadings.length
      ? [{
        id: 'dashboard-time-range',
        label: '时间筛选',
        content: [
          stamp.timeRangeLabel ? `当前筛选: ${stamp.timeRangeLabel}` : '',
          stamp.kpiReadings.length
            ? `KPI 快照:\n${stamp.kpiReadings.join('\n')}`
            : stamp.kpiFingerprint
              ? `KPI 快照: ${stamp.kpiFingerprint.replace(/\|/g, ' · ')}`
              : '',
          stamp.uptimeState ? `运行状态: ${stamp.uptimeState}` : '',
          stamp.collectionStatus ? `采集状态: ${stamp.collectionStatus}` : '',
        ].filter(Boolean).join('\n'),
        priority: 9,
      }]
      : []),
  ];
};

/** 截图超时仍能带上 KPI；问「磁盘使用率高吗」至少看得到 82.9%。 */
export function getTextContext(): Partial<AiPageContext> {
  const identity = dashboardIdentity();
  const stamp = readDashboardPageDataStamp();
  const dataUpdatedAt = buildDashboardCurrentTime(stamp);
  return {
    url: window.location.href,
    app: 'monitor',
    title: document.title || `${identity.objectName} 仪表盘`,
    sections: dashboardTextSections(stamp, identity, dataUpdatedAt),
    images: [],
  };
}

export async function getContext(
  toolkit: PageContextToolkit,
): Promise<Partial<AiPageContext>> {
  const stamp = readDashboardPageDataStamp();
  const dataUpdatedAt = buildDashboardCurrentTime(stamp);
  const base = getTextContext();

  const nodes = Array.from(document.querySelectorAll<HTMLElement>('[_echarts_instance_]')).filter(
    (dom) => !isDecorativeDashboardChart(dom),
  );
  const labeled = nodes.map((dom) => ({ dom, ...labelFromDashboardCard(dom) }));
  // 有标题的图优先，仍按 DOM 顺序截到上限；前端不做问法筛选。
  const ordered = [
    ...labeled.filter((item) => item.title),
    ...labeled.filter((item) => !item.title),
  ].slice(0, PAGE_CONTEXT_MAX_IMAGES);
  const captured = await Promise.all(
    ordered.map(async (item) => {
      const [shot] = await toolkit.captureEchartsFromDoms([item.dom], 1);
      if (!shot) return null;
      return applyDashboardLabel(shot, item);
    }),
  );
  const images = captured.filter((item): item is ChartSnapshot => Boolean(item));

  const chartLines = images.length
    ? images.map((image, index) => `${index + 1}. ${image.caption}`)
    : [];

  console.info('[ai-page-context] page data updated at', dataUpdatedAt, {
    timeRange: stamp.timeRangeLabel || '(unknown)',
    kpi: stamp.kpiFingerprint,
    kpiReadings: stamp.kpiReadings,
    collectionStatus: stamp.collectionStatus,
    uptimeState: stamp.uptimeState,
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
          priority: 9,
        }]
        : []),
    ],
    images,
  };
}
