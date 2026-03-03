'use client';

import React, { useEffect, useRef, CSSProperties } from 'react';
import { useReactFlow } from '@xyflow/react';

interface HelperLinesProps {
  horizontal?: number;
  vertical?: number;
}

const canvasStyle: CSSProperties = {
  position: 'absolute',
  top: 0,
  left: 0,
  width: '100%',
  height: '100%',
  zIndex: 10,
  pointerEvents: 'none',
};

const HelperLines: React.FC<HelperLinesProps> = ({ horizontal, vertical }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const { getViewport } = useReactFlow();

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const viewport = getViewport();
    const { x: viewportX, y: viewportY, zoom } = viewport;

    const dpi = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    
    canvas.width = rect.width * dpi;
    canvas.height = rect.height * dpi;
    
    ctx.scale(dpi, dpi);
    ctx.clearRect(0, 0, rect.width, rect.height);

    ctx.strokeStyle = '#3b82f6';
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);

    if (typeof vertical === 'number') {
      const x = vertical * zoom + viewportX;
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, rect.height);
      ctx.stroke();
    }

    if (typeof horizontal === 'number') {
      const y = horizontal * zoom + viewportY;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(rect.width, y);
      ctx.stroke();
    }
  }, [horizontal, vertical, getViewport]);

  if (typeof horizontal !== 'number' && typeof vertical !== 'number') {
    return null;
  }

  return <canvas ref={canvasRef} style={canvasStyle} />;
};

export default HelperLines;
