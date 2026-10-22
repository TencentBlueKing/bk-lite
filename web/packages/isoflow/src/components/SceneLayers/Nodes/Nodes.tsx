import React, { useEffect, useState } from 'react';
import { findDrawnIconId } from 'src/interaction/viewPointer';
import { useUiStateStore } from 'src/stores/uiStateStore';
import { ViewItem } from 'src/types';
import { HoveredIconContext, Node, NodeLabelLayerContext } from './Node/Node';

interface Props {
  nodes: ViewItem[];
}

export const Nodes = ({ nodes }: Props) => {
  const [labelRoot, setLabelRoot] = useState<HTMLDivElement | null>(null);
  const [hoveredIconId, setHoveredIconId] = useState<string | null>(null);
  const rendererEl = useUiStateStore((state) => state.rendererEl);

  useEffect(() => {
    if (!rendererEl) return undefined;

    const onMove = (event: PointerEvent) => {
      const next = findDrawnIconId(rendererEl, {
        x: event.clientX,
        y: event.clientY
      });
      setHoveredIconId((current) => (current === next ? current : next));
    };
    const onLeave = () => setHoveredIconId(null);

    rendererEl.addEventListener('pointermove', onMove);
    rendererEl.addEventListener('pointerleave', onLeave);
    return () => {
      rendererEl.removeEventListener('pointermove', onMove);
      rendererEl.removeEventListener('pointerleave', onLeave);
    };
  }, [rendererEl]);
  // Back first so a nearer plate is portaled later and wins when plates overlap.
  const backToFront = [...nodes].sort(
    (a, b) => b.tile.x + b.tile.y - (a.tile.x + a.tile.y)
  );

  return (
    <HoveredIconContext.Provider value={hoveredIconId}>
    <NodeLabelLayerContext.Provider value={labelRoot}>
      {backToFront.map((node) => {
        return (
          <Node key={node.id} order={-node.tile.x - node.tile.y} node={node} />
        );
      })}
      {/* Plates escape icon z-index. A nearer icon would otherwise cover the plate behind it. */}
      <div
        ref={setLabelRoot}
        data-node-label-layer=""
        style={{
          position: 'absolute',
          zIndex: 1000000,
          left: 0,
          top: 0,
          pointerEvents: 'none'
        }}
      />
    </NodeLabelLayerContext.Provider>
    </HoveredIconContext.Provider>
  );
};
