'use client';

import { DeleteOutlined } from '@ant-design/icons';
import { BaseEdge, EdgeLabelRenderer, getBezierPath, getSmoothStepPath, Position, type Edge, type EdgeProps } from '@xyflow/react';
import { theme } from 'antd';
import { useState } from 'react';

import { useTranslation } from '@/utils/i18n';
import { WorkflowPermission } from './workflow-permission';

interface WorkflowEdgeData extends Record<string, unknown> {
  readOnly?: boolean;
  onRemove?: (id: string) => void;
}

type WorkflowEdge = Edge<WorkflowEdgeData, 'workflowCanvas'>;

export function WorkflowCanvasEdge({ id, sourceX, sourceY, targetX, targetY, sourcePosition = Position.Right, targetPosition = Position.Left, selected, data }: EdgeProps<WorkflowEdge>) {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const [hovered, setHovered] = useState(false);
  const [deleteHovered, setDeleteHovered] = useState(false);
  const [path, labelX, labelY] = targetX <= sourceX
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
    {selected && !data?.readOnly ? <EdgeLabelRenderer>
      <WorkflowPermission operation="Edit"><button
        type="button"
        aria-label={t('workflowOrchestration.editor.deleteEdge', '删除连线')}
        className="nodrag nopan grid h-7 w-7 place-items-center rounded border border-[var(--color-border-2)] bg-[var(--color-bg)] shadow-[0_1px_3px_-1px_var(--color-border-3)]"
        style={{
          position: 'absolute',
          zIndex: 10,
          transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
          pointerEvents: 'all',
          cursor: 'pointer',
          color: deleteHovered ? token.colorError : token.colorText,
          borderColor: deleteHovered ? token.colorError : undefined,
        }}
        onMouseEnter={() => setDeleteHovered(true)}
        onMouseLeave={() => setDeleteHovered(false)}
        onClick={(event) => {
          event.stopPropagation();
          data?.onRemove?.(id);
        }}
      >
        <DeleteOutlined style={{ color: deleteHovered ? token.colorError : token.colorText }} />
      </button></WorkflowPermission>
    </EdgeLabelRenderer> : null}
  </g>;
}
