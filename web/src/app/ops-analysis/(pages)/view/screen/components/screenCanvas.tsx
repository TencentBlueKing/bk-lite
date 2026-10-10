"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { Empty } from "antd";
import { Rnd } from "react-rnd";
import { useTranslation } from "@/utils/i18n";
import type {
  FilterValue,
  UnifiedFilterDefinition,
} from "@/app/ops-analysis/types/dashBoard";
import type { DatasourceItem } from "@/app/ops-analysis/types/dataSource";
import type {
  ScreenDisplayAdapter,
  ScreenItem,
  ScreenItemGeometry,
  ScreenViewSets,
  ScreenWidgetItem,
} from "@/app/ops-analysis/types/screen";
import type { DashboardWidgetRenderResult } from "@/app/ops-analysis/renderContract";
import type { CanvasRuntimeRefreshCause } from "@/app/ops-analysis/utils/canvasRefreshTimer";
import type { OpsChartThemeMode } from "@/app/ops-analysis/utils/chartTheme";
import { getScreenRndNodeClassName } from "../utils/classNames";
import { calculateScreenVisualMetrics } from "../utils/metrics";
import { resolveScreenCanvasBackgroundStyle } from "../utils/screenBackground";
import {
  isScreenWidgetItem,
  readScreenChromeDrag,
  SCREEN_CHROME_DRAG_MIME,
  type ScreenChromeDragPayload,
} from "../utils/screenItems";
import { getScreenTheme } from "../utils/screenTheme";
import { resolveScreenDisplayAdapter } from "../utils/viewport";
import ScreenChromeRenderer from "./screenChromeRenderer";
import { ScreenChromeSkinStyles } from "./screenChromeSkins";
import ScreenWidgetRenderer from "./screenWidgetRenderer";

const RndComponent = Rnd as unknown as React.ComponentType<any>;

const unresolvedDataSource = () => undefined as DatasourceItem | undefined;

interface ScreenCanvasProps {
  viewSets: ScreenViewSets;
  fullscreen?: boolean;
  editMode?: boolean;
  shareMode?: boolean;
  selectedItemId?: string | null;
  refreshVersion?: number;
  refreshCause?: CanvasRuntimeRefreshCause;
  screenId?: string | number;
  filterDefinitions?: UnifiedFilterDefinition[];
  unifiedFilterValues?: Record<string, FilterValue>;
  filterSearchVersion?: number;
  namespaceSearchVersion?: number;
  builtinNamespaceId?: number;
  dataSourceResolver?: (
    dataSource?: string | number,
  ) => DatasourceItem | undefined;
  onWidgetRenderStatus?: (result: DashboardWidgetRenderResult) => void;
  onSelectItem?: (itemId: string | null) => void;
  onMoveItem?: (itemId: string, position: { x: number; y: number }) => void;
  onResizeItem?: (itemId: string, size: { w: number; h: number }) => void;
  onEditItem?: (itemId: string) => void;
  onOpenItemMenu?: (itemId: string, point: { x: number; y: number }) => void;
  onDropChrome?: (
    payload: ScreenChromeDragPayload,
    point: { x: number; y: number },
  ) => void;
  forceContain?: boolean;
  onTopologyLayoutChange?: (
    itemId: string,
    next: NonNullable<
      NonNullable<ScreenWidgetItem['valueConfig']>['networkStatusTopology']
    >,
  ) => void;
}

interface CanvasSize {
  width: number;
  height: number;
}

interface WidgetGeometry {
  x: number;
  y: number;
  w: number;
  h: number;
}

interface ScreenDragBounds {
  width: number;
  height: number;
}

interface DragSession {
  pointerId: number;
  startClientX: number;
  startClientY: number;
  startGeometry: WidgetGeometry;
  nextGeometry: WidgetGeometry;
  node: HTMLElement | null;
  frame: number | null;
  moved: boolean;
}

interface ScreenRndItemProps {
  item: ScreenItemGeometry;
  editable: boolean;
  selected: boolean;
  scale: number;
  minWidth?: number;
  minHeight?: number;
  children: React.ReactNode;
  onSelectItem?: (itemId: string | null) => void;
  onMoveItem?: (itemId: string, position: { x: number; y: number }) => void;
  onResizeItem?: (itemId: string, size: { w: number; h: number }) => void;
  onEditItem?: (itemId: string) => void;
  onOpenItemMenu?: (itemId: string, point: { x: number; y: number }) => void;
}

const getWidgetGeometry = (item: ScreenItemGeometry): WidgetGeometry => ({
  x: item.x,
  y: item.y,
  w: item.w,
  h: item.h,
});

const clamp = (value: number, min: number, max: number) =>
  Math.min(Math.max(value, min), max);

const getSafeDragScale = (scale: number) =>
  Number.isFinite(scale) && scale > 0 ? scale : 1;

const getMovedScreenGeometry = (
  start: WidgetGeometry,
  delta: { clientX: number; clientY: number },
  scale: number,
  bounds: ScreenDragBounds,
): WidgetGeometry => {
  const safeScale = getSafeDragScale(scale);
  const maxX = Math.max(bounds.width - start.w, 0);
  const maxY = Math.max(bounds.height - start.h, 0);

  return {
    ...start,
    x: Math.round(clamp(start.x + delta.clientX / safeScale, 0, maxX)),
    y: Math.round(clamp(start.y + delta.clientY / safeScale, 0, maxY)),
  };
};

const ScreenRndItem: React.FC<ScreenRndItemProps> = React.memo(
  ({
    item,
    editable,
    selected,
    scale,
    minWidth = 160,
    minHeight = 110,
    children,
    onSelectItem,
    onMoveItem,
    onResizeItem,
    onEditItem,
    onOpenItemMenu,
  }) => {
    const rndRef = useRef<any>(null);
    const interactingRef = useRef(false);
    const dragSessionRef = useRef<DragSession | null>(null);
    const suppressClickRef = useRef(false);
    const [geometry, setGeometry] = useState<WidgetGeometry>(() =>
      getWidgetGeometry(item),
    );

    useEffect(() => {
      if (interactingRef.current) return;
      const nextGeometry = getWidgetGeometry(item);
      setGeometry(nextGeometry);
      rndRef.current?.updatePosition?.({
        x: nextGeometry.x,
        y: nextGeometry.y,
      });
      rndRef.current?.updateSize?.({
        width: nextGeometry.w,
        height: nextGeometry.h,
      });
    }, [item]);

    const updateGeometry = (nextGeometry: WidgetGeometry) => {
      setGeometry({
        x: Math.round(nextGeometry.x),
        y: Math.round(nextGeometry.y),
        w: Math.round(nextGeometry.w),
        h: Math.round(nextGeometry.h),
      });
    };

    useEffect(() => {
      return () => {
        const session = dragSessionRef.current;
        if (session && session.frame !== null) {
          window.cancelAnimationFrame(session.frame);
        }
      };
    }, []);

    const beginMove = (
      event: React.PointerEvent<HTMLDivElement>,
      node: HTMLElement | null,
    ) => {
      if (!editable) return;
      if (event.button !== 0) return;

      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      if (!target.closest(".screen-widget-frame__drag-handle")) return;
      if (
        target.closest("button,input,textarea,.ant-select")
      ) {
        return;
      }

      event.preventDefault();
      event.stopPropagation();
      interactingRef.current = true;
      suppressClickRef.current = false;

      node?.style.setProperty("z-index", "10000");
      node?.classList.add("screen-rnd-node--interacting");
      event.currentTarget.setPointerCapture(event.pointerId);

      const startGeometry = geometry;
      dragSessionRef.current = {
        pointerId: event.pointerId,
        startClientX: event.clientX,
        startClientY: event.clientY,
        startGeometry,
        nextGeometry: startGeometry,
        node,
        frame: null,
        moved: false,
      };
    };

    const moveItem = (event: React.PointerEvent<HTMLDivElement>) => {
      const session = dragSessionRef.current;
      if (!session || session.pointerId !== event.pointerId) return;

      event.preventDefault();
      event.stopPropagation();

      const nextGeometry = getMovedScreenGeometry(
        session.startGeometry,
        {
          clientX: event.clientX - session.startClientX,
          clientY: event.clientY - session.startClientY,
        },
        scale,
        {
          width: session.node?.parentElement?.offsetWidth || item.w,
          height: session.node?.parentElement?.offsetHeight || item.h,
        },
      );

      session.nextGeometry = nextGeometry;
      session.moved =
        session.moved ||
        nextGeometry.x !== session.startGeometry.x ||
        nextGeometry.y !== session.startGeometry.y;

      if (session.frame !== null) return;

      session.frame = window.requestAnimationFrame(() => {
        session.frame = null;
        rndRef.current?.updatePosition?.({
          x: session.nextGeometry.x,
          y: session.nextGeometry.y,
        });
      });
    };

    const finishMove = (event: React.PointerEvent<HTMLDivElement>) => {
      const session = dragSessionRef.current;
      if (!session || session.pointerId !== event.pointerId) return;

      event.preventDefault();
      event.stopPropagation();

      if (session.frame !== null) {
        window.cancelAnimationFrame(session.frame);
        session.frame = null;
      }

      rndRef.current?.updatePosition?.({
        x: session.nextGeometry.x,
        y: session.nextGeometry.y,
      });
      updateGeometry(session.nextGeometry);
      interactingRef.current = false;
      session.node?.style.setProperty("z-index", String(item.zIndex));
      session.node?.classList.remove("screen-rnd-node--interacting");

      dragSessionRef.current = null;
      suppressClickRef.current = session.moved;

      try {
        event.currentTarget.releasePointerCapture(event.pointerId);
      } catch {
        // Pointer capture may already be released by the browser.
      }

      onSelectItem?.(item.id);
      if (session.moved) {
        onMoveItem?.(item.id, {
          x: session.nextGeometry.x,
          y: session.nextGeometry.y,
        });
      }
    };

    return (
      <RndComponent
        ref={rndRef}
        bounds="parent"
        scale={scale}
        disableDragging
        default={{
          x: geometry.x,
          y: geometry.y,
          width: geometry.w,
          height: geometry.h,
        }}
        size={{
          width: geometry.w,
          height: geometry.h,
        }}
        minWidth={minWidth}
        minHeight={minHeight}
        dragHandleClassName="screen-widget-frame__drag-handle"
        cancel="button,input,textarea,.ant-select"
        enableResizing={{
          top: false,
          right: false,
          bottom: false,
          left: false,
          topRight: editable && selected,
          bottomRight: editable && selected,
          bottomLeft: editable && selected,
          topLeft: editable && selected,
        }}
        resizeHandleClasses={{
          top: "screen-rnd-handle screen-rnd-handle--n",
          right: "screen-rnd-handle screen-rnd-handle--e",
          bottom: "screen-rnd-handle screen-rnd-handle--s",
          left: "screen-rnd-handle screen-rnd-handle--w",
          topRight: "screen-rnd-handle screen-rnd-handle--ne",
          bottomRight: "screen-rnd-handle screen-rnd-handle--se",
          bottomLeft: "screen-rnd-handle screen-rnd-handle--sw",
          topLeft: "screen-rnd-handle screen-rnd-handle--nw",
        }}
        className={getScreenRndNodeClassName(editable && selected)}
        data-screen-item-id={item.id}
        style={{ zIndex: item.zIndex }}
        onClick={
          editable
            ? (event: React.MouseEvent) => {
              event.stopPropagation();
              if (suppressClickRef.current) {
                suppressClickRef.current = false;
                return;
              }
              onSelectItem?.(item.id);
            }
            : undefined
        }
        onContextMenu={
          editable
            ? (event: React.MouseEvent) => {
              event.preventDefault();
              event.stopPropagation();
              onSelectItem?.(item.id);
              onOpenItemMenu?.(item.id, { x: event.clientX, y: event.clientY });
            }
            : undefined
        }
        onResizeStart={(_, __, ref) => {
          interactingRef.current = true;
          ref.style.zIndex = "10000";
          ref.classList.add("screen-rnd-node--interacting");
          onSelectItem?.(item.id);
        }}
        onResize={(_, __, ref, ___, position) => {
          updateGeometry({
            x: position.x,
            y: position.y,
            w: ref.offsetWidth,
            h: ref.offsetHeight,
          });
        }}
        onResizeStop={(_, __, ref, ___, position) => {
          const nextGeometry = {
            x: position.x,
            y: position.y,
            w: ref.offsetWidth,
            h: ref.offsetHeight,
          };
          updateGeometry(nextGeometry);
          interactingRef.current = false;
          ref.style.zIndex = String(item.zIndex);
          ref.classList.remove("screen-rnd-node--interacting");
          onResizeItem?.(item.id, {
            w: Math.round(nextGeometry.w),
            h: Math.round(nextGeometry.h),
          });
          onMoveItem?.(item.id, {
            x: Math.round(nextGeometry.x),
            y: Math.round(nextGeometry.y),
          });
        }}
      >
        <div
          className="h-full w-full"
          onPointerDown={(event) =>
            beginMove(
              event,
              event.currentTarget.closest(
                ".screen-rnd-node",
              ) as HTMLElement | null,
            )
          }
          onPointerMove={moveItem}
          onPointerUp={finishMove}
          onPointerCancel={finishMove}
          onDoubleClick={(event) => {
            if (!editable) return;
            event.stopPropagation();
            onEditItem?.(item.id);
          }}
        >
          {children}
        </div>
      </RndComponent>
    );
  },
);

ScreenRndItem.displayName = "ScreenRndItem";

interface ScreenCanvasNodeProps {
  item: ScreenItem;
  editable: boolean;
  selected: boolean;
  scale: number;
  fitScale: number;
  screenDensity: number;
  screenUiScale: number;
  chartThemeMode: OpsChartThemeMode;
  refreshVersion: number;
  refreshCause?: CanvasRuntimeRefreshCause;
  screenId?: string | number;
  filterDefinitions?: UnifiedFilterDefinition[];
  unifiedFilterValues?: Record<string, FilterValue>;
  filterSearchVersion?: number;
  namespaceSearchVersion?: number;
  builtinNamespaceId?: number;
  dataSourceResolver: (
    dataSource?: string | number,
  ) => DatasourceItem | undefined;
  onWidgetRenderStatus?: (result: DashboardWidgetRenderResult) => void;
  onSelectItem?: (itemId: string | null) => void;
  onMoveItem?: (itemId: string, position: { x: number; y: number }) => void;
  onResizeItem?: (itemId: string, size: { w: number; h: number }) => void;
  onEditItem?: (itemId: string) => void;
  onOpenItemMenu?: (itemId: string, point: { x: number; y: number }) => void;
  onTopologyLayoutChange?: ScreenCanvasProps["onTopologyLayoutChange"];
  layoutEditable: boolean;
}

const ScreenCanvasNode = React.memo(function ScreenCanvasNode({
  item,
  editable,
  selected,
  scale,
  fitScale,
  screenDensity,
  screenUiScale,
  chartThemeMode,
  refreshVersion,
  refreshCause,
  screenId,
  filterDefinitions,
  unifiedFilterValues,
  filterSearchVersion,
  namespaceSearchVersion,
  builtinNamespaceId,
  dataSourceResolver,
  onWidgetRenderStatus,
  onSelectItem,
  onMoveItem,
  onResizeItem,
  onEditItem,
  onOpenItemMenu,
  onTopologyLayoutChange,
  layoutEditable,
}: ScreenCanvasNodeProps) {
  const isWidget = isScreenWidgetItem(item);
  const content = isWidget ? (
    <ScreenWidgetRenderer
      item={item}
      selected={editable && selected}
      editMode={editable}
      refreshVersion={refreshVersion}
      refreshCause={refreshCause}
      screenId={screenId}
      fitScale={fitScale}
      screenDensity={screenDensity}
      screenUiScale={screenUiScale}
      dataSourceResolver={dataSourceResolver}
      chartThemeMode={chartThemeMode}
      filterDefinitions={filterDefinitions}
      unifiedFilterValues={unifiedFilterValues}
      filterSearchVersion={filterSearchVersion}
      namespaceSearchVersion={namespaceSearchVersion}
      builtinNamespaceId={builtinNamespaceId}
      onRenderStatus={onWidgetRenderStatus}
      layoutEditable={layoutEditable}
      onTopologyLayoutChange={
        layoutEditable && onTopologyLayoutChange
          ? (next) => onTopologyLayoutChange(item.id, next)
          : undefined
      }
    />
  ) : (
    <div className="h-full w-full screen-chrome-item screen-widget-frame__drag-handle">
      <ScreenChromeRenderer item={item} />
    </div>
  );

  return (
    <ScreenRndItem
      item={item}
      editable={editable}
      selected={editable && selected}
      scale={scale}
      minWidth={isWidget ? 160 : 24}
      minHeight={isWidget ? 110 : 16}
      onSelectItem={onSelectItem}
      onMoveItem={onMoveItem}
      onResizeItem={onResizeItem}
      onEditItem={isWidget ? onEditItem : undefined}
      onOpenItemMenu={onOpenItemMenu}
    >
      {content}
    </ScreenRndItem>
  );
});

const ScreenCanvas: React.FC<ScreenCanvasProps> = ({
  viewSets,
  fullscreen = false,
  editMode = false,
  shareMode = false,
  selectedItemId = null,
  refreshVersion = 0,
  refreshCause = "manual",
  screenId,
  filterDefinitions,
  unifiedFilterValues,
  filterSearchVersion = 0,
  namespaceSearchVersion = 0,
  builtinNamespaceId,
  dataSourceResolver,
  onWidgetRenderStatus,
  onSelectItem,
  onMoveItem,
  onResizeItem,
  onEditItem,
  onOpenItemMenu,
  onDropChrome,
  onTopologyLayoutChange,
  forceContain = false,
}) => {
  const { t } = useTranslation();
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerSize, setContainerSize] = useState<CanvasSize>({
    width: 0,
    height: 0,
  });
  const { width, height } = viewSets.viewport;
  const screenTheme = useMemo(
    () => getScreenTheme(viewSets.viewport.theme),
    [viewSets.viewport.theme],
  );
  const displayAdapter: ScreenDisplayAdapter = resolveScreenDisplayAdapter({
    adapter: viewSets.viewport.adapter,
    fullscreen,
    shareMode,
    forceContain,
  });
  const canvasBackground = useMemo(
    () =>
      resolveScreenCanvasBackgroundStyle(
        viewSets.viewport.background,
        viewSets.viewport.theme,
      ),
    [viewSets.viewport.background, viewSets.viewport.theme],
  );

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;

    const updateSize = () => {
      const rect = element.getBoundingClientRect();
      setContainerSize({
        width: rect.width,
        height: rect.height,
      });
    };

    updateSize();
    const observer = new ResizeObserver(updateSize);
    observer.observe(element);

    return () => {
      observer.disconnect();
    };
  }, []);

  const presentation = Boolean(fullscreen || shareMode);
  const screenMetrics = useMemo(() => {
    const padding = presentation ? 0 : 32;
    return calculateScreenVisualMetrics({
      contentWidth: Math.max(containerSize.width - padding, 0),
      contentHeight: Math.max(containerSize.height - padding, 0),
      designWidth: width,
      designHeight: height,
      adapter: displayAdapter,
    });
  }, [
    containerSize.height,
    containerSize.width,
    displayAdapter,
    height,
    presentation,
    width,
  ]);

  const scale = screenMetrics.scaleX;
  const resolveDataSource = dataSourceResolver ?? unresolvedDataSource;
  const editable = Boolean(editMode && !fullscreen);
  const workbenchAlign =
    displayAdapter === "fitHeight"
      ? "items-start justify-start overflow-x-auto overflow-y-hidden"
      : displayAdapter === "fitWidth"
        ? "items-start justify-start overflow-y-auto overflow-x-hidden"
        : "items-center justify-center overflow-hidden";

  return (
    <div
      ref={containerRef}
      className={`screen-canvas-workbench flex h-full min-h-0 w-full ${workbenchAlign} ${
        presentation ? "screen-canvas-workbench--preview p-0" : "p-4"
      }`}
      style={screenTheme.variables as React.CSSProperties}
    >
      <div
        className="screen-canvas-stage shrink-0"
        style={{
          width: screenMetrics.renderedWidth,
          height: screenMetrics.renderedHeight,
        }}
      >
        <div
          className={`screen-tech-canvas relative overflow-hidden ${
            editMode && !fullscreen ? "screen-tech-canvas--editing" : ""
          }`}
          data-screen-theme={screenTheme.id}
          onClick={() => editMode && onSelectItem?.(null)}
          onDragOver={(event) => {
            if (
              !editable ||
              !Array.from(event.dataTransfer.types).includes(SCREEN_CHROME_DRAG_MIME)
            ) {
              return;
            }
            event.preventDefault();
            event.dataTransfer.dropEffect = "copy";
          }}
          onDrop={(event) => {
            if (!editable || !onDropChrome) return;
            const payload = readScreenChromeDrag(event.dataTransfer);
            if (!payload) return;
            event.preventDefault();
            const rect = event.currentTarget.getBoundingClientRect();
            const scaleX = screenMetrics.scaleX || 1;
            const scaleY = screenMetrics.scaleY || 1;
            onDropChrome(payload, {
              x: (event.clientX - rect.left) / scaleX,
              y: (event.clientY - rect.top) / scaleY,
            });
          }}
          style={{
            width,
            height,
            transform: `scale(${screenMetrics.scaleX}, ${screenMetrics.scaleY})`,
            ...canvasBackground,
            "--screen-fit-scale": screenMetrics.fitScale,
            "--screen-density": screenMetrics.screenDensity,
            "--screen-ui-scale": screenMetrics.screenUiScale,
          } as React.CSSProperties}
        >
          {editMode && !fullscreen && (
            <div className="screen-canvas-resolution">
              {width} × {height}
            </div>
          )}
          {viewSets.items.length === 0 ? (
            <div className="screen-canvas-empty" role="status">
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={t("opsAnalysis.screen.canvasEmpty")}
              />
            </div>
          ) : (
            viewSets.items.map((item) => (
              <ScreenCanvasNode
                key={item.id}
                item={item}
                editable={editable}
                selected={selectedItemId === item.id}
                scale={scale}
                fitScale={screenMetrics.fitScale}
                screenDensity={screenMetrics.screenDensity}
                screenUiScale={screenMetrics.screenUiScale}
                chartThemeMode={screenTheme.chartThemeMode}
                refreshVersion={refreshVersion ?? 0}
                refreshCause={refreshCause}
                screenId={screenId}
                filterDefinitions={filterDefinitions}
                unifiedFilterValues={unifiedFilterValues}
                filterSearchVersion={filterSearchVersion}
                namespaceSearchVersion={namespaceSearchVersion}
                builtinNamespaceId={builtinNamespaceId}
                dataSourceResolver={resolveDataSource}
                onWidgetRenderStatus={onWidgetRenderStatus}
                onSelectItem={onSelectItem}
                onMoveItem={onMoveItem}
                onResizeItem={onResizeItem}
                onEditItem={onEditItem}
                onOpenItemMenu={onOpenItemMenu}
                onTopologyLayoutChange={onTopologyLayoutChange}
                layoutEditable={Boolean(editMode && !shareMode)}
              />
            ))
          )}
        </div>
      </div>
      <ScreenChromeSkinStyles />
      <style>{`
        .screen-canvas-workbench {
          background: var(--screen-workbench-bg);
        }

        .screen-canvas-workbench--preview {
          background: var(--screen-preview-workbench-bg);
        }

        .screen-canvas-workbench--preview .screen-canvas-stage,
        .screen-canvas-workbench--preview .screen-tech-canvas {
          border: 0;
          box-shadow: none;
        }

        .screen-canvas-stage {
          position: relative;
          overflow: hidden;
          border-radius: 0;
          background: var(--screen-stage-bg);
          box-shadow: var(--screen-stage-shadow);
        }

        .screen-tech-canvas {
          position: absolute;
          left: 0;
          top: 0;
          isolation: isolate;
          background-color: var(--screen-stage-bg);
          transform-origin: left top;
          color: var(--screen-canvas-color);
          border: 1px solid var(--screen-canvas-border);
          box-shadow: var(--screen-canvas-shadow);
          background: var(--screen-canvas-bg);
        }

        .screen-tech-canvas--editing {
          outline: 2px solid var(--screen-canvas-editing-outline);
          outline-offset: -2px;
        }

        .screen-canvas-resolution {
          position: absolute;
          left: calc(8px * var(--screen-ui-scale));
          top: calc(8px * var(--screen-ui-scale));
          z-index: 31;
          border: 1px solid var(--screen-resolution-border);
          border-radius: calc(4px * var(--screen-ui-scale));
          background: var(--screen-resolution-bg);
          color: var(--screen-resolution-color);
          padding: calc(4px * var(--screen-ui-scale)) calc(7px * var(--screen-ui-scale));
          font-size: calc(14px * var(--screen-ui-scale));
          font-weight: 600;
          letter-spacing: 0;
          line-height: 1.2;
          box-shadow: var(--screen-resolution-shadow);
        }

        .screen-canvas-empty {
          position: absolute;
          inset: 0;
          display: flex;
          align-items: center;
          justify-content: center;
          color: var(--screen-empty-color);
        }

        .screen-canvas-empty .ant-empty-description {
          color: var(--screen-empty-color) !important;
        }

        .screen-rnd-node {
          transform: translateZ(0);
          transition: filter 120ms ease;
          will-change: transform;
        }

        .screen-rnd-node:not(.screen-rnd-node--selected) .screen-rnd-handle {
          opacity: 0;
          pointer-events: none;
        }

        .screen-tech-canvas--editing .screen-rnd-node:hover:not(.screen-rnd-node--selected) {
          outline: 1px dashed var(--color-primary);
          outline-offset: 0;
        }

        .screen-rnd-node--selected {
          outline: 2px solid var(--color-primary);
          outline-offset: 0;
        }

        .screen-rnd-node--interacting {
          z-index: 10000 !important;
          filter: var(--screen-rnd-interacting-filter);
        }

        .screen-rnd-handle {
          z-index: 8;
          opacity: 0.64;
          border: 1px solid var(--screen-rnd-handle-border);
          border-radius: calc(2px * var(--screen-ui-scale));
          background: var(--screen-rnd-handle-bg);
          box-shadow: var(--screen-rnd-handle-shadow);
          transition:
            background 120ms ease,
            border-color 120ms ease,
            opacity 120ms ease;
        }

        .screen-rnd-handle--n,
        .screen-rnd-handle--s {
          width: 8px !important;
          height: 8px !important;
          left: calc(50% - 4px) !important;
        }

        .screen-rnd-handle--e,
        .screen-rnd-handle--w {
          width: 8px !important;
          height: 8px !important;
          top: calc(50% - 4px) !important;
        }

        .screen-rnd-handle--n {
          top: -4px !important;
        }

        .screen-rnd-handle--s {
          bottom: -4px !important;
        }

        .screen-rnd-handle--e {
          right: -4px !important;
        }

        .screen-rnd-handle--w {
          left: -4px !important;
        }

        .screen-rnd-handle--n,
        .screen-rnd-handle--s,
        .screen-rnd-handle--e,
        .screen-rnd-handle--w,
        .screen-rnd-handle--nw,
        .screen-rnd-handle--ne,
        .screen-rnd-handle--sw,
        .screen-rnd-handle--se {
          border-radius: 0;
          opacity: 1;
          background: var(--color-bg-1);
          border: 1px solid var(--color-primary);
          box-shadow: none;
        }

        .screen-rnd-handle--nw,
        .screen-rnd-handle--ne,
        .screen-rnd-handle--sw,
        .screen-rnd-handle--se {
          width: 8px !important;
          height: 8px !important;
        }

        .screen-rnd-handle--nw {
          left: -4px !important;
          top: -4px !important;
        }

        .screen-rnd-handle--ne {
          right: -4px !important;
          top: -4px !important;
        }

        .screen-rnd-handle--sw {
          left: -4px !important;
          bottom: -4px !important;
        }

        .screen-rnd-handle--se {
          right: -4px !important;
          bottom: -4px !important;
        }

        .screen-rnd-node--selected:hover .screen-rnd-handle--nw,
        .screen-rnd-node--selected:hover .screen-rnd-handle--ne,
        .screen-rnd-node--selected:hover .screen-rnd-handle--sw,
        .screen-rnd-node--selected:hover .screen-rnd-handle--se,
        .screen-rnd-node--interacting .screen-rnd-handle--nw,
        .screen-rnd-node--interacting .screen-rnd-handle--ne,
        .screen-rnd-node--interacting .screen-rnd-handle--sw,
        .screen-rnd-node--interacting .screen-rnd-handle--se {
          opacity: 1;
          background: var(--color-bg-1);
          border-color: var(--color-primary);
        }

        .screen-widget-frame {
          position: relative;
          display: flex;
          height: 100%;
          min-height: 0;
          flex-direction: column;
          overflow: hidden;
          border: 1px solid var(--screen-widget-border);
          border-radius: 0;
          background: var(--screen-widget-bg);
          box-shadow: var(--screen-widget-shadow);
          backdrop-filter: var(--screen-widget-backdrop-filter);
          -webkit-backdrop-filter: var(--screen-widget-backdrop-filter);
          contain: layout paint style;
        }

        .screen-widget-frame::before {
          content: '';
          position: absolute;
          inset: 0;
          pointer-events: none;
          background: var(--screen-widget-overlay-bg);
          opacity: 0.55;
        }

        .screen-widget-frame--bare {
          overflow: visible;
          border-color: transparent;
          border-radius: 0;
          background: transparent;
          box-shadow: none;
          backdrop-filter: none;
        }

        .screen-widget-frame--bare::before {
          display: none;
        }

        .screen-widget-frame--bare.screen-widget-frame--editable:hover {
          border-color: transparent;
          box-shadow: none;
        }

        .screen-widget-frame__header {
          position: relative;
          z-index: 1;
          display: flex;
          height: calc(34px * var(--screen-widget-ui-scale));
          flex-shrink: 0;
          align-items: center;
          justify-content: space-between;
          padding: 0 calc(var(--screen-widget-title-padding, 10px) * var(--screen-widget-ui-scale));
          padding-left: calc((var(--screen-widget-title-padding, 10px) + 8px) * var(--screen-widget-ui-scale));
          border-bottom: 1px solid var(--screen-widget-header-border);
          background: var(--screen-widget-header-bg);
          cursor: move;
          user-select: none;
        }

        .screen-widget-frame__header::before {
          content: '';
          position: absolute;
          left: calc(6px * var(--screen-widget-ui-scale));
          top: calc(9px * var(--screen-widget-ui-scale));
          bottom: calc(9px * var(--screen-widget-ui-scale));
          width: calc(2px * var(--screen-widget-ui-scale));
          background: var(--screen-chrome-accent);
          box-shadow: 0 0 8px var(--screen-chrome-glow);
        }

        .screen-widget-frame__title {
          min-width: 0;
          width: 100%;
          overflow: hidden;
          padding-right: 0;
          text-overflow: ellipsis;
          white-space: nowrap;
          color: var(--screen-widget-title-color);
          font-size: calc(14px * var(--screen-widget-ui-scale));
          font-weight: 700;
          letter-spacing: 0;
          text-shadow: var(--screen-widget-title-shadow);
        }

        .screen-widget-frame__body {
          position: relative;
          z-index: 1;
          min-height: 0;
          flex: 1;
          padding: calc(var(--screen-widget-content-padding, 9px) * var(--screen-widget-ui-scale));
        }

        .screen-widget-frame--bare .screen-widget-frame__body {
          padding: 0;
        }

        .screen-widget-frame--kpi .screen-widget-frame__body {
          padding: 0 calc(10px * var(--screen-widget-ui-scale));
        }

        .screen-widget-frame--gauge .screen-widget-frame__body {
          padding: calc(8px * var(--screen-widget-ui-scale)) calc(10px * var(--screen-widget-ui-scale)) calc(10px * var(--screen-widget-ui-scale));
        }

        .screen-widget-frame__drag-surface {
          position: absolute;
          inset: 0;
          z-index: 3;
          cursor: move;
          user-select: none;
          background: transparent;
        }

        .screen-tech-canvas .screen-widget-frame__body .ant-empty {
          margin: 0;
          color: var(--screen-table-muted) !important;
        }

        .screen-tech-canvas .screen-widget-frame__body .ant-empty-image {
          display: none !important;
        }

        .screen-tech-canvas .screen-widget-frame__body .ant-empty-description {
          color: var(--screen-table-muted) !important;
          font-size: calc(13px * var(--screen-widget-ui-scale)) !important;
          line-height: 1.35 !important;
        }

        .screen-tech-canvas .screen-widget-frame__body .ant-spin {
          color: var(--screen-table-spin-color) !important;
        }

        .screen-tech-canvas .screen-widget-frame__body .ant-spin-dot {
          font-size: calc(16px * var(--screen-widget-ui-scale)) !important;
        }

        .screen-tech-canvas .screen-widget-frame__body .ant-spin-dot-holder,
        .screen-tech-canvas .screen-widget-frame__body .ant-spin-dot,
        .screen-tech-canvas .screen-widget-frame__body .ant-spin-dot-spin {
          width: calc(16px * var(--screen-widget-ui-scale)) !important;
          height: calc(16px * var(--screen-widget-ui-scale)) !important;
        }

        .screen-tech-canvas .screen-widget-frame__body .ant-spin-dot-item {
          background-color: var(--screen-table-spin-color) !important;
          opacity: 1 !important;
        }

        .screen-tech-canvas .ant-table-wrapper,
        .screen-tech-canvas .ant-table,
        .screen-tech-canvas .ant-table-container,
        .screen-tech-canvas .ant-table-content,
        .screen-tech-canvas .ant-table-body {
          color: var(--screen-table-text) !important;
          background: transparent !important;
        }

        .screen-tech-canvas .ant-table-thead > tr > th {
          border-bottom: 1px solid var(--screen-table-border) !important;
          background: var(--screen-table-header-bg) !important;
          color: var(--screen-table-heading) !important;
          font-size: var(--ops-screen-table-header-font-size, calc(22px * var(--screen-widget-ui-scale))) !important;
          font-weight: 700 !important;
          line-height: var(--ops-screen-table-line-height, calc(32px * var(--screen-widget-ui-scale))) !important;
          padding: var(--ops-screen-table-cell-padding-y, calc(14px * var(--screen-widget-ui-scale))) var(--ops-screen-table-cell-padding-x, calc(18px * var(--screen-widget-ui-scale))) !important;
        }

        .screen-tech-canvas .ant-table-measure-row,
        .screen-tech-canvas .ant-table-measure-cell {
          background: transparent !important;
          color: transparent !important;
          border-color: transparent !important;
        }

        .screen-tech-canvas .ant-table-tbody > tr > td {
          border-bottom: 1px solid var(--screen-table-border) !important;
          background: var(--screen-table-row-bg) !important;
          color: var(--screen-table-text) !important;
          font-size: var(--ops-screen-table-body-font-size, calc(20px * var(--screen-widget-ui-scale))) !important;
          line-height: var(--ops-screen-table-line-height, calc(30px * var(--screen-widget-ui-scale))) !important;
          padding: var(--ops-screen-table-cell-padding-y, calc(12px * var(--screen-widget-ui-scale))) var(--ops-screen-table-cell-padding-x, calc(18px * var(--screen-widget-ui-scale))) !important;
        }

        .screen-tech-canvas .ant-table-tbody > tr:nth-child(even) > td {
          background: var(--screen-table-row-even-bg) !important;
        }

        .screen-tech-canvas .ant-table-tbody > tr.ant-table-row:hover > td,
        .screen-tech-canvas .ant-table-tbody > tr > td.ant-table-cell-row-hover {
          background: var(--screen-table-row-hover-bg) !important;
        }

        .screen-tech-canvas .ant-table-placeholder,
        .screen-tech-canvas .ant-table-placeholder:hover > td {
          background: transparent !important;
        }

        .screen-tech-canvas .ant-pagination,
        .screen-tech-canvas .ant-pagination-total-text,
        .screen-tech-canvas .ant-pagination-options {
          color: var(--screen-table-muted) !important;
          font-size: var(--ops-screen-table-pagination-font-size, var(--ops-screen-table-body-font-size, calc(18px * var(--screen-widget-ui-scale)))) !important;
        }

        .screen-tech-canvas .ant-pagination-item,
        .screen-tech-canvas .ant-pagination-prev .ant-pagination-item-link,
        .screen-tech-canvas .ant-pagination-next .ant-pagination-item-link {
          border-color: var(--screen-table-border) !important;
          background: var(--screen-table-control-bg) !important;
        }

        .screen-tech-canvas .ant-pagination-item a,
        .screen-tech-canvas .ant-pagination-prev button,
        .screen-tech-canvas .ant-pagination-next button {
          color: var(--screen-table-text) !important;
        }

        .screen-tech-canvas .ant-pagination-item-active {
          border-color: var(--screen-table-spin-color) !important;
          background: var(--screen-table-control-active-bg) !important;
        }

        .screen-tech-canvas .ant-table-row-expand-icon {
          border-color: var(--screen-table-border) !important;
          background: var(--screen-table-expand-icon-bg) !important;
          color: var(--screen-table-text) !important;
        }

        .screen-tech-canvas .ant-table-row-expand-icon::before,
        .screen-tech-canvas .ant-table-row-expand-icon::after {
          background: var(--screen-table-spin-color) !important;
        }

        .screen-tech-canvas .ant-select-selector {
          border-color: var(--screen-table-border) !important;
          background: var(--screen-table-control-bg) !important;
          color: var(--screen-table-text) !important;
        }
      `}</style>
    </div>
  );
};

export default ScreenCanvas;
