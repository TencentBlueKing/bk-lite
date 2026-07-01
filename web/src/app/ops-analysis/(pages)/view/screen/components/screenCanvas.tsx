"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { Rnd } from "react-rnd";
import { useTranslation } from "@/utils/i18n";
import type {
  FilterValue,
  UnifiedFilterDefinition,
} from "@/app/ops-analysis/types/dashBoard";
import type { DatasourceItem } from "@/app/ops-analysis/types/dataSource";
import type {
  ScreenViewSets,
  ScreenWidgetItem,
} from "@/app/ops-analysis/types/screen";
import {
  formatScreenClock,
  getScreenRndNodeClassName,
} from "../utils/classNames";
import { calculateScreenVisualMetrics } from "../utils/metrics";
import ScreenWidgetRenderer from "./screenWidgetRenderer";

const RndComponent = Rnd as unknown as React.ComponentType<any>;

interface ScreenCanvasProps {
  viewSets: ScreenViewSets;
  fullscreen?: boolean;
  editMode?: boolean;
  selectedItemId?: string | null;
  refreshVersion?: number;
  screenId?: string | number;
  filterDefinitions?: UnifiedFilterDefinition[];
  unifiedFilterValues?: Record<string, FilterValue>;
  filterSearchVersion?: number;
  namespaceSearchVersion?: number;
  builtinNamespaceId?: number;
  dataSourceResolver?: (
    dataSource?: string | number,
  ) => DatasourceItem | undefined;
  onSelectItem?: (itemId: string | null) => void;
  onMoveItem?: (itemId: string, position: { x: number; y: number }) => void;
  onResizeItem?: (itemId: string, size: { w: number; h: number }) => void;
  onEditItem?: (itemId: string) => void;
  onDeleteItem?: (itemId: string) => void;
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

interface ScreenRndItemProps {
  item: ScreenWidgetItem;
  selected: boolean;
  scale: number;
  children: React.ReactNode;
  onSelectItem?: (itemId: string | null) => void;
  onMoveItem?: (itemId: string, position: { x: number; y: number }) => void;
  onResizeItem?: (itemId: string, size: { w: number; h: number }) => void;
  onEditItem?: (itemId: string) => void;
}

const getWidgetGeometry = (item: ScreenWidgetItem): WidgetGeometry => ({
  x: item.x,
  y: item.y,
  w: item.w,
  h: item.h,
});

const ScreenRndItem: React.FC<ScreenRndItemProps> = React.memo(
  ({
    item,
    selected,
    scale,
    children,
    onSelectItem,
    onMoveItem,
    onResizeItem,
    onEditItem,
  }) => {
    const rndRef = useRef<any>(null);
    const interactingRef = useRef(false);
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

    return (
      <RndComponent
        ref={rndRef}
        bounds="parent"
        scale={scale}
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
        minWidth={160}
        minHeight={110}
        dragHandleClassName="screen-widget-frame__header"
        cancel=".screen-widget-frame__actions,.screen-widget-frame__action,button,input,textarea,.ant-select"
        enableResizing={{
          top: false,
          right: false,
          bottom: false,
          left: false,
          topRight: selected,
          bottomRight: selected,
          bottomLeft: selected,
          topLeft: selected,
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
        className={getScreenRndNodeClassName(selected)}
        style={{ zIndex: item.zIndex }}
        onClick={(event: React.MouseEvent) => {
          event.stopPropagation();
          onSelectItem?.(item.id);
        }}
        onDragStart={(_, data) => {
          interactingRef.current = true;
          if (data.node) {
            data.node.style.zIndex = "10000";
            data.node.classList.add("screen-rnd-node--interacting");
          }
          onSelectItem?.(item.id);
        }}
        onDragStop={(_, data) => {
          const nextGeometry = {
            ...geometry,
            x: data.x,
            y: data.y,
          };
          updateGeometry(nextGeometry);
          interactingRef.current = false;
          if (data.node) {
            data.node.style.zIndex = String(item.zIndex);
            data.node.classList.remove("screen-rnd-node--interacting");
          }
          onMoveItem?.(item.id, {
            x: Math.round(nextGeometry.x),
            y: Math.round(nextGeometry.y),
          });
        }}
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
          onDoubleClick={(event) => {
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

const ScreenCanvas: React.FC<ScreenCanvasProps> = ({
  viewSets,
  fullscreen = false,
  editMode = false,
  selectedItemId = null,
  refreshVersion = 0,
  screenId,
  filterDefinitions,
  unifiedFilterValues,
  filterSearchVersion = 0,
  namespaceSearchVersion = 0,
  builtinNamespaceId,
  dataSourceResolver,
  onSelectItem,
  onMoveItem,
  onResizeItem,
  onEditItem,
  onDeleteItem,
}) => {
  const { t } = useTranslation();
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerSize, setContainerSize] = useState<CanvasSize>({
    width: 0,
    height: 0,
  });
  const [currentTime, setCurrentTime] = useState(() => new Date());
  const { width, height } = viewSets.viewport;
  const screenTitle = viewSets.decorations.title?.trim() || "";
  const shouldShowTitle = Boolean(
    viewSets.decorations.showTitle && screenTitle,
  );
  const shouldShowClock = Boolean(viewSets.decorations.showClock);

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

  useEffect(() => {
    if (!shouldShowClock) return;
    const timer = window.setInterval(() => {
      setCurrentTime(new Date());
    }, 1000);

    return () => window.clearInterval(timer);
  }, [shouldShowClock]);

  const screenMetrics = useMemo(() => {
    const padding = fullscreen ? 32 : 32;
    return calculateScreenVisualMetrics({
      contentWidth: Math.max(containerSize.width - padding, 0),
      contentHeight: Math.max(containerSize.height - padding, 0),
      designWidth: width,
      designHeight: height,
    });
  }, [containerSize.height, containerSize.width, fullscreen, height, width]);

  const scale = screenMetrics.fitScale;
  const resolveDataSource =
    dataSourceResolver || (() => undefined as DatasourceItem | undefined);

  const renderScreenItem = (item: ScreenWidgetItem) => {
    const selected = selectedItemId === item.id;

    const content = (
      <ScreenWidgetRenderer
        item={item}
        selected={selected}
        editMode={editMode}
        refreshVersion={refreshVersion}
        screenId={screenId}
        fitScale={scale}
        screenDensity={screenMetrics.screenDensity}
        screenUiScale={screenMetrics.screenUiScale}
        dataSourceResolver={resolveDataSource}
        filterDefinitions={filterDefinitions}
        unifiedFilterValues={unifiedFilterValues}
        filterSearchVersion={filterSearchVersion}
        namespaceSearchVersion={namespaceSearchVersion}
        builtinNamespaceId={builtinNamespaceId}
        onEditConfig={() => onEditItem?.(item.id)}
        onDelete={onDeleteItem}
      />
    );

    if (!editMode || fullscreen) {
      return (
        <div
          key={item.id}
          style={{
            position: "absolute",
            left: item.x,
            top: item.y,
            width: item.w,
            height: item.h,
            zIndex: item.zIndex,
          }}
        >
          {content}
        </div>
      );
    }

    return (
      <ScreenRndItem
        key={item.id}
        item={item}
        selected={selected}
        scale={scale}
        onSelectItem={onSelectItem}
        onMoveItem={onMoveItem}
        onResizeItem={onResizeItem}
        onEditItem={onEditItem}
      >
        {content}
      </ScreenRndItem>
    );
  };

  return (
    <div
      ref={containerRef}
      className={`screen-canvas-workbench flex h-full min-h-0 w-full items-center justify-center overflow-hidden ${
        fullscreen ? "screen-canvas-workbench--preview p-4" : "p-5"
      }`}
    >
      <div
        className="screen-canvas-stage"
        style={{
          width: screenMetrics.renderedWidth,
          height: screenMetrics.renderedHeight,
        }}
      >
        <div
          className={`screen-tech-canvas relative overflow-hidden ${
            editMode && !fullscreen ? "screen-tech-canvas--editing" : ""
          }`}
          onClick={() => editMode && onSelectItem?.(null)}
          style={{
            width,
            height,
            transform: `scale(${scale})`,
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
          {(shouldShowTitle || shouldShowClock) && (
            <div
              className={`screen-canvas-header pointer-events-none absolute left-0 right-0 top-14 z-20 ${
                shouldShowTitle ? "" : "screen-canvas-header--clock-only"
              }`}
            >
              {shouldShowTitle && (
                <>
                  <div className="screen-canvas-header__side screen-canvas-header__side--left">
                    <div className="screen-canvas-header__rail" />
                  </div>
                  <div className="screen-canvas-title">
                    <span>{screenTitle}</span>
                  </div>
                </>
              )}
              <div className="screen-canvas-header__side screen-canvas-header__side--right">
                {shouldShowTitle && (
                  <div className="screen-canvas-header__rail" />
                )}
                {shouldShowClock && (
                  <div className="screen-canvas-clock">
                    {formatScreenClock(currentTime)}
                  </div>
                )}
              </div>
            </div>
          )}
          {viewSets.items.length === 0 ? (
            <div className="screen-canvas-empty">
              <div className="screen-canvas-empty__icon" aria-hidden="true" />
              <div className="screen-canvas-empty__title">
                {t("opsAnalysis.screen.canvasEmpty")}
              </div>
            </div>
          ) : (
            viewSets.items.map((item) => renderScreenItem(item))
          )}
        </div>
      </div>
      <style>{`
        .screen-canvas-workbench {
          background:
            radial-gradient(circle at 50% -12%, rgba(34, 211, 238, 0.12), transparent 28%),
            radial-gradient(circle at 12% 22%, rgba(59, 130, 246, 0.08), transparent 22%),
            linear-gradient(180deg, #08111f 0%, #040815 100%);
        }

        .screen-canvas-workbench--preview {
          background: #020617;
        }

        .screen-canvas-stage {
          position: relative;
          overflow: hidden;
          border-radius: 14px;
          background: #020617;
          box-shadow:
            0 22px 58px rgba(0, 0, 0, 0.38),
            0 0 0 1px rgba(148, 163, 184, 0.12);
        }

        .screen-tech-canvas {
          position: absolute;
          left: 0;
          top: 0;
          transform-origin: left top;
          color: #eafbff;
          border: 1px solid rgba(56, 189, 248, 0.12);
          box-shadow:
            inset 0 0 120px rgba(14, 165, 233, 0.06),
            inset 0 0 0 1px rgba(255, 255, 255, 0.025);
          background:
            radial-gradient(circle at 52% 14%, rgba(34, 211, 238, 0.14), transparent 26%),
            radial-gradient(circle at 18% 34%, rgba(37, 99, 235, 0.11), transparent 30%),
            radial-gradient(circle at 82% 76%, rgba(14, 165, 233, 0.08), transparent 28%),
            linear-gradient(135deg, #061428 0%, #09213c 46%, #020713 100%);
          background-size: auto;
        }

        .screen-tech-canvas::before {
          display: none;
        }

        .screen-tech-canvas--editing {
          outline: 2px solid rgba(56, 189, 248, 0.26);
          outline-offset: -2px;
        }

        .screen-canvas-resolution {
          position: absolute;
          left: calc(8px * var(--screen-ui-scale));
          top: calc(8px * var(--screen-ui-scale));
          z-index: 31;
          border: 1px solid rgba(125, 211, 252, 0.14);
          border-radius: calc(4px * var(--screen-ui-scale));
          background: rgba(4, 16, 34, 0.42);
          color: rgba(224, 251, 255, 0.56);
          padding: calc(4px * var(--screen-ui-scale)) calc(7px * var(--screen-ui-scale));
          font-size: calc(14px * var(--screen-ui-scale));
          font-weight: 600;
          letter-spacing: 0;
          line-height: 1.2;
          box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
        }

        .screen-canvas-header {
          top: calc(14px * var(--screen-ui-scale));
          display: grid;
          grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
          align-items: center;
          gap: calc(18px * var(--screen-ui-scale));
          padding: 0 calc(94px * var(--screen-ui-scale));
        }

        .screen-canvas-header--clock-only {
          display: block;
          top: calc(18px * var(--screen-ui-scale));
          padding: 0 calc(48px * var(--screen-ui-scale));
        }

        .screen-canvas-header--clock-only .screen-canvas-header__side {
          height: calc(34px * var(--screen-ui-scale));
        }

        .screen-canvas-header__side {
          position: relative;
          min-width: 0;
          height: calc(42px * var(--screen-ui-scale));
        }

        .screen-canvas-header__rail {
          position: absolute;
          left: auto;
          right: 0;
          top: 50%;
          width: min(58%, calc(460px * var(--screen-ui-scale)));
          height: calc(16px * var(--screen-ui-scale));
          opacity: 0.46;
          transform: translateY(-50%);
          background:
            linear-gradient(90deg, transparent, rgba(103, 232, 249, 0.34)),
            linear-gradient(180deg, rgba(103, 232, 249, 0.12), transparent 46%);
          clip-path: polygon(0 42%, 78% 42%, 84% 0, 100% 0, 94% 100%, 0 100%);
          box-shadow: 0 0 calc(9px * var(--screen-ui-scale)) rgba(34, 211, 238, 0.09);
        }

        .screen-canvas-header__rail::after {
          content: '';
          position: absolute;
          left: 18%;
          right: calc(18px * var(--screen-ui-scale));
          bottom: calc(2px * var(--screen-ui-scale));
          height: calc(1px * var(--screen-ui-scale));
          background: linear-gradient(90deg, transparent, rgba(125, 211, 252, 0.36), transparent);
        }

        .screen-canvas-header__side--right .screen-canvas-header__rail {
          left: 0;
          right: auto;
          transform: translateY(-50%) scaleX(-1);
        }

        .screen-canvas-title {
          position: relative;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          min-width: calc(300px * var(--screen-ui-scale));
          max-width: calc(600px * var(--screen-ui-scale));
          height: calc(40px * var(--screen-ui-scale));
          padding: 0 calc(46px * var(--screen-ui-scale));
          border: calc(1px * var(--screen-ui-scale)) solid rgba(125, 211, 252, 0.16);
          border-left-color: rgba(125, 211, 252, 0.06);
          border-right-color: rgba(125, 211, 252, 0.06);
          border-radius: calc(2px * var(--screen-ui-scale));
          color: #eafbff;
          font-size: calc(24px * var(--screen-ui-scale));
          font-weight: 800;
          letter-spacing: 0;
          text-shadow:
            0 0 calc(8px * var(--screen-ui-scale)) rgba(103, 232, 249, 0.38),
            0 0 calc(16px * var(--screen-ui-scale)) rgba(37, 99, 235, 0.13);
          background:
            linear-gradient(90deg, rgba(8, 47, 73, 0.02), rgba(34, 211, 238, 0.12) 24%, rgba(59, 130, 246, 0.1) 50%, rgba(34, 211, 238, 0.12) 76%, rgba(8, 47, 73, 0.02)),
            linear-gradient(180deg, rgba(255, 255, 255, 0.06), rgba(2, 6, 23, 0.04));
          box-shadow:
            inset 0 calc(1px * var(--screen-ui-scale)) 0 rgba(255, 255, 255, 0.06),
            0 0 calc(18px * var(--screen-ui-scale)) rgba(34, 211, 238, 0.08);
        }

        .screen-canvas-title span {
          position: relative;
          z-index: 1;
          display: inline-flex;
          align-items: center;
        }

        .screen-canvas-title::before,
        .screen-canvas-title::after {
          content: '';
          position: absolute;
          pointer-events: none;
        }

        .screen-canvas-title::before {
          left: calc(28px * var(--screen-ui-scale));
          right: calc(28px * var(--screen-ui-scale));
          bottom: calc(4px * var(--screen-ui-scale));
          height: calc(1px * var(--screen-ui-scale));
          background: linear-gradient(90deg, transparent, rgba(103, 232, 249, 0.5), transparent);
          box-shadow: 0 0 calc(8px * var(--screen-ui-scale)) rgba(34, 211, 238, 0.14);
        }

        .screen-canvas-title::after {
          left: 50%;
          top: calc(-1px * var(--screen-ui-scale));
          width: calc(76px * var(--screen-ui-scale));
          height: calc(2px * var(--screen-ui-scale));
          border-radius: 999px;
          background: linear-gradient(90deg, transparent, rgba(224, 251, 255, 0.62), transparent);
          transform: translateX(-50%);
          box-shadow: 0 0 calc(10px * var(--screen-ui-scale)) rgba(34, 211, 238, 0.18);
        }

        .screen-canvas-title span::before,
        .screen-canvas-title span::after {
          content: '';
          display: inline-block;
          width: calc(18px * var(--screen-ui-scale));
          height: calc(1px * var(--screen-ui-scale));
          background: rgba(103, 232, 249, 0.44);
          box-shadow: 0 0 calc(6px * var(--screen-ui-scale)) rgba(34, 211, 238, 0.14);
        }

        .screen-canvas-title span::before {
          margin-right: calc(14px * var(--screen-ui-scale));
        }

        .screen-canvas-title span::after {
          margin-left: calc(14px * var(--screen-ui-scale));
        }

        .screen-canvas-clock {
          position: absolute;
          right: 0;
          top: 50%;
          min-width: calc(230px * var(--screen-ui-scale));
          margin-left: auto;
          border: 1px solid rgba(103, 232, 249, 0.2);
          border-radius: calc(4px * var(--screen-ui-scale));
          background: linear-gradient(90deg, rgba(8, 47, 73, 0.14), rgba(8, 145, 178, 0.18));
          color: rgba(224, 251, 255, 0.82);
          padding: calc(4px * var(--screen-ui-scale)) calc(10px * var(--screen-ui-scale));
          font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
          font-size: calc(14px * var(--screen-ui-scale));
          font-weight: 700;
          letter-spacing: 0;
          text-align: center;
          transform: translateY(-50%);
          box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
        }

        .screen-canvas-empty {
          position: absolute;
          inset: 0;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: calc(12px * var(--screen-ui-scale));
          color: rgba(224, 251, 255, 0.46);
          font-size: calc(21px * var(--screen-ui-scale));
          font-weight: 600;
        }

        .screen-canvas-empty__icon {
          position: relative;
          width: calc(72px * var(--screen-ui-scale));
          height: calc(72px * var(--screen-ui-scale));
          border: 1px solid rgba(125, 211, 252, 0.16);
          border-radius: calc(18px * var(--screen-ui-scale));
          background:
            linear-gradient(135deg, rgba(34, 211, 238, 0.09), transparent),
            rgba(2, 6, 23, 0.2);
          box-shadow: 0 0 28px rgba(34, 211, 238, 0.08);
        }

        .screen-canvas-empty__icon::before,
        .screen-canvas-empty__icon::after {
          content: '';
          position: absolute;
          left: 50%;
          top: 50%;
          border-radius: 999px;
          background: rgba(186, 230, 253, 0.42);
          transform: translate(-50%, -50%);
        }

        .screen-canvas-empty__icon::before {
          width: calc(26px * var(--screen-ui-scale));
          height: calc(2px * var(--screen-ui-scale));
        }

        .screen-canvas-empty__icon::after {
          width: calc(2px * var(--screen-ui-scale));
          height: calc(26px * var(--screen-ui-scale));
        }

        .screen-canvas-empty__title {
          text-shadow: 0 0 18px rgba(34, 211, 238, 0.12);
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

        .screen-rnd-node--selected {
          z-index: 100 !important;
        }

        .screen-rnd-node--interacting {
          z-index: 10000 !important;
          filter: drop-shadow(0 18px 34px rgba(14, 165, 233, 0.26));
        }

        .screen-rnd-handle {
          z-index: 8;
          opacity: 0.64;
          border: 1px solid rgba(186, 230, 253, 0.58);
          border-radius: calc(2px * var(--screen-ui-scale));
          background: rgba(6, 24, 50, 0.56);
          box-shadow: 0 0 5px rgba(34, 211, 238, 0.14);
          transition:
            background 120ms ease,
            border-color 120ms ease,
            opacity 120ms ease;
        }

        .screen-rnd-handle--n,
        .screen-rnd-handle--s {
          height: calc(8px * var(--screen-ui-scale)) !important;
          width: calc(72px * var(--screen-ui-scale)) !important;
          left: calc(50% - (36px * var(--screen-ui-scale))) !important;
        }

        .screen-rnd-handle--e,
        .screen-rnd-handle--w {
          height: calc(72px * var(--screen-ui-scale)) !important;
          width: calc(8px * var(--screen-ui-scale)) !important;
          top: calc(50% - (36px * var(--screen-ui-scale))) !important;
        }

        .screen-rnd-handle--nw,
        .screen-rnd-handle--ne,
        .screen-rnd-handle--sw,
        .screen-rnd-handle--se {
          width: calc(10px * var(--screen-ui-scale)) !important;
          height: calc(10px * var(--screen-ui-scale)) !important;
        }

        .screen-rnd-node--selected:hover .screen-rnd-handle,
        .screen-rnd-node--interacting .screen-rnd-handle {
          opacity: 0.9;
          border-color: rgba(186, 230, 253, 0.78);
          background: rgba(6, 24, 50, 0.72);
        }

        .screen-widget-frame {
          position: relative;
          display: flex;
          height: 100%;
          min-height: 0;
          flex-direction: column;
          overflow: hidden;
          border: 1px solid rgba(125, 211, 252, 0.22);
          border-radius: calc(8px * var(--screen-widget-ui-scale));
          background:
            linear-gradient(180deg, rgba(8, 31, 52, 0.78), rgba(3, 13, 29, 0.68)),
            rgba(4, 18, 36, 0.62);
          box-shadow:
            0 14px 30px rgba(0, 10, 28, 0.18),
            inset 0 1px 0 rgba(226, 251, 255, 0.08),
            inset 0 -24px 42px rgba(14, 116, 144, 0.05);
          backdrop-filter: blur(14px) saturate(112%);
          contain: layout paint style;
        }

        .screen-widget-frame::before {
          content: '';
          position: absolute;
          inset: 0;
          pointer-events: none;
          background:
            linear-gradient(90deg, rgba(103, 232, 249, 0.06), transparent 22%, transparent 78%, rgba(103, 232, 249, 0.05)),
            linear-gradient(180deg, rgba(255, 255, 255, 0.03), transparent 38%);
          opacity: 0.55;
        }

        .screen-widget-frame--selected {
          border-color: rgba(125, 211, 252, 0.5);
          box-shadow:
            0 0 0 1px rgba(125, 211, 252, 0.1),
            0 16px 40px rgba(0, 10, 28, 0.28),
            inset 0 1px 0 rgba(226, 251, 255, 0.14);
        }

        .screen-widget-frame__corners {
          display: none;
        }

        .screen-widget-frame__header {
          position: relative;
          z-index: 1;
          display: flex;
          height: calc(34px * var(--screen-widget-ui-scale));
          flex-shrink: 0;
          align-items: center;
          justify-content: space-between;
          padding: 0 calc(10px * var(--screen-widget-ui-scale));
          border-bottom: 1px solid rgba(109, 226, 255, 0.12);
          background:
            linear-gradient(90deg, rgba(56, 189, 248, 0.09), transparent 72%),
            rgba(2, 6, 23, 0.1);
          cursor: move;
          user-select: none;
        }

        .screen-widget-frame__title {
          min-width: 0;
          width: 100%;
          overflow: hidden;
          padding-right: 0;
          text-overflow: ellipsis;
          white-space: nowrap;
          color: #eafbff;
          font-size: calc(14px * var(--screen-widget-ui-scale));
          font-weight: 700;
          letter-spacing: 0;
          text-shadow: 0 0 8px rgba(125, 211, 252, 0.14);
        }

        .screen-widget-frame:hover .screen-widget-frame__title,
        .screen-widget-frame--selected .screen-widget-frame__title {
          padding-right: calc(26px * var(--screen-widget-ui-scale));
        }

        .screen-widget-frame__signal {
          position: absolute;
          right: calc(8px * var(--screen-widget-ui-scale));
          top: 50%;
          width: calc(18px * var(--screen-widget-ui-scale));
          height: calc(1px * var(--screen-widget-ui-scale));
          border-radius: 999px;
          opacity: 0.48;
          background: linear-gradient(90deg, transparent, rgba(103, 232, 249, 0.34));
          box-shadow: 0 0 calc(5px * var(--screen-widget-ui-scale)) rgba(54, 231, 255, 0.1);
          transform: translateY(-50%);
        }

        .screen-widget-frame--kpi .screen-widget-frame__signal,
        .screen-widget-frame--gauge .screen-widget-frame__signal {
          width: calc(16px * var(--screen-widget-ui-scale));
        }

        .screen-widget-frame__body {
          position: relative;
          z-index: 1;
          min-height: 0;
          flex: 1;
          padding: calc(9px * var(--screen-widget-ui-scale));
        }

        .screen-widget-frame--kpi .screen-widget-frame__body,
        .screen-widget-frame--gauge .screen-widget-frame__body {
          padding: calc(8px * var(--screen-widget-ui-scale)) calc(10px * var(--screen-widget-ui-scale)) calc(10px * var(--screen-widget-ui-scale));
        }

        .screen-widget-frame__actions {
          position: absolute;
          right: calc(3px * var(--screen-widget-ui-scale));
          top: calc(3px * var(--screen-widget-ui-scale));
          z-index: 4;
          opacity: 0;
          pointer-events: none;
          transform: translateY(calc(-2px * var(--screen-widget-ui-scale)));
          transition:
            opacity 120ms ease,
            transform 120ms ease;
        }

        .screen-widget-frame:hover .screen-widget-frame__actions,
        .screen-widget-frame--selected .screen-widget-frame__actions {
          opacity: 1;
          pointer-events: auto;
          transform: translateY(0);
        }

        .screen-widget-frame__action {
          display: inline-flex;
          width: calc(22px * var(--screen-widget-ui-scale));
          height: calc(22px * var(--screen-widget-ui-scale));
          cursor: pointer;
          align-items: center;
          justify-content: center;
          border: 1px solid rgba(148, 163, 184, 0.18);
          border-radius: 999px;
          background: rgba(2, 10, 24, 0.38);
          color: rgba(224, 251, 255, 0.64);
          padding: 0;
          font-size: calc(12px * var(--screen-widget-ui-scale));
          line-height: 1;
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.14);
          backdrop-filter: blur(8px);
          transition:
            border-color 120ms ease,
            background 120ms ease,
            color 120ms ease;
        }

        .screen-widget-frame__action:hover {
          border-color: rgba(125, 211, 252, 0.46);
          background: rgba(8, 29, 54, 0.72);
          color: rgba(255, 255, 255, 0.9);
        }

        .screen-widget-frame-actions-menu .ant-dropdown-menu {
          min-width: 108px;
          padding: 4px;
          border-radius: 8px;
          box-shadow: 0 8px 24px rgba(15, 23, 42, 0.16);
        }

        .screen-widget-frame-actions-menu .ant-dropdown-menu-item {
          min-height: 30px;
          padding: 5px 9px !important;
          border-radius: 5px;
          font-size: 12px;
          line-height: 20px;
        }

        .screen-widget-frame-actions-menu .ant-dropdown-menu-item-icon {
          font-size: 12px !important;
        }

        .screen-widget-frame__action-label {
          position: absolute;
          width: 1px;
          height: 1px;
          overflow: hidden;
          clip: rect(0, 0, 0, 0);
          white-space: nowrap;
        }

        .screen-tech-canvas .ant-empty-description {
          color: rgba(186, 230, 253, 0.68) !important;
        }

        .screen-tech-canvas .ant-spin-dot-item {
          background-color: #67e8f9;
        }

        .screen-tech-canvas .ant-table-wrapper,
        .screen-tech-canvas .ant-table,
        .screen-tech-canvas .ant-table-container,
        .screen-tech-canvas .ant-table-content,
        .screen-tech-canvas .ant-table-body {
          color: rgba(224, 251, 255, 0.82) !important;
          background: transparent !important;
        }

        .screen-tech-canvas .ant-table-thead > tr > th {
          border-bottom: 1px solid rgba(103, 232, 249, 0.18) !important;
          background: linear-gradient(180deg, rgba(20, 82, 126, 0.88), rgba(9, 37, 72, 0.82)) !important;
          color: #dffbff !important;
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
          border-bottom: 1px solid rgba(103, 232, 249, 0.12) !important;
          background: rgba(3, 16, 36, 0.46) !important;
          color: rgba(224, 251, 255, 0.78) !important;
          font-size: var(--ops-screen-table-body-font-size, calc(20px * var(--screen-widget-ui-scale))) !important;
          line-height: var(--ops-screen-table-line-height, calc(30px * var(--screen-widget-ui-scale))) !important;
          padding: var(--ops-screen-table-cell-padding-y, calc(12px * var(--screen-widget-ui-scale))) var(--ops-screen-table-cell-padding-x, calc(18px * var(--screen-widget-ui-scale))) !important;
        }

        .screen-tech-canvas .ant-table-tbody > tr:nth-child(even) > td {
          background: rgba(11, 38, 72, 0.44) !important;
        }

        .screen-tech-canvas .ant-table-tbody > tr.ant-table-row:hover > td,
        .screen-tech-canvas .ant-table-tbody > tr > td.ant-table-cell-row-hover {
          background: rgba(34, 139, 206, 0.32) !important;
        }

        .screen-tech-canvas .ant-table-placeholder,
        .screen-tech-canvas .ant-table-placeholder:hover > td {
          background: transparent !important;
        }

        .screen-tech-canvas .ant-pagination,
        .screen-tech-canvas .ant-pagination-total-text,
        .screen-tech-canvas .ant-pagination-options {
          color: rgba(186, 230, 253, 0.72) !important;
          font-size: var(--ops-screen-table-pagination-font-size, var(--ops-screen-table-body-font-size, calc(18px * var(--screen-widget-ui-scale)))) !important;
        }

        .screen-tech-canvas .ant-pagination-item,
        .screen-tech-canvas .ant-pagination-prev .ant-pagination-item-link,
        .screen-tech-canvas .ant-pagination-next .ant-pagination-item-link {
          border-color: rgba(103, 232, 249, 0.26) !important;
          background: rgba(6, 24, 50, 0.74) !important;
        }

        .screen-tech-canvas .ant-pagination-item a,
        .screen-tech-canvas .ant-pagination-prev button,
        .screen-tech-canvas .ant-pagination-next button {
          color: rgba(224, 251, 255, 0.78) !important;
        }

        .screen-tech-canvas .ant-pagination-item-active {
          border-color: rgba(103, 232, 249, 0.7) !important;
          background: rgba(34, 211, 238, 0.22) !important;
        }

        .screen-tech-canvas .ant-table-row-expand-icon {
          border-color: rgba(103, 232, 249, 0.38) !important;
          background: rgba(6, 24, 50, 0.84) !important;
          color: rgba(224, 251, 255, 0.76) !important;
        }

        .screen-tech-canvas .ant-table-row-expand-icon::before,
        .screen-tech-canvas .ant-table-row-expand-icon::after {
          background: rgba(103, 232, 249, 0.78) !important;
        }

        .screen-tech-canvas .ant-select-selector {
          border-color: rgba(103, 232, 249, 0.26) !important;
          background: rgba(6, 24, 50, 0.82) !important;
          color: rgba(224, 251, 255, 0.8) !important;
        }
      `}</style>
    </div>
  );
};

export default ScreenCanvas;
