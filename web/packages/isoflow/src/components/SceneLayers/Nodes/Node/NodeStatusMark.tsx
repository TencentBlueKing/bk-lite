import React from 'react';
import { Box } from '@mui/material';
import { PROJECTED_TILE_SIZE } from 'src/config';
import { useDiagramVisual } from 'src/diagramOverlay/context';
import {
  HIGHLIGHT_STROKE,
  NODE_TILE_FLOOR_COLOR
} from 'src/diagramOverlay/colors';

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
  const level = status?.level;
  const floorColor = level ? NODE_TILE_FLOOR_COLOR[level] : undefined;
  // Only warning / critical have a floor color; other levels get no glow.
  const tileGlow = Boolean(floorColor);
  const glowId = `node-tile-glow-${nodeId}`;
  const liftId = `${glowId}-lift`;
  const points = `${width / 2},0 ${width},${height / 2} ${width / 2},${height} 0,${height / 2}`;
  // Screen-space circle under the icon. Slightly past the cell's short axis;
  // the rim fades so the overflow stays pale.
  const glowRadius = height * 0.64;
  if (part === 'outline') {
    if (!highlighted && !showUnbound && !tileGlow) return null;

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
          {tileGlow && floorColor && level ? (
            <>
              <defs>
                {/* Soft lift only — too much white muddies the status color on light grid. */}
                <radialGradient id={liftId} cx="50%" cy="50%" r="50%">
                  <stop offset="0%" stopColor="#ffffff" stopOpacity="0.28" />
                  <stop offset="62%" stopColor="#ffffff" stopOpacity="0.08" />
                  <stop offset="100%" stopColor="#ffffff" stopOpacity="0" />
                </radialGradient>
                <radialGradient id={glowId} cx="50%" cy="50%" r="50%">
                  <stop offset="0%" stopColor={floorColor} stopOpacity="0.62" />
                  <stop offset="42%" stopColor={floorColor} stopOpacity="0.32" />
                  <stop offset="74%" stopColor={floorColor} stopOpacity="0.12" />
                  <stop offset="100%" stopColor={floorColor} stopOpacity="0" />
                </radialGradient>
              </defs>
              <ellipse
                cx={width / 2}
                cy={height / 2}
                rx={glowRadius}
                ry={glowRadius}
                fill={`url(#${liftId})`}
              />
              <ellipse
                data-node-glow={level}
                cx={width / 2}
                cy={height / 2}
                rx={glowRadius}
                ry={glowRadius}
                fill={`url(#${glowId})`}
              />
            </>
          ) : null}
          {showUnbound && (
            <>
              <polygon
                data-binding-unbound-diamond="fill"
                points={points}
                fill="rgba(255,255,255,0.15)"
                stroke="#ffffff"
                strokeOpacity={0.9}
                strokeWidth={4}
                strokeLinejoin="round"
              />
              <polygon
                data-binding-unbound-diamond="dash"
                points={points}
                fill="none"
                stroke="#475569"
                strokeWidth={2}
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
