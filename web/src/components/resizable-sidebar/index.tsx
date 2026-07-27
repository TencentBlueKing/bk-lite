'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { LeftOutlined, RightOutlined } from '@ant-design/icons';
import { clampWidth } from './clamp';
import styles from './index.module.scss';

export interface ResizableSidebarProps {
  storageKey?: string;
  collapseStorageKey?: string;
  defaultWidth?: number;
  minWidth?: number;
  maxWidth?: number;
  collapsible?: boolean;
  children: React.ReactNode;
}

const readNumber = (key: string, fallback: number): number => {
  if (typeof window === 'undefined') return fallback;
  const raw = window.localStorage.getItem(key);
  const n = raw == null ? NaN : Number(raw);
  return Number.isFinite(n) ? n : fallback;
};

const readBool = (key: string): boolean => {
  if (typeof window === 'undefined') return false;
  return window.localStorage.getItem(key) === '1';
};

const ResizableSidebar: React.FC<ResizableSidebarProps> = ({
  storageKey = 'monitor.objectTree.width',
  collapseStorageKey,
  defaultWidth = 216,
  minWidth = 180,
  maxWidth = 480,
  collapsible = true,
  children,
}) => {
  const [width, setWidth] = useState(defaultWidth);
  const [collapsed, setCollapsed] = useState(false);
  const [dragging, setDragging] = useState(false);
  const dragRef = useRef<{ startX: number; startWidth: number } | null>(null);

  useEffect(() => {
    setWidth(clampWidth(readNumber(storageKey, defaultWidth), minWidth, maxWidth, defaultWidth));
    if (collapseStorageKey) setCollapsed(readBool(collapseStorageKey));
  }, [storageKey, collapseStorageKey, defaultWidth, minWidth, maxWidth]);

  const onMouseMove = useCallback(
    (e: MouseEvent) => {
      if (!dragRef.current) return;
      const next = clampWidth(
        dragRef.current.startWidth + (e.clientX - dragRef.current.startX),
        minWidth,
        maxWidth,
        defaultWidth,
      );
      setWidth(next);
    },
    [minWidth, maxWidth, defaultWidth],
  );

  const onMouseUp = useCallback(() => {
    dragRef.current = null;
    setDragging(false);
    document.removeEventListener('mousemove', onMouseMove);
    document.removeEventListener('mouseup', onMouseUp);
    setWidth(currentWidth => {
      if (typeof window !== 'undefined') {
        window.localStorage.setItem(storageKey, String(currentWidth));
      }
      return currentWidth;
    });
  }, [onMouseMove, storageKey]);

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      dragRef.current = { startX: e.clientX, startWidth: width };
      setDragging(true);
      document.addEventListener('mousemove', onMouseMove);
      document.addEventListener('mouseup', onMouseUp);
    },
    [width, onMouseMove, onMouseUp],
  );

  useEffect(() => {
    return () => {
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
    };
  }, [onMouseMove, onMouseUp]);

  const toggleCollapsed = () => {
    setCollapsed(currentCollapsed => {
      const next = !currentCollapsed;
      if (collapseStorageKey && typeof window !== 'undefined') {
        window.localStorage.setItem(collapseStorageKey, next ? '1' : '0');
      }
      return next;
    });
  };

  return (
    <div
      className={`${styles.wrap} ${dragging ? styles.dragging : ''} ${
        collapsed ? styles.collapsed : ''
      }`}
    >
      <div className={styles.panel} style={{ width: collapsed ? 0 : width }}>
        <div className={styles.inner}>{children}</div>
      </div>
      {!collapsed && <div className={styles.handle} onMouseDown={onMouseDown} />}
      {collapsible && (
        <div className={styles.toggle} onClick={toggleCollapsed}>
          {collapsed ? <RightOutlined /> : <LeftOutlined />}
        </div>
      )}
    </div>
  );
};

export default ResizableSidebar;
