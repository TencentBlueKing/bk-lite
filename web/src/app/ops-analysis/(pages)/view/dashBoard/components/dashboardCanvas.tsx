import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { createPortal } from 'react-dom';
import { Button, Dropdown, Empty, Menu, Spin } from 'antd';
import { MoreOutlined, PlusOutlined } from '@ant-design/icons';
import type {
  GridItemHTMLElement,
  GridStack as GridStackInstance,
  GridStackWidget,
} from 'gridstack';

import { useTranslation } from '@/utils/i18n';
import type {
  DashboardLayoutItem,
  DashboardWidgetLayoutItem,
  FilterValue,
  UnifiedFilterDefinition,
} from '@/app/ops-analysis/types/dashBoard';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import PermissionWrapper from '@/components/permission';
import {
  buildDashboardGridStackLayout,
  buildDashboardGridStackStructureKey,
  deserializeDashboardGridStackLayout,
  type DashboardGridStackStoredWidget,
} from '@/app/ops-analysis/utils/dashboardGridStack';

import GroupHeader from './groupHeader';
import WidgetWrapper from '@/app/ops-analysis/components/widgetDataRenderer';

import 'gridstack/dist/gridstack.min.css';

const DASHBOARD_GRID_COLS = 12;
const DASHBOARD_GRID_ROW_HEIGHT = 60;
const DASHBOARD_GRID_MARGIN: [number, number] = [4, 4];
const DASHBOARD_GRID_CONTAINER_PADDING: [number, number] = [6, 2];

const acceptOnlyWidgetNodes = (element: Element) =>
  element instanceof HTMLElement && element.dataset.nodeKind === 'widget';

interface DashboardCanvasProps {
  loading: boolean;
  isEditMode: boolean;
  isDarkTheme: boolean;
  dashboardId?: number | string;
  layout: DashboardLayoutItem[];
  collapsedGroups: Record<string, true>;
  chartTheme: {
    panelBg: string;
    panelBorderColor: string;
  };
  filterSearchVersion: number;
  namespaceSearchVersion: number;
  dashboardReloadVersion: number;
  widgetReloadVersions: Record<string, number>;
  dataSourceResolver: (
    dataSource?: string | number,
  ) => DatasourceItem | undefined;
  appliedFilterValues: Record<string, FilterValue>;
  appliedFilterDefinitions: UnifiedFilterDefinition[];
  appliedNamespaceId: number | undefined;
  selectedDashboardLocked?: boolean;
  onLayoutChange: (newLayout: DashboardLayoutItem[]) => void;
  onOpenAddModal: (groupId?: string) => void;
  onToggleCollapsedGroup: (groupId: string) => void;
  onRenameGroup: (groupId: string) => void;
  onRemoveGroup: (groupId: string) => void;
  onDeleteEntireGroup: (groupId: string) => void;
  onEditWidget: (id: string) => void;
  onDeleteWidget: (id: string) => void;
}

const DashboardCanvas: React.FC<DashboardCanvasProps> = ({
  loading,
  isEditMode,
  isDarkTheme,
  dashboardId,
  layout,
  collapsedGroups,
  chartTheme,
  filterSearchVersion,
  namespaceSearchVersion,
  dashboardReloadVersion,
  widgetReloadVersions,
  dataSourceResolver,
  appliedFilterValues,
  appliedFilterDefinitions,
  appliedNamespaceId,
  selectedDashboardLocked,
  onOpenAddModal,
  onLayoutChange,
  onToggleCollapsedGroup,
  onRenameGroup,
  onRemoveGroup,
  onDeleteEntireGroup,
  onEditWidget,
  onDeleteWidget,
}) => {
  const { t } = useTranslation();
  const gridRootRef = useRef<HTMLDivElement>(null);
  const rootGridRef = useRef<GridStackInstance | null>(null);
  const subGridRefs = useRef<Map<string, GridStackInstance>>(new Map());
  const rootItemElementsRef = useRef<Map<string, HTMLDivElement>>(new Map());
  const subGridRootElementsRef = useRef<Map<string, HTMLDivElement>>(new Map());
  const widgetHostsRef = useRef<Map<string, HTMLDivElement>>(new Map());
  const groupHeaderHostsRef = useRef<Map<string, HTMLDivElement>>(new Map());
  const groupBodyElementsRef = useRef<Map<string, HTMLDivElement>>(new Map());
  const commitFrameRef = useRef<number | null>(null);
  const syncingRef = useRef(false);

  const gridStackLayout = useMemo(
    () => buildDashboardGridStackLayout(layout),
    [layout],
  );
  const gridStructureKey = useMemo(
    () => buildDashboardGridStackStructureKey(layout),
    [layout],
  );
  const dashboardInstanceKey = useMemo(
    () => `${dashboardId ?? 'dashboard'}:${gridStructureKey}`,
    [dashboardId, gridStructureKey],
  );
  const layoutRef = useRef(layout);
  const collapsedGroupsRef = useRef(collapsedGroups);
  const gridStackLayoutRef = useRef(gridStackLayout);
  const emitLayoutChangeRef = useRef<() => void>(() => undefined);
  const handleWidgetMutationStopRef = useRef<
    (element: HTMLElement | null) => void
      >(() => undefined);
  const [, setPortalVersion] = useState(0);

  useEffect(() => {
    layoutRef.current = layout;
    collapsedGroupsRef.current = collapsedGroups;
    gridStackLayoutRef.current = gridStackLayout;
  }, [layout, collapsedGroups, gridStackLayout]);

  const clearElementMaps = useCallback(() => {
    rootItemElementsRef.current.clear();
    subGridRootElementsRef.current.clear();
    widgetHostsRef.current.clear();
    groupHeaderHostsRef.current.clear();
    groupBodyElementsRef.current.clear();
  }, []);

  const createWidgetShell = useCallback((itemId: string) => {
    const itemElement = document.createElement('div');
    itemElement.className = 'grid-stack-item';
    itemElement.dataset.nodeId = itemId;
    itemElement.dataset.nodeKind = 'widget';
    itemElement.setAttribute('gs-id', itemId);

    const contentElement = document.createElement('div');
    contentElement.className =
      'grid-stack-item-content overflow-visible! bg-transparent! shadow-none!';

    const hostElement = document.createElement('div');
    hostElement.className = 'h-full';
    hostElement.dataset.widgetHost = itemId;

    contentElement.appendChild(hostElement);
    itemElement.appendChild(contentElement);
    widgetHostsRef.current.set(itemId, hostElement);

    return itemElement;
  }, []);

  const createGroupShell = useCallback(
    (
      node: Extract<
        (typeof gridStackLayout.topLevelNodes)[number],
        { kind: 'group' }
      >,
    ) => {
      const itemElement = document.createElement('div');
      itemElement.className = 'grid-stack-item';
      itemElement.dataset.nodeId = node.id;
      itemElement.dataset.nodeKind = 'group';
      itemElement.setAttribute('gs-id', node.id);

      const contentElement = document.createElement('div');
      contentElement.className =
        'grid-stack-item-content overflow-visible! bg-transparent! shadow-none!';

      const cardElement = document.createElement('div');
      cardElement.className =
        'flex min-h-0 flex-col overflow-hidden rounded-lg border';
      cardElement.style.backgroundColor = isDarkTheme
        ? 'rgba(255,255,255,0.02)'
        : '#f7f8fa';
      cardElement.style.borderColor = isDarkTheme
        ? 'rgba(255,255,255,0.12)'
        : 'rgba(61,79,104,0.14)';

      const headerElement = document.createElement('div');
      headerElement.className = 'shrink-0 overflow-hidden rounded-t-lg';
      headerElement.style.backgroundColor = isDarkTheme
        ? 'rgba(255,255,255,0.03)'
        : '#f1f3f8';
      headerElement.style.borderBottom = isDarkTheme
        ? '1px solid rgba(255,255,255,0.08)'
        : '1px solid rgba(61,79,104,0.08)';

      const headerHost = document.createElement('div');
      headerHost.dataset.groupHeaderHost = node.id;
      headerElement.appendChild(headerHost);

      const bodyElement = document.createElement('div');
      bodyElement.className = 'px-1.5 pb-1.5 pt-1';
      bodyElement.dataset.groupBody = node.id;

      const subGridRoot = document.createElement('div');
      subGridRoot.className = 'grid-stack min-h-0';
      subGridRoot.dataset.subgridRoot = node.id;
      bodyElement.appendChild(subGridRoot);

      cardElement.append(headerElement, bodyElement);
      contentElement.appendChild(cardElement);
      itemElement.appendChild(contentElement);

      groupHeaderHostsRef.current.set(node.id, headerHost);
      groupBodyElementsRef.current.set(node.id, bodyElement);
      subGridRootElementsRef.current.set(node.id, subGridRoot);

      return itemElement;
    },
    [isDarkTheme],
  );

  const buildCurrentLayout = useCallback((): DashboardLayoutItem[] => {
    const rootGrid = rootGridRef.current;
    const currentLayout = layoutRef.current;
    const currentCollapsedGroups = collapsedGroupsRef.current;

    if (!rootGrid) {
      return currentLayout;
    }

    const itemById = new Map(currentLayout.map((item) => [item.i, item]));
    const topLevelWidgets = (rootGrid.save(false, false) ||
      []) as GridStackWidget[];
    const storedWidgets: DashboardGridStackStoredWidget[] = [];

    topLevelWidgets.forEach((widget) => {
      const itemId = String(widget.id ?? '');
      const item = itemById.get(itemId);

      if (!item) {
        return;
      }

      const nextX = widget.x ?? item.x;
      const nextY = Math.max(widget.y ?? item.y, 0);
      const nextW = widget.w ?? item.w;

      if (item.itemType === 'group') {
        const subGrid = subGridRefs.current.get(item.i);
        const childWidgets = (subGrid?.save(false, false) ||
          []) as GridStackWidget[];
        const children = childWidgets.flatMap((child) => {
          const childId = String(child.id ?? '');
          const childItem = itemById.get(childId);

          if (!childItem || childItem.itemType === 'group') {
            return [];
          }

          return [
            {
              id: childItem.i,
              x: child.x ?? childItem.x,
              y: Math.max(child.y ?? 0, 0),
              w: child.w ?? childItem.w,
              h: child.h ?? childItem.h,
              itemType: 'widget' as const,
              name: childItem.name,
              description: childItem.description,
              valueConfig: childItem.valueConfig,
            } satisfies DashboardGridStackStoredWidget,
          ];
        });

        storedWidgets.push({
          id: item.i,
          x: nextX,
          y: nextY,
          w: nextW,
          h: widget.h ?? item.h,
          itemType: 'group',
          name: item.name,
          description: item.description,
          headerH: item.h,
          sizeToContent: !currentCollapsedGroups[item.i],
          subGridOpts: {
            children,
          },
        });
        return;
      }

      storedWidgets.push({
        id: item.i,
        x: nextX,
        y: nextY,
        w: nextW,
        h: widget.h ?? item.h,
        itemType: 'widget',
        name: item.name,
        description: item.description,
        valueConfig: item.valueConfig,
      });
    });

    return deserializeDashboardGridStackLayout(storedWidgets);
  }, []);

  const scheduleGridCommit = useCallback((callback: () => void) => {
    if (typeof window === 'undefined') {
      callback();
      return;
    }

    if (commitFrameRef.current !== null) {
      window.cancelAnimationFrame(commitFrameRef.current);
    }

    commitFrameRef.current = window.requestAnimationFrame(() => {
      commitFrameRef.current = null;
      callback();
    });
  }, []);

  const resizeParentGroupToContent = useCallback(
    (element: HTMLElement | null) => {
      const rootGrid = rootGridRef.current;

      if (!rootGrid || !element) {
        return;
      }

      const groupElement =
        element.dataset.nodeKind === 'group'
          ? element
          : element.closest('[data-node-kind="group"]');

      if (!(groupElement instanceof HTMLElement)) {
        return;
      }

      rootGrid.resizeToContent(groupElement as GridItemHTMLElement);
    },
    [],
  );

  const syncGroupPresentation = useCallback(
    (
      node: Extract<
        (typeof gridStackLayout.topLevelNodes)[number],
        { kind: 'group' }
      >,
      options?: { preservePosition?: boolean },
    ) => {
      const rootGrid = rootGridRef.current;
      const bodyElement = groupBodyElementsRef.current.get(node.id);
      const groupElement = rootItemElementsRef.current.get(node.id);
      const isCollapsed = Boolean(collapsedGroupsRef.current[node.id]);

      if (bodyElement) {
        bodyElement.style.display = isCollapsed ? 'none' : '';
        // bodyElement.style.minHeight =
        //   visibleChildRows > 0
        //     ? `${visibleChildRows * DASHBOARD_GRID_ROW_HEIGHT + Math.max(visibleChildRows - 1, 0) * DASHBOARD_GRID_MARGIN[1] + 8}px`
        //     : '0';
      }

      if (!rootGrid || !groupElement) {
        return;
      }

      const nextOptions = options?.preservePosition
        ? {
          id: node.id,
          h: isCollapsed ? node.item.h : node.h,
          sizeToContent: !isCollapsed,
        }
        : {
          id: node.id,
          x: node.x,
          y: node.y,
          w: node.w,
          h: isCollapsed ? node.item.h : node.h,
          sizeToContent: !isCollapsed,
        };

      rootGrid.update(groupElement, nextOptions);

      if (!isCollapsed) {
        rootGrid.resizeToContent(groupElement as GridItemHTMLElement);
      }
    },
    [],
  );

  const syncRootGridNode = useCallback(
    (node: (typeof gridStackLayout.topLevelNodes)[number]) => {
      const rootGrid = rootGridRef.current;
      const element = rootItemElementsRef.current.get(node.id);

      if (!rootGrid || !element) {
        return;
      }

      const isCollapsedGroup =
        node.kind === 'group' && Boolean(collapsedGroupsRef.current[node.id]);

      rootGrid.update(element, {
        id: node.id,
        x: node.x,
        y: node.y,
        w: node.w,
        h: node.kind === 'group' && isCollapsedGroup ? node.item.h : node.h,
        sizeToContent: node.kind === 'group' && !isCollapsedGroup,
      });
    },
    [],
  );

  const emitLayoutChange = useCallback(() => {
    if (!isEditMode || syncingRef.current) {
      return;
    }

    scheduleGridCommit(() => {
      if (!isEditMode || syncingRef.current) {
        return;
      }

      onLayoutChange(buildCurrentLayout());
    });
  }, [buildCurrentLayout, isEditMode, onLayoutChange, scheduleGridCommit]);

  const handleWidgetMutationStop = useCallback(
    (element: HTMLElement | null) => {
      if (!isEditMode || syncingRef.current || !element) {
        return;
      }

      scheduleGridCommit(() => {
        resizeParentGroupToContent(element);
        if (!isEditMode || syncingRef.current) {
          return;
        }

        onLayoutChange(buildCurrentLayout());
      });
    },
    [
      buildCurrentLayout,
      isEditMode,
      onLayoutChange,
      resizeParentGroupToContent,
      scheduleGridCommit,
    ],
  );

  useEffect(() => {
    emitLayoutChangeRef.current = emitLayoutChange;
    handleWidgetMutationStopRef.current = handleWidgetMutationStop;
  }, [emitLayoutChange, handleWidgetMutationStop]);

  const renderWidgetCard = useCallback(
    (item: DashboardWidgetLayoutItem) => {
      const isTableWidget =
        item.valueConfig?.chartType === 'table' ||
        item.valueConfig?.chartType === 'eventTable';
      const menu = (
        <Menu>
          <Menu.Item key="edit" onClick={() => onEditWidget(item.i)}>
            {t('common.edit')}
          </Menu.Item>
          <Menu.Item key="delete" onClick={() => onDeleteWidget(item.i)}>
            {t('common.delete')}
          </Menu.Item>
        </Menu>
      );

      return (
        <div
          className="widget rounded-lg overflow-hidden p-3 flex h-full flex-col"
          style={{
            backgroundColor: chartTheme.panelBg,
            border: `1px solid ${chartTheme.panelBorderColor}`,
          }}
        >
          <div className="widget-header mb-2 flex justify-between items-start gap-2">
            <div className="flex-1 min-w-0">
              <h4 className="truncate text-[14px] font-medium leading-5 text-(--color-text-2)">
                {item.name}
              </h4>
              {item.description?.trim() && (
                <p className="mt-0.5 text-[11px] leading-4 text-(--color-text-3) wrap-break-word whitespace-normal">
                  {item.description}
                </p>
              )}
            </div>
            {isEditMode && (
              <Dropdown overlay={menu} trigger={['click']}>
                <button
                  type="button"
                  aria-label={t('common.more')}
                  className="no-drag text-(--color-text-2) hover:text-(--color-text-1) transition-colors cursor-pointer"
                >
                  <MoreOutlined
                    aria-hidden="true"
                    style={{ fontSize: '18px' }}
                  />
                </button>
              </Dropdown>
            )}
          </div>
          <div
            className="widget-body flex-1 h-full"
            style={{
              overflow: isTableWidget ? 'visible' : 'hidden',
            }}
          >
            <WidgetWrapper
              dashboardId={dashboardId}
              widgetId={item.i}
              key={`${dashboardId ?? 'dashboard'}:${item.i}`}
              chartType={item.valueConfig?.chartType}
              config={item.valueConfig}
              filterSearchVersion={filterSearchVersion}
              namespaceSearchVersion={namespaceSearchVersion}
              reloadVersion={`${dashboardReloadVersion}:${widgetReloadVersions[item.i] || 0}`}
              dataSource={dataSourceResolver(item.valueConfig?.dataSource)}
              unifiedFilterValues={appliedFilterValues}
              filterDefinitions={appliedFilterDefinitions}
              builtinNamespaceId={appliedNamespaceId}
            />
          </div>
        </div>
      );
    },
    [
      appliedFilterDefinitions,
      appliedFilterValues,
      appliedNamespaceId,
      chartTheme.panelBg,
      chartTheme.panelBorderColor,
      dashboardReloadVersion,
      dataSourceResolver,
      filterSearchVersion,
      isEditMode,
      namespaceSearchVersion,
      onDeleteWidget,
      onEditWidget,
      t,
      widgetReloadVersions,
    ],
  );

  useEffect(() => {
    if (!gridRootRef.current) {
      return;
    }

    let cancelled = false;

    const destroyGrids = () => {
      subGridRefs.current.forEach((grid) => grid.destroy(false));
      subGridRefs.current.clear();
      rootGridRef.current?.destroy(false);
      rootGridRef.current = null;

      if (gridRootRef.current) {
        gridRootRef.current.replaceChildren();
      }

      clearElementMaps();
      setPortalVersion((previous) => previous + 1);
    };

    const initGrid = async () => {
      syncingRef.current = true;
      destroyGrids();

      const { GridStack } = await import('gridstack');

      if (cancelled || !gridRootRef.current) {
        return;
      }

      const nextGridStackLayout = gridStackLayoutRef.current;

      nextGridStackLayout.topLevelNodes.forEach((node) => {
        if (node.kind === 'group') {
          const itemElement = createGroupShell(node);
          rootItemElementsRef.current.set(node.id, itemElement);
          gridRootRef.current?.appendChild(itemElement);
          return;
        }

        const itemElement = createWidgetShell(node.id);
        rootItemElementsRef.current.set(node.id, itemElement);
        gridRootRef.current?.appendChild(itemElement);
      });

      const rootGrid = GridStack.init(
        {
          column: DASHBOARD_GRID_COLS,
          cellHeight: DASHBOARD_GRID_ROW_HEIGHT,
          margin: DASHBOARD_GRID_MARGIN[0],
          float: false,
          animate: false,
          acceptWidgets: isEditMode ? acceptOnlyWidgetNodes : false,
          disableDrag: !isEditMode,
          disableResize: !isEditMode,
          draggable: {
            cancel: '.no-drag, .widget-body',
          },
        },
        gridRootRef.current,
      );

      rootGridRef.current = rootGrid;

      nextGridStackLayout.topLevelNodes.forEach((node) => {
        const element = rootItemElementsRef.current.get(node.id);
        const isCollapsedGroup =
          node.kind === 'group' && Boolean(collapsedGroupsRef.current[node.id]);

        if (!element) {
          return;
        }

        rootGrid.makeWidget(element, {
          id: node.id,
          x: node.x,
          y: node.y,
          w: node.w,
          h: node.kind === 'group' && isCollapsedGroup ? node.item.h : node.h,
          sizeToContent: node.kind === 'group' && !isCollapsedGroup,
          noMove: false,
          noResize: node.kind === 'group',
        });

        rootGrid.update(element, {
          id: node.id,
          x: node.x,
          y: node.y,
          w: node.w,
          h: node.kind === 'group' && isCollapsedGroup ? node.item.h : node.h,
          sizeToContent: node.kind === 'group' && !isCollapsedGroup,
        });
      });
      rootGrid.on('dragstop', (_event: Event, element: GridItemHTMLElement) => {
        if ((element as HTMLElement).dataset.nodeKind === 'widget') {
          handleWidgetMutationStopRef.current(element as HTMLElement);
          return;
        }

        emitLayoutChangeRef.current();
      });
      rootGrid.on(
        'resizestop',
        (_event: Event, element: GridItemHTMLElement) => {
          if ((element as HTMLElement).dataset.nodeKind === 'widget') {
            handleWidgetMutationStopRef.current(element as HTMLElement);
            return;
          }

          emitLayoutChangeRef.current();
        },
      );

      nextGridStackLayout.groupNodes.forEach((node) => {
        const subGridRoot = subGridRootElementsRef.current.get(node.id);

        if (!subGridRoot) {
          return;
        }

        const subGrid = GridStack.init(
          {
            column: 'auto',
            cellHeight: DASHBOARD_GRID_ROW_HEIGHT,
            margin: DASHBOARD_GRID_MARGIN[0],
            float: false,
            animate: false,
            acceptWidgets: isEditMode ? acceptOnlyWidgetNodes : false,
            disableDrag: !isEditMode,
            disableResize: !isEditMode,
            draggable: {
              cancel: '.no-drag, .widget-body',
            },
          },
          subGridRoot,
        );

        subGridRefs.current.set(node.id, subGrid);

        node.children.forEach((child) => {
          const element = createWidgetShell(child.id);
          subGridRoot.appendChild(element);

          subGrid.makeWidget(element, {
            id: child.id,
            x: child.x,
            y: child.y,
            w: child.w,
            h: child.h,
            noMove: false,
            noResize: false,
          });
        });

        const groupElement = rootItemElementsRef.current.get(node.id) ?? null;
        if (groupElement) {
          requestAnimationFrame(() => {
            if (!cancelled) {
              syncGroupPresentation(node);
            }
          });
        }
        subGrid.on(
          'dragstop',
          (_event: Event, element: GridItemHTMLElement) => {
            handleWidgetMutationStopRef.current(element as HTMLElement);
          },
        );
        subGrid.on(
          'resizestop',
          (_event: Event, element: GridItemHTMLElement) => {
            handleWidgetMutationStopRef.current(element as HTMLElement);
          },
        );
      });

      setPortalVersion((previous) => previous + 1);

      requestAnimationFrame(() => {
        if (!cancelled) {
          syncingRef.current = false;
        }
      });
    };

    void initGrid();

    return () => {
      cancelled = true;
      syncingRef.current = true;
      if (commitFrameRef.current !== null) {
        window.cancelAnimationFrame(commitFrameRef.current);
        commitFrameRef.current = null;
      }
      destroyGrids();
    };
  }, [
    clearElementMaps,
    createGroupShell,
    createWidgetShell,
    dashboardInstanceKey,
    syncGroupPresentation,
  ]);

  useEffect(() => {
    const rootGrid = rootGridRef.current;

    if (!rootGrid) {
      return;
    }

    rootGrid.updateOptions({
      acceptWidgets: isEditMode ? acceptOnlyWidgetNodes : false,
      disableDrag: !isEditMode,
      disableResize: !isEditMode,
    });
    rootGrid.enableMove(isEditMode);
    rootGrid.enableResize(isEditMode);

    subGridRefs.current.forEach((subGrid) => {
      subGrid.updateOptions({
        acceptWidgets: isEditMode ? acceptOnlyWidgetNodes : false,
        disableDrag: !isEditMode,
        disableResize: !isEditMode,
      });
      subGrid.enableMove(isEditMode);
      subGrid.enableResize(isEditMode);
    });
  }, [isEditMode]);

  useEffect(() => {
    if (!rootGridRef.current) {
      return;
    }

    let cancelled = false;

    const frameId = window.requestAnimationFrame(() => {
      if (cancelled || !rootGridRef.current) {
        return;
      }

      gridStackLayout.topLevelNodes.forEach((node) => {
        if (node.kind === 'group') {
          syncGroupPresentation(node);
          return;
        }

        syncRootGridNode(node);
      });
    });

    return () => {
      cancelled = true;
      window.cancelAnimationFrame(frameId);
    };
  }, [gridStackLayout.topLevelNodes, syncGroupPresentation, syncRootGridNode]);

  useEffect(() => {
    if (!rootGridRef.current) {
      return;
    }

    let cancelled = false;

    const frameId = window.requestAnimationFrame(() => {
      if (cancelled) {
        return;
      }

      gridStackLayout.groupNodes.forEach((node) => {
        syncGroupPresentation(node, { preservePosition: true });
      });
    });

    return () => {
      cancelled = true;
      window.cancelAnimationFrame(frameId);
    };
  }, [collapsedGroups, gridStackLayout.groupNodes, syncGroupPresentation]);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Spin size="large" />
      </div>
    );
  }

  if (!layout.length) {
    return (
      <div className="h-full flex flex-col items-center justify-center">
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={
            <span className="text-(--color-text-2)">
              {t('dashboard.addView')}
            </span>
          }
        >
          <PermissionWrapper requiredPermissions={['EditChart']}>
            <Button
              type="primary"
              icon={<PlusOutlined aria-hidden="true" />}
              onClick={() => onOpenAddModal()}
              disabled={selectedDashboardLocked}
            >
              {t('dashboard.addView')}
            </Button>
          </PermissionWrapper>
        </Empty>
      </div>
    );
  }

  const groupHeaderPortals = gridStackLayout.groupNodes.map((node) => {
    const host = groupHeaderHostsRef.current.get(node.id);

    if (!host) {
      return null;
    }

    return createPortal(
      <GroupHeader
        item={node.item}
        collapsed={!!collapsedGroups[node.id]}
        isEditMode={isEditMode}
        onAddView={() => onOpenAddModal(node.id)}
        onToggle={() => onToggleCollapsedGroup(node.id)}
        onRename={() => onRenameGroup(node.id)}
        onRemoveGroup={() => onRemoveGroup(node.id)}
        onDeleteGroup={() => onDeleteEntireGroup(node.id)}
      />,
      host,
      `group-header:${dashboardId ?? 'dashboard'}:${node.id}`,
    );
  });

  const widgetPortals = [
    ...gridStackLayout.topLevelNodes
      .filter(
        (
          node,
        ): node is Extract<
          (typeof gridStackLayout.topLevelNodes)[number],
          { kind: 'widget' }
        > => node.kind === 'widget',
      )
      .map((node) => ({ id: node.id, item: node.item })),
    ...gridStackLayout.groupNodes.flatMap((node) =>
      collapsedGroups[node.id]
        ? []
        : node.children.map((child) => ({ id: child.id, item: child.item })),
    ),
  ].map(({ id, item }) => {
    const host = widgetHostsRef.current.get(id);

    if (!host) {
      return null;
    }

    return createPortal(renderWidgetCard(item), host, `widget:${id}`);
  });

  return (
    <div
      className="relative w-full"
      style={{
        padding: `${DASHBOARD_GRID_CONTAINER_PADDING[1]}px ${DASHBOARD_GRID_CONTAINER_PADDING[0]}px`,
      }}
    >
      <style jsx global>{`
        .grid-stack > .grid-stack-item > .grid-stack-item-content,
        .grid-stack > .grid-stack-placeholder > .placeholder-content {
          overflow: visible;
        }

        .grid-stack-item > .ui-resizable-handle {
          width: 24px;
          height: 24px;
          background-repeat: no-repeat;
          background-origin: content-box;
          box-sizing: border-box;
          background-image: url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA2IDYiIHN0eWxlPSJiYWNrZ3JvdW5kLWNvbG9yOiNmZmZmZmYwMCIgeD0iMHB4IiB5PSIwcHgiIHdpZHRoPSI2cHgiIGhlaWdodD0iNnB4Ij48ZyBvcGFjaXR5PSIwLjMwMiI+PHBhdGggZD0iTSA2IDYgTCAwIDYgTCAwIDQuMiBMIDQgNC4yIEwgNC4yIDQuMiBMIDQuMiAwIEwgNiAwIEwgNiA2IEwgNiA2IFoiIGZpbGw9IiMwMDAwMDAiLz48L2c+PC9zdmc+');
          background-position: bottom right;
          transform: rotate(0);
          padding: 0 3px 3px 0;
        }

        .grid-stack-item > .ui-resizable-se {
          right: calc(var(--gs-item-margin-right) + 2px);
          bottom: calc(var(--gs-item-margin-bottom));
        }

        .grid-stack-item[data-node-kind='group'] > .ui-resizable-handle {
          display: none !important;
        }

        .dark .grid-stack-item > .ui-resizable-handle,
        [data-theme='dark'] .grid-stack-item > .ui-resizable-handle {
          filter: invert(1) opacity(0.65);
        }

        .grid-stack-item > .ui-resizable-n,
        .grid-stack-item > .ui-resizable-ne,
        .grid-stack-item > .ui-resizable-e,
        .grid-stack-item > .ui-resizable-s,
        .grid-stack-item > .ui-resizable-sw,
        .grid-stack-item > .ui-resizable-w,
        .grid-stack-item > .ui-resizable-nw {
          display: none !important;
        }
      `}</style>
      <div ref={gridRootRef} className="grid-stack relative z-10 w-full" />
      {groupHeaderPortals as unknown as React.ReactNode}
      {widgetPortals as unknown as React.ReactNode}
    </div>
  );
};

export default DashboardCanvas;
