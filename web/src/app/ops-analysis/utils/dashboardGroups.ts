import type {
  DashboardGroupLayoutItem,
  DashboardLayoutItem,
  LayoutChangeItem,
  DashboardWidgetLayoutItem,
} from '../types/dashBoard';

export interface DashboardGroupSection {
  group: DashboardGroupLayoutItem;
  widgets: DashboardWidgetLayoutItem[];
}

export interface DraggingDashboardGroupState {
  groupId: string;
  proxyHeight: number;
  hiddenWidgetIds: string[];
}

export interface DashboardSections {
  ungrouped: DashboardWidgetLayoutItem[];
  groups: DashboardGroupSection[];
}

export interface DashboardTopLevelBlock {
  key: string;
  type: 'ungrouped' | 'group';
  items: DashboardLayoutItem[];
  top: number;
}

const DASHBOARD_EMPTY_GROUP_DROP_ROWS = 4;

export const isDashboardGroupItem = (
  item: DashboardLayoutItem,
): item is DashboardGroupLayoutItem => item.itemType === 'group';

export const isDashboardWidgetItem = (
  item: DashboardLayoutItem,
): item is DashboardWidgetLayoutItem => item.itemType !== 'group';

export const sortDashboardLayoutItems = (items: DashboardLayoutItem[]) =>
  [...items].sort((a, b) => a.y - b.y || a.x - b.x || a.i.localeCompare(b.i));

export const buildDashboardSections = (items: DashboardLayoutItem[]): DashboardSections => {
  const ordered = sortDashboardLayoutItems(items);
  const sections: DashboardSections = { ungrouped: [], groups: [] };
  const groupMap = new Map<string, DashboardGroupSection>();
  let currentGroup: DashboardGroupSection | null = null;

  ordered.forEach((item) => {
    if (isDashboardGroupItem(item)) {
      currentGroup = { group: item, widgets: [] };
      sections.groups.push(currentGroup);
      groupMap.set(item.i, currentGroup);
      return;
    }

    if (item.groupId === null) {
      sections.ungrouped.push(item);
      return;
    }

    if (item.groupId && groupMap.has(item.groupId)) {
      groupMap.get(item.groupId)?.widgets.push(item);
      return;
    }

    sections.ungrouped.push(item);
  });

  return sections;
};

export const normalizeDashboardLayoutGroupIds = (
  items: DashboardLayoutItem[],
): DashboardLayoutItem[] => {
  const sections = buildDashboardSections(items);
  const widgetGroupIds = new Map<string, string | null>();

  sections.ungrouped.forEach((widget) => {
    widgetGroupIds.set(widget.i, null);
  });

  sections.groups.forEach((section) => {
    section.widgets.forEach((widget) => {
      widgetGroupIds.set(widget.i, section.group.i);
    });
  });

  return items.map((item) =>
    isDashboardWidgetItem(item)
      ? {
        ...item,
        groupId: widgetGroupIds.get(item.i) ?? null,
      }
      : item,
  );
};

export const buildDashboardTopLevelBlocks = (
  items: DashboardLayoutItem[],
): DashboardTopLevelBlock[] => {
  const ordered = sortDashboardLayoutItems(
    normalizeDashboardLayoutGroupIds(items),
  );
  const blocks: DashboardTopLevelBlock[] = [];
  let currentGroupBlock: DashboardTopLevelBlock | null = null;
  let currentUngroupedRowBlock: DashboardTopLevelBlock | null = null;

  ordered.forEach((item) => {
    if (isDashboardGroupItem(item)) {
      currentGroupBlock = {
        key: item.i,
        type: 'group',
        items: [item],
        top: item.y,
      };
      currentUngroupedRowBlock = null;
      blocks.push(currentGroupBlock);
      return;
    }

    if (item.groupId && currentGroupBlock?.key === item.groupId) {
      currentGroupBlock.items.push(item);
      return;
    }

    if (!currentUngroupedRowBlock || currentUngroupedRowBlock.top !== item.y) {
      currentUngroupedRowBlock = {
        key: `ungrouped:${item.i}`,
        type: 'ungrouped',
        items: [item],
        top: item.y,
      };
      blocks.push(currentUngroupedRowBlock);
      return;
    }

    currentUngroupedRowBlock.items.push(item);
  });

  return blocks;
};

export const buildDashboardGroupStorageKey = (username: string, dashboardId: number | string) =>
  `ops-analysis:dashboard-groups:${username}:${dashboardId}`;

export const sanitizeCollapsedGroups = (
  value: unknown,
  validGroupIds: Set<string>,
): Record<string, true> => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {};
  }

  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>).filter(
      ([groupId, collapsed]) => validGroupIds.has(groupId) && collapsed === true,
    ),
  ) as Record<string, true>;
};

export const getVisibleDashboardLayoutItems = (
  items: DashboardLayoutItem[],
  collapsedGroups: Record<string, true>,
  draggingGroup?: DraggingDashboardGroupState | null,
): DashboardLayoutItem[] => {
  const blocks = buildDashboardTopLevelBlocks(items);
  const hiddenGroupChildren = draggingGroup
    ? new Set(
      buildDashboardSections(items).groups.map((section) => section.group.i),
    )
    : new Set(Object.keys(collapsedGroups));
  let nextY = 0;

  return blocks.flatMap((block) => {
    const blockTop = Math.min(...block.items.map((item) => item.y));

    if (block.type === 'ungrouped') {
      const compactUngroupedItems = block.items.map((item) => ({
        ...item,
        y: nextY + (item.y - blockTop),
      }));
      const blockBottom = Math.max(...block.items.map((item) => item.y + item.h));
      nextY += blockBottom - blockTop;
      return compactUngroupedItems;
    }

    const [group, ...widgets] = block.items;
    const groupItem = group as DashboardGroupLayoutItem;

    if (hiddenGroupChildren.has(groupItem.i)) {
      const compactGroup = {
        ...groupItem,
        y: nextY,
      };

      nextY += compactGroup.h;
      return [compactGroup];
    }

    const visibleItems = [groupItem, ...widgets].map((item) => ({
      ...item,
      y: nextY + (item.y - blockTop),
    }));
    const blockBottom = Math.max(...block.items.map((item) => item.y + item.h));
    nextY += blockBottom - blockTop;
    return visibleItems;
  });
};

export const getDashboardGroupBlockHeight = (
  items: DashboardLayoutItem[],
  groupId: string,
): number => {
  const targetSection = buildDashboardSections(items).groups.find(
    (section) => section.group.i === groupId,
  );

  if (!targetSection) {
    return 1;
  }

  return targetSection.group.h + targetSection.widgets.reduce(
    (totalHeight, widget) => totalHeight + widget.h,
    0,
  );
};

export const buildDraggingDashboardGroupState = (
  items: DashboardLayoutItem[],
  groupId: string,
): DraggingDashboardGroupState | null => {
  const sections = buildDashboardSections(items);
  const targetSection = sections.groups.find(
    (section) => section.group.i === groupId,
  );

  if (!targetSection) {
    return null;
  }

  return {
    groupId,
    proxyHeight: targetSection.group.h,
    hiddenWidgetIds: sections.groups.flatMap((section) =>
      section.widgets.map((widget) => widget.i),
    ),
  };
};

const applyLayoutChanges = (
  items: DashboardLayoutItem[],
  nextLayout: LayoutChangeItem[],
) => {
  const layoutById = new Map(nextLayout.map((item) => [item.i, item]));

  return items
    .filter((item) => layoutById.has(item.i))
    .map((item) => ({
      ...item,
      ...layoutById.get(item.i),
    }));
};

const getItemBounds = (item: Pick<DashboardLayoutItem, 'x' | 'y' | 'w' | 'h'>) => ({
  left: item.x,
  top: item.y,
  right: item.x + item.w,
  bottom: item.y + item.h,
});

export const getDashboardGroupSectionBounds = (
  section: DashboardGroupSection,
) => {
  const items = [section.group, ...section.widgets];
  const bounds = items.map(getItemBounds);
  const actualBottom = Math.max(...bounds.map((item) => item.bottom));
  const emptyGroupBottom =
    section.group.y + section.group.h + DASHBOARD_EMPTY_GROUP_DROP_ROWS;

  return {
    left: section.group.x,
    top: section.group.y,
    right: section.group.x + section.group.w,
    bottom: Math.max(actualBottom, emptyGroupBottom),
  };
};

const getOverlapArea = (
  first: ReturnType<typeof getItemBounds>,
  second: ReturnType<typeof getItemBounds>,
) => {
  const overlapWidth = Math.max(
    0,
    Math.min(first.right, second.right) - Math.max(first.left, second.left),
  );
  const overlapHeight = Math.max(
    0,
    Math.min(first.bottom, second.bottom) - Math.max(first.top, second.top),
  );

  return overlapWidth * overlapHeight;
};

const resolveDashboardWidgetDropGroupId = (
  items: DashboardLayoutItem[],
  widget: DashboardWidgetLayoutItem,
) => {
  const widgetBounds = getItemBounds(widget);
  const widgetCenterX = widget.x + widget.w / 2;
  const widgetCenterY = widget.y + widget.h / 2;
  let matchedGroupId: string | null = null;
  let bestScore = 0;

  buildDashboardSections(items).groups.forEach((section) => {
    const sectionBounds = getDashboardGroupSectionBounds(section);
    const overlapArea = getOverlapArea(widgetBounds, sectionBounds);
    const overlapRatio = overlapArea / Math.max(widget.w * widget.h, 1);
    const centerInside =
      widgetCenterX >= sectionBounds.left &&
      widgetCenterX <= sectionBounds.right &&
      widgetCenterY >= sectionBounds.top &&
      widgetCenterY <= sectionBounds.bottom;

    const score = centerInside ? Math.max(overlapRatio, 1) : overlapRatio;

    if (score >= 0.2 && score > bestScore) {
      matchedGroupId = section.group.i;
      bestScore = score;
    }
  });

  return matchedGroupId;
};

export const syncDashboardWidgetGroupIds = (
  items: DashboardLayoutItem[],
  nextVisibleLayout: LayoutChangeItem[],
  activeWidgetId?: string,
): DashboardLayoutItem[] => {
  const layoutById = new Map(nextVisibleLayout.map((item) => [item.i, item]));
  const visibleItemIds = new Set(nextVisibleLayout.map((item) => item.i));
  const positionedItems = items.map((item) => {
    const nextLayoutItem = layoutById.get(item.i);
    return nextLayoutItem ? { ...item, ...nextLayoutItem } : item;
  });
  const positionedVisibleItems = positionedItems.filter((item) =>
    visibleItemIds.has(item.i),
  );

  if (activeWidgetId) {
    const activeWidget = positionedItems.find(
      (item): item is DashboardWidgetLayoutItem =>
        item.i === activeWidgetId && isDashboardWidgetItem(item),
    );

    if (!activeWidget || !visibleItemIds.has(activeWidgetId)) {
      return positionedItems;
    }

    const otherVisibleItems = positionedVisibleItems.filter(
      (item) => item.i !== activeWidgetId,
    );
    const matchedGroupId = resolveDashboardWidgetDropGroupId(
      otherVisibleItems,
      activeWidget,
    );

    if (!matchedGroupId) {
      return positionedItems.map((item) =>
        item.i === activeWidgetId && isDashboardWidgetItem(item)
          ? { ...activeWidget, groupId: null }
          : item,
      );
    }

    if (matchedGroupId === activeWidget.groupId) {
      return positionedItems;
    }

    return insertDashboardWidgetIntoGroup(
      positionedItems.filter((item) => item.i !== activeWidgetId),
      { ...activeWidget, groupId: null },
      matchedGroupId,
    );
  }

  return positionedItems.map((item) => {
    if (!isDashboardWidgetItem(item) || !visibleItemIds.has(item.i)) {
      return item;
    }

    return {
      ...item,
      groupId: resolveDashboardWidgetDropGroupId(
        positionedVisibleItems.filter((visibleItem) => visibleItem.i !== item.i),
        item,
      ),
    };
  });
};

export const insertDashboardWidgetIntoGroup = (
  items: DashboardLayoutItem[],
  widget: DashboardWidgetLayoutItem,
  groupId: string,
): DashboardLayoutItem[] => {
  const normalizedItems = normalizeDashboardLayoutGroupIds(items);
  const sections = buildDashboardSections(normalizedItems);
  const targetSection = sections.groups.find((section) => section.group.i === groupId);

  if (!targetSection) {
    return [...normalizedItems, { ...widget, groupId: null }];
  }

  const canPlaceWidgetAt = (x: number, y: number) =>
    targetSection.widgets.every((item) => {
      const noHorizontalOverlap = x + widget.w <= item.x || item.x + item.w <= x;
      const noVerticalOverlap = y + widget.h <= item.y || item.y + item.h <= y;

      return noHorizontalOverlap || noVerticalOverlap;
    });

  const blockBottom = Math.max(
    ...[targetSection.group, ...targetSection.widgets].map(
      (item) => item.y + item.h,
    ),
  );

  let nextWidgetX = 0;
  let nextWidgetY = blockBottom;

  for (let candidateY = targetSection.group.y + targetSection.group.h; candidateY <= blockBottom; candidateY += 1) {
    let placed = false;

    for (let candidateX = 0; candidateX <= targetSection.group.w - widget.w; candidateX += 1) {
      if (!canPlaceWidgetAt(candidateX, candidateY)) {
        continue;
      }

      nextWidgetX = candidateX;
      nextWidgetY = candidateY;
      placed = true;
      break;
    }

    if (placed) {
      break;
    }
  }

  const insertedBottom = nextWidgetY + widget.h;
  const shiftDelta = Math.max(0, insertedBottom - blockBottom);
  const targetWidgetIds = new Set(targetSection.widgets.map((item) => item.i));

  const shiftedItems = normalizedItems.map((item) => {
    if (item.i === groupId || targetWidgetIds.has(item.i)) {
      return item;
    }

    if (shiftDelta > 0 && item.y >= blockBottom) {
      return {
        ...item,
        y: item.y + shiftDelta,
      };
    }

    return item;
  });

  return [
    ...shiftedItems,
    {
      ...widget,
      x: nextWidgetX,
      y: nextWidgetY,
      groupId,
    },
  ];
};

export const resolveDashboardGroupDropTargetIndex = (
  items: DashboardLayoutItem[],
  groupId: string,
  nextGroupY: number,
  nextVisibleLayout?: LayoutChangeItem[],
): number => {
  const blocks = nextVisibleLayout
    ? buildDashboardTopLevelBlocks(
      applyLayoutChanges(
        getVisibleDashboardLayoutItems(
          items,
          {},
          buildDraggingDashboardGroupState(items, groupId),
        ),
        nextVisibleLayout,
      ),
    )
    : buildDashboardTopLevelBlocks(normalizeDashboardLayoutGroupIds(items));
  const sourceIndex = blocks.findIndex((block) => block.key === groupId);

  if (sourceIndex < 0) {
    return -1;
  }

  const otherBlocks = blocks.filter((block) => block.key !== groupId);
  const targetIndex = otherBlocks.findIndex((block) => {
    const blockTop = Math.min(...block.items.map((item) => item.y));
    const blockBottom = Math.max(
      ...block.items.map((item) => item.y + item.h),
    );
    const midpoint = blockTop + (blockBottom - blockTop) / 2;

    return nextGroupY < midpoint;
  });

  return targetIndex >= 0 ? targetIndex : otherBlocks.length;
};

export const removeDashboardGroupHeader = (
  items: DashboardLayoutItem[],
  groupId: string,
): DashboardLayoutItem[] =>
  items
    .filter((item) => item.i !== groupId)
    .map((item) =>
      isDashboardWidgetItem(item) && item.groupId === groupId
        ? { ...item, groupId: null }
        : item,
    );

export const getDashboardGroupWidgetIds = (
  items: DashboardLayoutItem[],
  groupId: string,
): string[] => {
  const targetSection = buildDashboardSections(items).groups.find(
    (section) => section.group.i === groupId,
  );

  return targetSection ? targetSection.widgets.map((widget) => widget.i) : [];
};

export const bumpDashboardGroupWidgetReloadVersions = (
  items: DashboardLayoutItem[],
  groupId: string,
  versions: Record<string, number>,
): Record<string, number> => {
  const widgetIds = getDashboardGroupWidgetIds(items, groupId);

  if (widgetIds.length === 0) {
    return versions;
  }

  const nextVersions = { ...versions };
  widgetIds.forEach((widgetId) => {
    nextVersions[widgetId] = (nextVersions[widgetId] || 0) + 1;
  });

  return nextVersions;
};

export const moveDashboardGroupBlock = (
  items: DashboardLayoutItem[],
  groupId: string,
  nextGroupY: number,
): DashboardLayoutItem[] => {
  const sections = buildDashboardSections(items);
  const targetSection = sections.groups.find((section) => section.group.i === groupId);

  if (!targetSection) {
    return items;
  }

  const deltaY = nextGroupY - targetSection.group.y;
  if (deltaY === 0) {
    return items;
  }

  const widgetIds = new Set(targetSection.widgets.map((widget) => widget.i));

  return items.map((item) => {
    if (item.i === groupId || widgetIds.has(item.i)) {
      return {
        ...item,
        y: item.y + deltaY,
      };
    }

    return item;
  });
};

export const reorderDashboardGroupBlock = (
  items: DashboardLayoutItem[],
  groupId: string,
  targetBlockIndex: number,
): DashboardLayoutItem[] => {
  const normalizedItems = normalizeDashboardLayoutGroupIds(items);
  const blocks = buildDashboardTopLevelBlocks(normalizedItems);
  const sourceIndex = blocks.findIndex((block) => block.key === groupId);

  if (sourceIndex < 0 || sourceIndex === targetBlockIndex) {
    return items;
  }

  const boundedTargetIndex = Math.max(
    0,
    Math.min(targetBlockIndex, blocks.length - 1),
  );
  const nextBlocks = [...blocks];
  const [moved] = nextBlocks.splice(sourceIndex, 1);

  if (!moved) {
    return items;
  }

  nextBlocks.splice(boundedTargetIndex, 0, moved);

  let nextY = 0;
  const rebuilt: DashboardLayoutItem[] = [];

  nextBlocks.forEach((block) => {
    const blockTop = Math.min(...block.items.map((item) => item.y));
    const blockBottom = Math.max(
      ...block.items.map((item) => item.y + item.h),
    );
    const blockHeight = blockBottom - blockTop;

    block.items.forEach((item) => {
      const relativeY = item.y - blockTop;

      if (isDashboardGroupItem(item)) {
        rebuilt.push({ ...item, y: nextY + relativeY });
        return;
      }

      rebuilt.push({
        ...item,
        y: nextY + relativeY,
        groupId: block.type === 'group' ? block.key : null,
      });
    });

    nextY += blockHeight;
  });

  return rebuilt;
};
