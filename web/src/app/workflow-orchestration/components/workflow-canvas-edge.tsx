'use client';

import { BaseEdge, getBezierPath, getSmoothStepPath, Position, type Edge, type EdgeProps } from '@xyflow/react';
import { useState } from 'react';

type WorkflowEdge = Edge<Record<string, never>, 'workflowCanvas'>;

export function WorkflowCanvasEdge({ id, sourceX, sourceY, targetX, targetY, sourcePosition = Position.Right, targetPosition = Position.Left, selected }: EdgeProps<WorkflowEdge>) {
  const [hovered, setHovered] = useState(false);
  const [path] = targetX <= sourceX
    ? getSmoothStepPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, borderRadius: 16, offset: 40 })
    : getBezierPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition });

  return <g onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}>
    <BaseEdge
      id={id}
      path={path}
      interactionWidth={40}
      style={{
        fill: 'none',
        stroke: selected || hovered ? 'var(--color-text-3)' : 'var(--color-border-3)',
        strokeLinecap: 'round',
        strokeWidth: 2,
      }}
    />
  </g>;
}
