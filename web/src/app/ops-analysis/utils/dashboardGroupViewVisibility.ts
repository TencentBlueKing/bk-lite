import type { DashboardLayoutItem } from '../types/dashBoard';
import {
  buildDashboardSections,
  buildDashboardTopLevelBlocks,
  getVisibleDashboardLayoutItems,
  isDashboardGroupItem,
  isDashboardWidgetItem,
} from './dashboardGroups';
import type { DataSourceLookupStatus } from './widgetRequestVersion';

export type DashboardCanvasMode = 'edit' | 'view';

export interface DashboardGroupViewVisibilityInput {
  items: DashboardLayoutItem[];
  mode: DashboardCanvasMode;
  isWidgetUnauthorized: (widgetId: string) => boolean;
}

export interface DashboardTopLevelRenderBlock {
  key: string;
  type: 'ungrouped' | 'group';
}

/** 纯函数：决定查看/编辑态下本次 GridStack 应保留的顶层块（不测 GridStack 本身）。 */
export const selectDashboardTopLevelRenderBlocks = (
  input: DashboardGroupViewVisibilityInput,
): DashboardTopLevelRenderBlock[] => {
  const displayItems = deriveDashboardGridDisplayLayout(input);
  return buildDashboardTopLevelBlocks(displayItems).map((block) => ({
    key: block.key,
    type: block.type,
  }));
};

export const omitFullyUnauthorizedDashboardGroups = (
  items: DashboardLayoutItem[],
  isWidgetUnauthorized: (widgetId: string) => boolean,
): DashboardLayoutItem[] => {
  const sections = buildDashboardSections(items);
  const hiddenGroupIds = new Set<string>();

  sections.groups.forEach((section) => {
    const widgets = section.widgets;
    if (widgets.length === 0) {
      return;
    }
    if (widgets.every((widget) => isWidgetUnauthorized(widget.i))) {
      hiddenGroupIds.add(section.group.i);
    }
  });

  if (hiddenGroupIds.size === 0) {
    return items;
  }

  return items.filter((item) => {
    if (isDashboardGroupItem(item) && hiddenGroupIds.has(item.i)) {
      return false;
    }
    if (
      isDashboardWidgetItem(item)
      && item.groupId
      && hiddenGroupIds.has(item.groupId)
    ) {
      return false;
    }
    return true;
  });
};

export const deriveDashboardGridDisplayLayout = (
  input: DashboardGroupViewVisibilityInput,
): DashboardLayoutItem[] => {
  if (input.mode === 'edit') {
    return input.items;
  }

  const withoutUnauthorizedGroups = omitFullyUnauthorizedDashboardGroups(
    input.items,
    input.isWidgetUnauthorized,
  );

  // 仅对「整组省略」做纵向压缩；用户折叠仍由 GridStack 呈现层处理，不写 localStorage。
  return getVisibleDashboardLayoutItems(withoutUnauthorizedGroups, {});
};

export interface ModuleLicenseCanvasEmptyInput extends DashboardGroupViewVisibilityInput {
  /** 数据源 lookup 已决、场景检查与模块许可列表已就绪，不等于「正在加载」。 */
  resourcesReady: boolean;
  /** 首屏无权结论已冻结。未冻结时无权谓词还不可用，不能当成整盘无模块。 */
  frozen: boolean;
  /** lookup 失败时资源已决，但不能当成缺模块。缺省视为成功，兼容旧调用。 */
  dataSourceLookupStatus?: DataSourceLookupStatus;
}

/**
 * 查看态（含分享、订阅）在资源就绪后，存盘布局里每个组件都因模块不可见（§5.1）。
 * 含未分组组件。不读 omit 之后的展示布局，也不把未分组组件从布局摘掉。
 * 存盘本身没有组件时返回 false，留给「添加组件」空态。
 * 编辑态、未就绪、未冻结、lookup 失败一律 false，避免把加载或 lookup 失败标成缺模块。
 */
export const isModuleLicenseCanvasEmpty = (
  input: ModuleLicenseCanvasEmptyInput,
): boolean => {
  if (
    input.mode === 'edit'
    || !input.resourcesReady
    || !input.frozen
    || input.dataSourceLookupStatus === 'error'
  ) {
    return false;
  }
  const storedWidgets = input.items.filter(isDashboardWidgetItem);
  if (storedWidgets.length === 0) {
    return false;
  }
  return storedWidgets.every((widget) => input.isWidgetUnauthorized(widget.i));
};

/**
 * 订阅渲染要等的组件。整盘模块空态不挂载画布，因此不等未分组的无权组件回调。
 * 仍有可见组件时与展示布局一致：整组 omit 去掉的 id 不等，未分组无权组件留在列表里。
 * lookup 失败同样走 display layout：拓扑等不读 lookup 的场景组仍可 §5.2 omit，
 * 只等格子上仍会挂载的图表报 data-source-load-error，不按空列表发 report-ready。
 */
/**
 * lookup 成功会先于 setLayout 提交。那一帧组件 id 仍是 []，
 * 不能当成整盘空态发 report-ready。加载中、或就绪标记还不是本次画布时继续等。
 */
export const shouldHoldDashboardRenderSignal = ({
  loading,
  layoutReadyDashboardId,
  dashboardId,
}: {
  loading: boolean;
  layoutReadyDashboardId: number | string | null;
  dashboardId: number | string | null | undefined;
}): boolean =>
  loading
  || layoutReadyDashboardId == null
  || dashboardId == null
  || layoutReadyDashboardId !== dashboardId;

export const selectDashboardViewRenderWidgetIds = (
  input: ModuleLicenseCanvasEmptyInput,
): string[] => {
  const storedWidgetIds = input.items.filter(isDashboardWidgetItem).map((item) => item.i);
  if (input.mode === 'edit' || !input.resourcesReady || !input.frozen) {
    return storedWidgetIds;
  }
  if (isModuleLicenseCanvasEmpty(input)) {
    return [];
  }
  return deriveDashboardGridDisplayLayout({
    items: input.items,
    mode: 'view',
    isWidgetUnauthorized: input.isWidgetUnauthorized,
  })
    .filter(isDashboardWidgetItem)
    .map((item) => item.i);
};
