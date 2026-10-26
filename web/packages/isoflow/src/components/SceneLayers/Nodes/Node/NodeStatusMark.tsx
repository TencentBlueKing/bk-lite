import React from 'react';
import { Box } from '@mui/material';
import { PROJECTED_TILE_SIZE } from 'src/config';
import { useDiagramVisual } from 'src/diagramOverlay/context';
import { HIGHLIGHT_STROKE } from 'src/diagramOverlay/colors';

interface Props {
  nodeId: string;
  order: number;
  // outline is painted before the icon so the icon covers it; marks after it.
  part?: 'outline' | 'marks';
}

// Highlight stroke is 5px. Expand the outline hit box by half of that so the
// stroke edge still counts as the icon.
const STATUS_OUTLINE_HIT_PAD = 3;

export const NodeStatusMark = ({ nodeId, order, part = 'marks' }: Props) => {
  const visual = useDiagramVisual();
  // Edit mode may carry a name plate on nodeStatus. Alarm marks stay view-only.
  const status =
    visual.editorMode === 'EXPLORABLE_READONLY'
      ? visual.nodeStatus?.[nodeId]
      : undefined;
  const binding = visual.nodeBinding?.[nodeId];
  const highlighted =
    visual.editorMode === 'EXPLORABLE_READONLY' &&
    visual.highlightedItemId === nodeId;
  const showUnbound = Boolean(binding?.unbound);

  if (!status && !highlighted && !showUnbound) return null;

  const width = PROJECTED_TILE_SIZE.width;
  const height = PROJECTED_TILE_SIZE.height;
  const points = `${width / 2},0 ${width},${height / 2} ${width / 2},${height} 0,${height / 2}`;
  if (part === 'outline') {
    if (!highlighted && !showUnbound) return null;

    return (
      <Box
        aria-hidden
        sx={{
          position: 'absolute',
          left: -width / 2,
          top: -height,
          width,
          height,
          pointerEvents: 'none'
        }}
      >
        <svg
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          style={{ pointerEvents: 'none', overflow: 'visible' }}
        >
          {showUnbound && (
            <>
              <polygon
                data-binding-unbound-diamond="fill"
                points={points}
                fill="rgba(255,255,255,0.15)"
                stroke="#ffffff"
                strokeOpacity={0.22}
                strokeWidth={1.5}
                strokeLinejoin="round"
              />
              <polygon
                data-binding-unbound-diamond="dash"
                points={points}
                fill="none"
                stroke="#94A3B8"
                strokeOpacity={0.55}
                strokeWidth={1}
                strokeDasharray="6 4"
                strokeLinejoin="round"
              />
            </>
          )}
          {highlighted && (
            <polygon
              points={points}
              fill="none"
              stroke={HIGHLIGHT_STROKE}
              strokeWidth={5}
              strokeLinejoin="round"
            />
          )}
        </svg>
      </Box>
    );
  }

  return (
    <Box
      aria-hidden
      data-node-status={status?.level ?? ''}
      data-node-highlight={highlighted ? 'true' : 'false'}
      data-binding-unbound={showUnbound ? 'true' : 'false'}
      data-icon-hit={nodeId}
      data-icon-order={order}
      data-icon-pad={STATUS_OUTLINE_HIT_PAD}
      sx={{
        position: 'absolute',
        left: -width / 2,
        top: -height,
        width,
        height,
        pointerEvents: 'none'
      }}
    />
  );
};
