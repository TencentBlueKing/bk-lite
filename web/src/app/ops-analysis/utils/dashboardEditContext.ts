import { PAGE_CONTEXT_TEXT_BUDGET } from '@/components/ai-page-context/types';
import type { AiContextSection } from '@/components/ai-page-context/types';
import type {
  DashboardLayoutItem,
  FilterValue,
  OtherConfig,
  UnifiedFilterDefinition,
} from '@/app/ops-analysis/types/dashBoard';

const TOO_LARGE = '仪表盘编辑配置过长，本轮无法安全搭盘。请先减少组件后再描述调整。';
const DISPLAY_RESERVE = 2000;

const layoutForContext = (layout: DashboardLayoutItem[], omitDescriptions: boolean): DashboardLayoutItem[] => {
  if (!omitDescriptions) return layout;
  return layout.map((item) => {
    if (!item || typeof item !== 'object' || !('description' in item)) return item;
    const { description: _description, ...rest } = item;
    return rest as DashboardLayoutItem;
  });
};

const serializeEditSnapshot = (input: DashboardEditSnapshotInput, omitDescriptions: boolean) => JSON.stringify({
  snapshotVersion: '1.0',
  dashboardId: input.dashboardId ?? '',
  mode: input.mode || 'edit',
  name: input.name || '',
  layout: layoutForContext(input.layout, omitDescriptions),
  filters: input.filters,
  filterValues: input.filterValues || {},
  otherConfig: input.otherConfig || {},
  refreshInterval: input.refreshInterval ?? 0,
});

export interface DashboardEditSnapshotInput {
  dashboardId?: string | number;
  name?: string;
  layout: DashboardLayoutItem[];
  filters: UnifiedFilterDefinition[];
  filterValues?: Record<string, FilterValue>;
  otherConfig?: OtherConfig;
  refreshInterval?: number;
  mode?: 'view' | 'edit';
}

/**
 * 页面状态使用一个版本化 JSON 快照进入 page_context。
 * 后端只解析这个结构化契约，不再从人类可读文本反推参数、绑定和筛选器。
 */
export const buildDashboardEditStateSection = (input: DashboardEditSnapshotInput): AiContextSection => {
  let content = serializeEditSnapshot(input, false);
  if (content.length > PAGE_CONTEXT_TEXT_BUDGET - DISPLAY_RESERVE) {
    content = serializeEditSnapshot(input, true);
  }
  return {
    id: 'dashboard-edit-state',
    label: '仪表盘编辑状态',
    priority: 100,
    content: content.length > PAGE_CONTEXT_TEXT_BUDGET ? TOO_LARGE : content,
  };
};

export const dashboardEditStateAllowsApply = (input: DashboardEditSnapshotInput): boolean =>
  buildDashboardEditStateSection(input).content !== TOO_LARGE;
