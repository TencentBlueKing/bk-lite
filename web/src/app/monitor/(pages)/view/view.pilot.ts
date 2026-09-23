import type { AiPageContext, PageContextMessage } from '@/components/ai-page-context/types';
import { cleanLabel, treeSection } from '@/components/ai-page-context/domSnapshot';
import { buildTableListContext } from '@/app/monitor/page-context/tableListContext';

export const isMonitorViewIndexPath = (pathname: string): boolean => {
  const path = (pathname || '').replace(/\/+$/, '');
  return path === '/monitor/view' || /(^|\/)monitor\/view$/.test(path);
};

export const hiveColorHint = (fill: string): string => {
  const hex = (fill || '').trim();
  const raw = hex.replace('#', '');
  if (raw.length < 6) return hex;
  const r = Number.parseInt(raw.slice(0, 2), 16);
  const g = Number.parseInt(raw.slice(2, 4), 16);
  const b = Number.parseInt(raw.slice(4, 6), 16);
  if (![r, g, b].every(Number.isFinite)) return hex;
  if (r > 180 && g < 130 && b < 130) return `${hex} 红`;
  if (g > 150 && r < 140) return `${hex} 绿`;
  if (r > 180 && g > 120 && b < 90) return `${hex} 黄`;
  return hex;
};

export const isHiveView = (): boolean => {
  if (document.querySelector('[data-ai-hive-name]')) return true;
  const selected = document.querySelector('.ant-segmented-item-selected input') as HTMLInputElement | null;
  return (selected?.value || '') === 'view';
};

const hiveCells = () =>
  Array.from(document.querySelectorAll<HTMLElement>('[data-ai-hive-name]')).map((node) => {
    const name = cleanLabel(node.getAttribute('data-ai-hive-name') || '');
    const value = cleanLabel(node.getAttribute('data-ai-hive-value') || '');
    const fill = hiveColorHint(node.getAttribute('data-ai-hive-fill') || '');
    return [name, value, fill].filter(Boolean).join(' ');
  }).filter(Boolean);

export function getMessage(): PageContextMessage {
  const objectLabel = cleanLabel(document.querySelector('.ant-tree-node-selected')?.textContent || '');
  if (isHiveView()) {
    const metric = cleanLabel(document.querySelector('[data-ai-hive-metric]')?.getAttribute('data-ai-hive-metric') || '');
    const loaded = hiveCells().join('|');
    return {
      title: `monitor-view-hive:${objectLabel || 'all'}`,
      currentTime: [metric, loaded].filter(Boolean).join('::'),
    };
  }
  const table = buildTableListContext({ heading: '正在查看监控视图列表' });
  const range = (table.sections || []).find((section) => section.id === 'list-range')?.content || '';
  const rows = (table.sections || []).find((section) => section.id === 'list-table')?.content || '';
  return {
    title: `monitor-view-list:${objectLabel || 'all'}`,
    currentTime: [range, rows.slice(0, 120)].filter(Boolean).join('::'),
  };
}

export function getTextContext(): Partial<AiPageContext> {
  const objectLabel = cleanLabel(document.querySelector('.ant-tree-node-selected')?.textContent || '');
  if (isHiveView()) {
    const root = document.querySelector('[data-ai-hive-total]');
    const total = Number(root?.getAttribute('data-ai-hive-total') || 0);
    const loaded = Number(root?.getAttribute('data-ai-hive-loaded') || hiveCells().length);
    const remaining = Math.max(0, total - loaded);
    const metric = cleanLabel(root?.getAttribute('data-ai-hive-metric') || '');
    const node = cleanLabel(root?.getAttribute('data-ai-hive-node') || '');
    const cells = hiveCells();
    return {
      url: window.location.href,
      app: 'monitor',
      title: document.title || '监控视图',
      sections: [
        {
          id: 'view-hive-identity',
          label: '当前蜂窝',
          content: [
            '正在查看监控视图蜂窝',
            objectLabel ? `对象: ${objectLabel}` : '',
            metric ? `展示指标: ${metric}` : '',
            node ? `节点筛选: ${node}` : '',
            `已加载 ${loaded} 个格子`,
            remaining ? `还有 ${remaining} 个未加载` : '',
          ].filter(Boolean).join('\n'),
          priority: 10,
        },
        ...treeSection(),
        ...(cells.length
          ? [{
            id: 'view-hive-cells',
            label: '已加载格子',
            content: cells.join('\n'),
            priority: 6,
          }]
          : []),
      ],
      images: [],
    };
  }
  return buildTableListContext({
    heading: '正在查看监控视图列表',
    extraIdentity: objectLabel ? [`对象: ${objectLabel}`] : [],
    identityId: 'view-list-identity',
    identityLabel: '当前监控视图',
  });
}

export async function getContext(): Promise<Partial<AiPageContext>> {
  return getTextContext();
}
