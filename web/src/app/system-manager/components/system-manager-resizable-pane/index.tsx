'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';

interface SystemManagerResizablePaneProps {
  storageKey: string;
  defaultWidth?: number;
  minWidth?: number;
  maxWidth?: number;
  children: React.ReactNode;
}

function clampWidth(value: number, minWidth: number, maxWidth: number) {
  return Math.min(maxWidth, Math.max(minWidth, value));
}

function readStoredWidth(
  storageKey: string,
  fallback: number,
  minWidth: number,
  maxWidth: number,
) {
  if (typeof window === 'undefined') {
    return fallback;
  }
  const parsed = Number(window.localStorage.getItem(storageKey));
  return Number.isFinite(parsed) ? clampWidth(parsed, minWidth, maxWidth) : fallback;
}

export default function SystemManagerResizablePane({
  storageKey,
  defaultWidth = 260,
  minWidth = 200,
  maxWidth = 420,
  children,
}: SystemManagerResizablePaneProps) {
  const [width, setWidth] = useState(defaultWidth);
  const [dragging, setDragging] = useState(false);
  const dragRef = useRef<{ startX: number; startWidth: number } | null>(null);

  useEffect(() => {
    setWidth(readStoredWidth(storageKey, defaultWidth, minWidth, maxWidth));
  }, [defaultWidth, maxWidth, minWidth, storageKey]);

  const onMouseMove = useCallback((event: MouseEvent) => {
    if (!dragRef.current) {
      return;
    }
    setWidth(clampWidth(
      dragRef.current.startWidth + (event.clientX - dragRef.current.startX),
      minWidth,
      maxWidth,
    ));
  }, [maxWidth, minWidth]);

  const restoreDragCursor = useCallback(() => {
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  }, []);

  const onMouseUp = useCallback(() => {
    dragRef.current = null;
    setDragging(false);
    restoreDragCursor();
    document.removeEventListener('mousemove', onMouseMove);
    document.removeEventListener('mouseup', onMouseUp);
    setWidth((currentWidth) => {
      if (typeof window !== 'undefined') {
        window.localStorage.setItem(storageKey, String(currentWidth));
      }
      return currentWidth;
    });
  }, [onMouseMove, restoreDragCursor, storageKey]);

  const onMouseDown = (event: React.MouseEvent) => {
    event.preventDefault();
    dragRef.current = { startX: event.clientX, startWidth: width };
    setDragging(true);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  };

  useEffect(() => () => {
    restoreDragCursor();
    document.removeEventListener('mousemove', onMouseMove);
    document.removeEventListener('mouseup', onMouseUp);
  }, [onMouseMove, onMouseUp, restoreDragCursor]);

  return (
    <div className={`relative flex h-full min-h-0 shrink-0 ${dragging ? 'cursor-col-resize select-none' : ''}`}>
      <div className="h-full min-h-0 overflow-hidden" style={{ width }}>
        {children}
      </div>
      <div
        role="separator"
        aria-orientation="vertical"
        aria-valuemin={minWidth}
        aria-valuemax={maxWidth}
        aria-valuenow={width}
        className="group absolute top-0 -right-0.5 z-10 h-full w-1.5 cursor-col-resize"
        onMouseDown={onMouseDown}
      >
        <span
          aria-hidden
          className={`absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-[var(--color-border-2)] group-hover:bg-[var(--color-primary)] ${
            dragging ? 'bg-[var(--color-primary)]' : ''
          }`}
        />
      </div>
    </div>
  );
}
