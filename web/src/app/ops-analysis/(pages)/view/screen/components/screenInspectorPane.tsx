'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';

export const SCREEN_INSPECTOR_DEFAULT_WIDTH = 400;
const SCREEN_INSPECTOR_MIN_WIDTH = 320;
const SCREEN_INSPECTOR_MAX_WIDTH = 640;

const clampWidth = (value: number) =>
  Math.min(
    SCREEN_INSPECTOR_MAX_WIDTH,
    Math.max(SCREEN_INSPECTOR_MIN_WIDTH, value),
  );

export const ScreenInspectorPane: React.FC<{
  label: string;
  children: React.ReactNode;
}> = ({ label, children }) => {
  const [width, setWidth] = useState(SCREEN_INSPECTOR_DEFAULT_WIDTH);
  const [dragging, setDragging] = useState(false);
  const dragRef = useRef<{ startX: number; startWidth: number } | null>(null);

  const restoreDragCursor = useCallback(() => {
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  }, []);

  const onMouseMove = useCallback((event: MouseEvent) => {
    if (!dragRef.current) return;
    setWidth(
      clampWidth(
        dragRef.current.startWidth - (event.clientX - dragRef.current.startX),
      ),
    );
  }, []);

  const onMouseUp = useCallback(() => {
    dragRef.current = null;
    setDragging(false);
    restoreDragCursor();
    document.removeEventListener('mousemove', onMouseMove);
    document.removeEventListener('mouseup', onMouseUp);
  }, [onMouseMove, restoreDragCursor]);

  const onMouseDown = (event: React.MouseEvent) => {
    event.preventDefault();
    dragRef.current = { startX: event.clientX, startWidth: width };
    setDragging(true);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  };

  useEffect(
    () => () => {
      restoreDragCursor();
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
    },
    [onMouseMove, onMouseUp, restoreDragCursor],
  );

  return (
    <aside
      data-screen-inspector=""
      className={`relative flex h-full min-h-0 shrink-0 flex-col border-l border-(--color-border-1) bg-(--color-bg-1) ${
        dragging ? 'select-none' : ''
      }`}
      style={{ width }}
    >
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label={label}
        aria-valuemin={SCREEN_INSPECTOR_MIN_WIDTH}
        aria-valuemax={SCREEN_INSPECTOR_MAX_WIDTH}
        aria-valuenow={width}
        className="group absolute top-0 -left-0.5 z-20 h-full w-1.5 cursor-col-resize"
        onMouseDown={onMouseDown}
      >
        <span
          aria-hidden
          className={`absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-(--color-border-2) group-hover:bg-(--color-primary) ${
            dragging ? 'bg-(--color-primary)' : ''
          }`}
        />
      </div>
      {children}
    </aside>
  );
};
