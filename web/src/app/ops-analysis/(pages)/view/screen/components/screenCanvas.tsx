'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Empty } from 'antd';
import { useTranslation } from '@/utils/i18n';
import type { ScreenViewSets } from '@/app/ops-analysis/types/screen';

interface ScreenCanvasProps {
  viewSets: ScreenViewSets;
  fullscreen?: boolean;
}

interface CanvasSize {
  width: number;
  height: number;
}

const ScreenCanvas: React.FC<ScreenCanvasProps> = ({
  viewSets,
  fullscreen = false,
}) => {
  const { t } = useTranslation();
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerSize, setContainerSize] = useState<CanvasSize>({
    width: 0,
    height: 0,
  });
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

  return (
    <div
      ref={containerRef}
      className={`flex h-full min-h-0 w-full items-center justify-center overflow-hidden ${
        fullscreen ? 'bg-slate-950 p-4' : 'bg-[var(--color-bg-2)] p-4'
      }`}
    >
      <div
        className={`relative overflow-hidden border shadow-[0_10px_26px_rgba(15,23,42,0.08)] ${
          fullscreen
            ? 'border-cyan-300/50 bg-slate-900'
            : 'border-[var(--color-border-2)] bg-white'
        }`}
        style={
          canvasSize
            ? { width: canvasSize.width, height: canvasSize.height }
            : { width: '100%', aspectRatio: `${width} / ${height}` }
        }
      >
        <div className="absolute left-3 top-3 z-10 rounded bg-black/55 px-2 py-1 text-xs font-medium text-white">
          {width} × {height}
        </div>
        <div className="flex h-full w-full items-center justify-center p-8">
          <Empty
            description={
              <span className={fullscreen ? 'text-slate-400' : 'text-[var(--color-text-3)]'}>
                {t('opsAnalysis.screen.canvasEmpty')}
              </span>
            }
          />
        </div>
      </div>
    </div>
  );
};

export default ScreenCanvas;
