"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { Rnd } from "react-rnd";
import { useTranslation } from "@/utils/i18n";
import type { DatasourceItem } from "@/app/ops-analysis/types/dataSource";
import type {
  ScreenViewSets,
  ScreenWidgetItem,
} from "@/app/ops-analysis/types/screen";
import {
  formatScreenClock,
  getScreenRndNodeClassName,
} from "../utils/classNames";
import ScreenWidgetRenderer from "./screenWidgetRenderer";

const RndComponent = Rnd as unknown as React.ComponentType<any>;

interface ScreenCanvasProps {
  viewSets: ScreenViewSets;
  fullscreen?: boolean;
  editMode?: boolean;
  selectedItemId?: string | null;
  refreshVersion?: number;
  screenId?: string | number;
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
    if (!viewSets.decorations.showClock) return;
    const timer = window.setInterval(() => {
      setCurrentTime(new Date());
    }, 1000);

    return () => window.clearInterval(timer);
  }, [viewSets.decorations.showClock]);

  const canvasSize = useMemo(() => {
    const padding = fullscreen ? 32 : 32;
    const availableWidth = Math.max(containerSize.width - padding, 0);
    const availableHeight = Math.max(containerSize.height - padding, 0);
    if (!availableWidth || !availableHeight) {
      return null;
    }

    const ratio = width / height;
    const availableRatio = availableWidth / availableHeight;
    if (availableRatio > ratio) {
      return {
        width: Math.floor(availableHeight * ratio),
        height: Math.floor(availableHeight),
      };
    }

    return {
      width: Math.floor(availableWidth),
      height: Math.floor(availableWidth / ratio),
    };
  }, [containerSize.height, containerSize.width, height, width]);

  const scale = canvasSize ? canvasSize.width / width : 1;
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
        dataSourceResolver={resolveDataSource}
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
        style={
          canvasSize
            ? { width: canvasSize.width, height: canvasSize.height }
            : { width: "100%", aspectRatio: `${width} / ${height}` }
        }
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
          }}
        >
          {editMode && !fullscreen && (
            <>
              <div className="screen-canvas-ruler screen-canvas-ruler--top" />
              <div className="screen-canvas-ruler screen-canvas-ruler--left" />
            </>
          )}
          {editMode && !fullscreen && (
            <div className="screen-canvas-resolution">
              {width} × {height}
            </div>
          )}
          {(viewSets.decorations.showTitle ||
            viewSets.decorations.showClock) && (
            <div className="screen-canvas-header pointer-events-none absolute left-0 right-0 top-14 z-20">
              <div className="screen-canvas-header__side screen-canvas-header__side--left">
                <div className="screen-canvas-header__rail" />
              </div>
              <div className="screen-canvas-title">
                <span>
                  {viewSets.decorations.title ||
                    t("opsAnalysis.screen.defaultTitle")}
                </span>
              </div>
              <div className="screen-canvas-header__side screen-canvas-header__side--right">
                <div className="screen-canvas-header__rail" />
                {viewSets.decorations.showClock && (
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
            radial-gradient(circle at 50% -10%, rgba(34, 211, 238, 0.16), transparent 34%),
            radial-gradient(circle at 12% 18%, rgba(59, 130, 246, 0.12), transparent 26%),
            linear-gradient(180deg, #0b1220 0%, #050914 100%);
        }

        .screen-canvas-workbench--preview {
          background: #020617;
        }

        .screen-canvas-stage {
          position: relative;
          overflow: hidden;
          border-radius: 18px;
          background: #020617;
          box-shadow:
            0 24px 70px rgba(0, 0, 0, 0.42),
            0 0 0 1px rgba(148, 163, 184, 0.12);
        }

        .screen-tech-canvas {
          position: absolute;
          left: 0;
          top: 0;
          transform-origin: left top;
          color: #eafbff;
          border: 1px solid rgba(56, 189, 248, 0.2);
          box-shadow: inset 0 0 120px rgba(14, 165, 233, 0.08);
          background:
            radial-gradient(circle at 50% 8%, rgba(34, 211, 238, 0.16), transparent 24%),
            radial-gradient(circle at 14% 30%, rgba(59, 130, 246, 0.12), transparent 24%),
            linear-gradient(rgba(56, 189, 248, 0.035) 1px, transparent 1px),
            linear-gradient(90deg, rgba(56, 189, 248, 0.035) 1px, transparent 1px),
            linear-gradient(135deg, #031022 0%, #082541 48%, #020814 100%);
          background-size: auto, auto, 96px 96px, 96px 96px, auto;
        }

        .screen-tech-canvas::before {
          content: '';
          position: absolute;
          left: 120px;
          right: 120px;
          top: 118px;
          height: 1px;
          pointer-events: none;
          background: linear-gradient(90deg, transparent, rgba(103, 232, 249, 0.55), transparent);
          box-shadow: 0 0 18px rgba(34, 211, 238, 0.28);
        }

        .screen-tech-canvas--editing {
          outline: 2px solid rgba(56, 189, 248, 0.26);
          outline-offset: -2px;
        }

        .screen-canvas-ruler {
          position: absolute;
          z-index: 30;
          pointer-events: none;
          background: rgba(2, 6, 23, 0.42);
        }

        .screen-canvas-ruler--top {
          left: 0;
          right: 0;
          top: 0;
          height: 18px;
          border-bottom: 1px solid rgba(103, 232, 249, 0.12);
          background-image: repeating-linear-gradient(
            90deg,
            rgba(103, 232, 249, 0.32) 0 1px,
            transparent 1px 120px
          );
        }

        .screen-canvas-ruler--left {
          bottom: 0;
          left: 0;
          top: 0;
          width: 18px;
          border-right: 1px solid rgba(103, 232, 249, 0.12);
          background-image: repeating-linear-gradient(
            180deg,
            rgba(103, 232, 249, 0.32) 0 1px,
            transparent 1px 120px
          );
        }

        .screen-canvas-resolution {
          position: absolute;
          left: 44px;
          top: 42px;
          z-index: 31;
          border: 1px solid rgba(125, 211, 252, 0.22);
          border-radius: 8px;
          background: rgba(4, 16, 34, 0.68);
          color: rgba(224, 251, 255, 0.72);
          padding: 10px 14px;
          font-size: 24px;
          font-weight: 600;
          letter-spacing: 0;
        }

        .screen-canvas-header {
          display: grid;
          grid-template-columns: minmax(720px, 1fr) auto minmax(720px, 1fr);
          align-items: center;
          gap: 44px;
          padding: 0 138px;
        }

        .screen-canvas-header__side {
          position: relative;
          min-width: 0;
          height: 70px;
        }

        .screen-canvas-header__rail {
          position: absolute;
          left: 0;
          right: 0;
          top: 50%;
          height: 44px;
          opacity: 0.92;
          transform: translateY(-50%);
          background:
            linear-gradient(90deg, transparent, rgba(34, 211, 238, 0.26)),
            linear-gradient(180deg, rgba(103, 232, 249, 0.18), transparent 56%);
          clip-path: polygon(0 44%, 86% 44%, 91% 0, 100% 0, 94% 100%, 0 100%);
          border-bottom: 2px solid rgba(103, 232, 249, 0.36);
        }

        .screen-canvas-header__side--right .screen-canvas-header__rail {
          transform: translateY(-50%) scaleX(-1);
        }

        .screen-canvas-title {
          position: relative;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          min-width: 820px;
          height: 92px;
          color: #eafbff;
          font-size: 54px;
          font-weight: 800;
          letter-spacing: 0;
          text-shadow:
            0 0 12px rgba(103, 232, 249, 0.48),
            0 0 30px rgba(37, 99, 235, 0.34);
          background:
            linear-gradient(90deg, transparent 0 8%, rgba(34, 211, 238, 0.28) 22%, rgba(59, 130, 246, 0.18) 50%, rgba(34, 211, 238, 0.28) 78%, transparent 92%),
            linear-gradient(180deg, rgba(255, 255, 255, 0.1), rgba(103, 232, 249, 0.04) 58%, transparent);
          clip-path: polygon(10% 0, 90% 0, 100% 50%, 90% 100%, 10% 100%, 0 50%);
        }

        .screen-canvas-title::before,
        .screen-canvas-title::after {
          content: '';
          position: absolute;
          bottom: -8px;
          width: 180px;
          height: 5px;
          border-radius: 999px;
          background: linear-gradient(90deg, transparent, #67e8f9, transparent);
          box-shadow: 0 0 18px rgba(34, 211, 238, 0.54);
        }

        .screen-canvas-title::before {
          left: 104px;
        }

        .screen-canvas-title::after {
          right: 104px;
        }

        .screen-canvas-clock {
          position: absolute;
          right: 0;
          top: 50%;
          min-width: 460px;
          margin-left: auto;
          border: 1px solid rgba(103, 232, 249, 0.2);
          border-radius: 4px;
          background: linear-gradient(90deg, rgba(8, 47, 73, 0.14), rgba(8, 145, 178, 0.18));
          color: rgba(224, 251, 255, 0.82);
          padding: 14px 22px;
          font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
          font-size: 26px;
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
          gap: 18px;
          color: rgba(224, 251, 255, 0.72);
          font-size: 24px;
          font-weight: 600;
        }

        .screen-canvas-empty__icon {
          width: 112px;
          height: 112px;
          border: 1px solid rgba(125, 211, 252, 0.34);
          border-radius: 28px;
          background:
            linear-gradient(135deg, rgba(34, 211, 238, 0.26), transparent),
            rgba(2, 6, 23, 0.44);
          box-shadow: 0 0 42px rgba(34, 211, 238, 0.16);
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
          opacity: 1;
          border: 1px solid rgba(186, 230, 253, 0.92);
          border-radius: 4px;
          background: rgba(6, 24, 50, 0.94);
          box-shadow: 0 0 8px rgba(34, 211, 238, 0.22);
          transition: opacity 120ms ease;
        }

        .screen-rnd-handle--n,
        .screen-rnd-handle--s {
          height: 14px !important;
          width: 100px !important;
          left: calc(50% - 50px) !important;
        }

        .screen-rnd-handle--e,
        .screen-rnd-handle--w {
          height: 100px !important;
          width: 14px !important;
          top: calc(50% - 50px) !important;
        }

        .screen-rnd-handle--nw,
        .screen-rnd-handle--ne,
        .screen-rnd-handle--sw,
        .screen-rnd-handle--se {
          width: 18px !important;
          height: 18px !important;
        }

        .screen-widget-frame {
          position: relative;
          display: flex;
          height: 100%;
          min-height: 0;
          flex-direction: column;
          overflow: hidden;
          border: 1px solid rgba(125, 211, 252, 0.22);
          border-radius: 10px;
          background:
            linear-gradient(180deg, rgba(8, 31, 52, 0.78), rgba(3, 13, 29, 0.68)),
            rgba(4, 18, 36, 0.62);
          box-shadow:
            0 28px 60px rgba(0, 10, 28, 0.26),
            inset 0 1px 0 rgba(226, 251, 255, 0.12),
            inset 0 -30px 58px rgba(14, 116, 144, 0.07);
          backdrop-filter: blur(18px) saturate(118%);
          contain: layout paint style;
        }

        .screen-widget-frame::before {
          content: '';
          position: absolute;
          inset: 0;
          pointer-events: none;
          background:
            linear-gradient(90deg, rgba(103, 232, 249, 0.12), transparent 22%, transparent 78%, rgba(103, 232, 249, 0.08)),
            linear-gradient(180deg, rgba(255, 255, 255, 0.045), transparent 38%);
          opacity: 0.82;
        }

        .screen-widget-frame--selected {
          border-color: rgba(125, 211, 252, 0.5);
          box-shadow:
            0 0 0 1px rgba(125, 211, 252, 0.1),
            0 16px 40px rgba(0, 10, 28, 0.28),
            inset 0 1px 0 rgba(226, 251, 255, 0.14);
        }

        .screen-widget-frame__corners::before,
        .screen-widget-frame__corners::after {
          content: '';
          position: absolute;
          z-index: 2;
          width: 28px;
          height: 28px;
          pointer-events: none;
          border-color: rgba(125, 235, 255, 0.16);
          opacity: 0.46;
        }

        .screen-widget-frame__corners::before {
          left: 10px;
          top: 10px;
          border-left: 1px solid;
          border-top: 1px solid;
        }

        .screen-widget-frame__corners::after {
          right: 10px;
          bottom: 10px;
          border-right: 1px solid;
          border-bottom: 1px solid;
        }

        .screen-widget-frame__header {
          position: relative;
          z-index: 1;
          display: flex;
          height: 82px;
          flex-shrink: 0;
          align-items: center;
          justify-content: space-between;
          padding: 0 34px;
          border-bottom: 1px solid rgba(109, 226, 255, 0.12);
          background:
            linear-gradient(90deg, rgba(56, 189, 248, 0.13), transparent 72%),
            rgba(2, 6, 23, 0.14);
          cursor: move;
          user-select: none;
        }

        .screen-widget-frame--kpi .screen-widget-frame__header {
          height: 70px;
          padding: 0 24px;
        }

        .screen-widget-frame--gauge .screen-widget-frame__header {
          height: 66px;
          padding: 0 22px;
        }

        .screen-widget-frame__title {
          min-width: 0;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          color: #eafbff;
          font-size: 34px;
          font-weight: 700;
          letter-spacing: 0;
          text-shadow: 0 0 18px rgba(125, 211, 252, 0.22);
        }

        .screen-widget-frame--kpi .screen-widget-frame__title {
          font-size: 26px;
        }

        .screen-widget-frame--gauge .screen-widget-frame__title {
          font-size: 24px;
        }

        .screen-widget-frame__signal {
          width: 116px;
          height: 5px;
          flex-shrink: 0;
          border-radius: 999px;
          background: linear-gradient(90deg, transparent, rgba(103, 232, 249, 0.9));
          box-shadow: 0 0 18px rgba(54, 231, 255, 0.38);
        }

        .screen-widget-frame--kpi .screen-widget-frame__signal,
        .screen-widget-frame--gauge .screen-widget-frame__signal {
          width: 64px;
        }

        .screen-widget-frame__body {
          position: relative;
          z-index: 1;
          min-height: 0;
          flex: 1;
          padding: 30px;
        }

        .screen-widget-frame--kpi .screen-widget-frame__body,
        .screen-widget-frame--gauge .screen-widget-frame__body {
          padding: 20px 24px 22px;
        }

        .screen-widget-frame__actions {
          position: absolute;
          right: 20px;
          top: 16px;
          z-index: 4;
          opacity: 0;
          pointer-events: none;
          transform: translateY(-2px);
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
          width: 46px;
          height: 46px;
          cursor: pointer;
          align-items: center;
          justify-content: center;
          border: 1px solid rgba(148, 163, 184, 0.28);
          border-radius: 999px;
          background: rgba(2, 10, 24, 0.62);
          color: rgba(224, 251, 255, 0.82);
          padding: 0;
          font-size: 24px;
          line-height: 1;
          box-shadow: 0 8px 20px rgba(0, 0, 0, 0.22);
          backdrop-filter: blur(10px);
          transition:
            border-color 120ms ease,
            background 120ms ease,
            color 120ms ease;
        }

        .screen-widget-frame__action:hover {
          border-color: rgba(125, 211, 252, 0.62);
          background: rgba(8, 29, 54, 0.88);
          color: #ffffff;
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
          font-size: 22px !important;
          font-weight: 700 !important;
          line-height: 32px !important;
          padding: 14px 18px !important;
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
          font-size: 20px !important;
          line-height: 30px !important;
          padding: 12px 18px !important;
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
          font-size: 18px !important;
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
