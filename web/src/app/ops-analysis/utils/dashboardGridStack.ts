import type {
  DashboardGroupLayoutItem,
  DashboardLayoutItem,
  DashboardWidgetLayoutItem,
} from '../types/dashBoard';
import {
  isDashboardGroupItem,
  normalizeDashboardLayoutGroupIds,
  sortDashboardLayoutItems,
} from './dashboardGroups';

export interface DashboardGridStackBaseNode {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface DashboardGridStackWidgetNode extends DashboardGridStackBaseNode {
  kind: 'widget';
  item: DashboardWidgetLayoutItem;
  groupId: string | null;
}

export interface DashboardGridStackGroupNode extends DashboardGridStackBaseNode {
  kind: 'group';
  item: DashboardGroupLayoutItem;
  children: DashboardGridStackWidgetNode[];
}

export type DashboardGridStackNode =
  | DashboardGridStackWidgetNode
  | DashboardGridStackGroupNode;

export interface DashboardGridStackLayout {
  topLevelNodes: DashboardGridStackNode[];
  ungroupedNodes: DashboardGridStackWidgetNode[];
  groupNodes: DashboardGridStackGroupNode[];
}

export interface DashboardGridStackNodeChange extends DashboardGridStackBaseNode {
  children?: DashboardGridStackNodeChange[];
}

export interface DashboardGridStackStoredWidget {
  id?: string;
  x?: number;
  y?: number;
  w?: number;
  h?: number;
  itemType?: 'group' | 'widget';
  name?: string;
  description?: string;
  valueConfig?: DashboardWidgetLayoutItem['valueConfig'];
  headerH?: number;
  sizeToContent?: boolean | number;
  subGridOpts?: {
    children?: DashboardGridStackStoredWidget[];
  };
}

const toStoredInt = (value: unknown, fallback: number, min = 0) => {
  const parsed = typeof value === 'number' ? value : Number(value);

  if (!Number.isFinite(parsed)) {
    return fallback;
  }

  return Math.max(Math.round(parsed), min);
};

const isStoredWidget = (
  value: unknown,
): value is DashboardGridStackStoredWidget =>
  typeof value === 'object' && value !== null;

const isNativeDashboardGridStackLayout = (
  value: unknown,
): value is DashboardGridStackStoredWidget[] =>
  Array.isArray(value) &&
  value.some(
    (item) => isStoredWidget(item) && (typeof item.id === 'string' || !!item.subGridOpts),
  );

const toWidgetNode = (
  item: DashboardWidgetLayoutItem,
  groupId: string | null,
): DashboardGridStackWidgetNode => ({
  kind: 'widget',
  id: item.i,
  x: item.x,
  y: item.y,
  w: item.w,
  h: item.h,
  item,
  groupId,
});

const toGroupNode = (
  item: DashboardGroupLayoutItem,
  children: DashboardWidgetLayoutItem[],
): DashboardGridStackGroupNode => {
  const rawRelativeChildren = children.map((child) =>
    toWidgetNode(
      {
        ...child,
        y: Math.max(child.y - (item.y + item.h), 0),
      },
      item.i,
    ),
  );
  const minRelativeY = rawRelativeChildren.reduce(
    (currentMin, child) => Math.min(currentMin, child.y),
    Number.POSITIVE_INFINITY,
  );
  const relativeChildren =
    Number.isFinite(minRelativeY) && minRelativeY > 0
      ? rawRelativeChildren.map((child) => ({
        ...child,
        y: child.y - minRelativeY,
      }))
      : rawRelativeChildren;
  const childrenHeight = relativeChildren.reduce(
    (maxBottom, child) => Math.max(maxBottom, child.y + child.h),
    0,
  );

  return {
    kind: 'group',
    id: item.i,
    x: item.x,
    y: item.y,
    w: item.w,
    h: item.h + childrenHeight,
    item,
    children: relativeChildren,
  };
};

export const buildDashboardGridStackLayout = (
  items: DashboardLayoutItem[],
): DashboardGridStackLayout => {
  const normalized = normalizeDashboardLayoutGroupIds(items);
  const groupedWidgets = new Map<string, DashboardWidgetLayoutItem[]>();
  const ungroupedNodes: DashboardGridStackWidgetNode[] = [];

  normalized.forEach((item) => {
    if (!isDashboardGroupItem(item) && item.groupId) {
      const widgets = groupedWidgets.get(item.groupId) ?? [];
      widgets.push(item);
      groupedWidgets.set(item.groupId, widgets);
      return;
    }

    if (!isDashboardGroupItem(item)) {
      ungroupedNodes.push(toWidgetNode(item, null));
    }
  });

  const groupNodes = normalized
    .filter(isDashboardGroupItem)
    .map((item) =>
      toGroupNode(
        item,
        (sortDashboardLayoutItems(
          groupedWidgets.get(item.i) ?? [],
        ) as DashboardWidgetLayoutItem[]),
      ),
    );
  const groupNodeById = new Map(groupNodes.map((node) => [node.id, node]));

  const topLevelNodes: DashboardGridStackNode[] = [];

  normalized.forEach((item) => {
    if (isDashboardGroupItem(item)) {
      const groupNode = groupNodeById.get(item.i);

      if (groupNode) {
        topLevelNodes.push(groupNode);
      }
      return;
    }

    if (!item.groupId) {
      topLevelNodes.push(toWidgetNode(item, null));
    }
  });

  return {
    topLevelNodes,
    ungroupedNodes,
    groupNodes,
  };
};

export const buildDashboardGridStackStructureKey = (
  items: DashboardLayoutItem[],
): string => {
  const layout = buildDashboardGridStackLayout(items);

  const groupIds = layout.groupNodes
    .map((node) => node.id)
    .sort()
    .join(',');
  const widgetIds = [
    ...layout.ungroupedNodes,
    ...layout.groupNodes.flatMap((node) => node.children),
  ]
    .map((node) => node.id)
    .sort()
    .join(',');

  return `groups:${groupIds}||widgets:${widgetIds}`;
};

export const flattenDashboardGridStackLayout = (
  layout: DashboardGridStackLayout,
): DashboardLayoutItem[] => {
  const flattened = layout.topLevelNodes.flatMap((node) => {
    if (node.kind === 'group') {
      const groupItem = {
        ...node.item,
        x: node.x,
        y: node.y,
        w: node.w,
        h: node.item.h,
      };

      return [
        groupItem,
        ...sortDashboardLayoutItems(
          node.children.map((child) => ({
            ...child.item,
            x: child.x,
            y: node.y + groupItem.h + child.y,
            w: child.w,
            h: child.h,
            groupId: node.id,
          })),
        ),
      ];
    }

    return [
      {
        ...node.item,
        x: node.x,
        y: node.y,
        w: node.w,
        h: node.h,
        groupId: node.groupId,
      },
    ];
  });

  return normalizeDashboardLayoutGroupIds(flattened);
};

export const serializeDashboardGridStackLayout = (
  items: DashboardLayoutItem[],
): DashboardGridStackStoredWidget[] =>
  buildDashboardGridStackLayout(items).topLevelNodes.map((node) => {
    if (node.kind === 'group') {
      return {
        id: node.id,
        x: node.x,
        y: node.y,
        w: node.w,
        h: node.h,
        itemType: 'group',
        name: node.item.name,
        description: node.item.description,
        headerH: node.item.h,
        sizeToContent: true,
        subGridOpts: {
          children: node.children.map((child) => ({
            id: child.id,
            x: child.x,
            y: child.y,
            w: child.w,
            h: child.h,
            itemType: 'widget',
            name: child.item.name,
            description: child.item.description,
            valueConfig: child.item.valueConfig,
          })),
        },
      };
    }

    return {
      id: node.id,
      x: node.x,
      y: node.y,
      w: node.w,
      h: node.h,
      itemType: 'widget',
      name: node.item.name,
      description: node.item.description,
      valueConfig: node.item.valueConfig,
    };
  });

export const deserializeDashboardGridStackLayout = (
  viewSets: unknown,
): DashboardLayoutItem[] => {
  if (!Array.isArray(viewSets)) {
    return [];
  }

  if (!isNativeDashboardGridStackLayout(viewSets)) {
    return normalizeDashboardLayoutGroupIds(viewSets as DashboardLayoutItem[]);
  }

  const flattened = viewSets.flatMap((item) => {
    if (!isStoredWidget(item) || typeof item.id !== 'string' || !item.id.trim()) {
      return [];
    }

    const itemId = item.id.trim();
    const baseX = toStoredInt(item.x, 0);
    const baseY = toStoredInt(item.y, 0);
    const baseW = toStoredInt(item.w, 4, 1);
    const baseH = toStoredInt(item.h, 3, 1);

    if (item.itemType === 'group' || Array.isArray(item.subGridOpts?.children)) {
      const headerH = toStoredInt(item.headerH, 1, 1);
      const groupItem: DashboardGroupLayoutItem = {
        i: itemId,
        itemType: 'group',
        x: baseX,
        y: baseY,
        w: baseW,
        h: headerH,
        name: item.name ?? '',
        description: item.description,
      };

      const children = Array.isArray(item.subGridOpts?.children)
        ? item.subGridOpts.children
        : [];

      return [
        groupItem,
        ...children.flatMap((child) => {
          if (
            !isStoredWidget(child) ||
            typeof child.id !== 'string' ||
            !child.id.trim()
          ) {
            return [];
          }

          return [
            {
              i: child.id.trim(),
              x: toStoredInt(child.x, 0),
              y: baseY + headerH + toStoredInt(child.y, 0),
              w: toStoredInt(child.w, 4, 1),
              h: toStoredInt(child.h, 3, 1),
              name: child.name ?? '',
              description: child.description,
              groupId: itemId,
              valueConfig: child.valueConfig,
            } satisfies DashboardWidgetLayoutItem,
          ];
        }),
      ];
    }

    return [
      {
        i: itemId,
        x: baseX,
        y: baseY,
        w: baseW,
        h: baseH,
        name: item.name ?? '',
        description: item.description,
        groupId: null,
        valueConfig: item.valueConfig,
      } satisfies DashboardWidgetLayoutItem,
    ];
  });

  return normalizeDashboardLayoutGroupIds(flattened);
};

export const applyDashboardGridStackLayoutChanges = (
  items: DashboardLayoutItem[],
  changes: DashboardGridStackNodeChange[],
): DashboardLayoutItem[] => {
  const normalized = normalizeDashboardLayoutGroupIds(items);
  const groupItemById = new Map(
    normalized
      .filter(isDashboardGroupItem)
      .map((item) => [item.i, item]),
  );
  const parentChangeByChildId = new Map<string, DashboardGridStackNodeChange>();
  const groupChangeById = new Map<string, DashboardGridStackNodeChange>();
  const changeMap = new Map<string, DashboardGridStackNodeChange>();

  changes.forEach((change) => {
    changeMap.set(change.id, change);
    groupChangeById.set(change.id, change);
    change.children?.forEach((child) => {
      changeMap.set(child.id, child);
      parentChangeByChildId.set(child.id, change);
    });
  });

  const updated = normalized.map((item) => {
    const change = changeMap.get(item.i);

    if (!change && !(!isDashboardGroupItem(item) && item.groupId)) {
      return item;
    }

    if (!isDashboardGroupItem(item) && item.groupId) {
      const parentChange = parentChangeByChildId.get(item.i);
      const parentGroup = groupItemById.get(item.groupId);
      const parentHeaderHeight = parentGroup?.h ?? 1;

      if (!change && parentChange && parentGroup) {
        return {
          ...item,
          x: item.x + (parentChange.x - parentGroup.x),
          y: item.y + (parentChange.y - parentGroup.y),
        };
      }

      return {
        ...item,
        x: change?.x ?? item.x,
        y:
          change && parentChange
            ? parentChange.y + parentHeaderHeight + change.y
            : item.y,
        w: change?.w ?? item.w,
        h: change?.h ?? item.h,
      };
    }

    return {
      ...item,
      x: change.x,
      y: change.y,
      w: change.w,
      h: isDashboardGroupItem(item) ? item.h : change.h,
    };
  });

  return normalizeDashboardLayoutGroupIds(updated);
};
