import React from 'react';
import { Box } from '@mui/material';
import { useScene } from 'src/hooks/useScene';
import { useDiagramVisual } from 'src/diagramOverlay/context';
import { ALERT_BADGE_TONE } from 'src/diagramOverlay/colors';
import {
  getEdgeLabelScale,
  getRectangleRightVertex,
  RECTANGLE_EDGE_LABEL_OFFSET,
  RECTANGLE_EDGE_LABEL_SIZE
} from 'src/diagramOverlay/rectangleAnchor';
import { getIsoProjectionCss } from 'src/utils';

const GROUND_PROJECTION = getIsoProjectionCss();

/** Warning triangle; the mark is cut out in the label colour. */
const AlertTriangle = ({ fill, mark }: { fill: string; mark: string }) => {
  return (
    <svg
      width={RECTANGLE_EDGE_LABEL_SIZE.icon}
      height={RECTANGLE_EDGE_LABEL_SIZE.icon * (13 / 14)}
      viewBox="0 0 14 13"
      aria-hidden="true"
    >
      <path
        d="M7 1.2 L13.2 12 H0.8 Z"
        fill={fill}
        stroke={fill}
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <rect x="6.25" y="4.6" width="1.5" height="4.2" rx="0.75" fill={mark} />
      <circle cx="7" cy="10.3" r="0.85" fill={mark} />
    </svg>
  );
};

/**
 * Area alert label lying on the ground just inside the lower-right edge, next
 * to the right corner. The wrapper sits on the sharp right corner and applies
 * the same iso matrix as tiles and text boxes, so the label stays parallel to
 * the edge at any zoom; the label is laid out in the unprojected plane, where
 * x runs along the edge and negative y points into the area.
 */
export const RectangleStatusLayer = () => {
  const { rectangles } = useScene();
  const { rectangleStatus, setHoveredRectangleId } = useDiagramVisual();

  if (!rectangleStatus) return null;

  return (
    <>
      {rectangles.map((rectangle) => {
        const status = rectangleStatus[rectangle.id];
        const level = status?.badgeLevel;
        const count = status?.badgeCount ?? 0;
        const tone = level ? ALERT_BADGE_TONE[level] : undefined;

        if (!tone || count <= 0) return null;

        const corner = getRectangleRightVertex(rectangle.from, rectangle.to);
        const badgeHint = status?.badgeHint?.trim() ? status.badgeHint : undefined;
        const scale = getEdgeLabelScale(rectangle.from, rectangle.to, count);

        return (
          <Box
            key={rectangle.id}
            data-rectangle-id={rectangle.id}
            data-rectangle-anchor="right"
            data-anchor-x={corner.x}
            data-anchor-y={corner.y}
            style={{
              left: corner.x,
              top: corner.y
            }}
            sx={{
              position: 'absolute',
              width: 0,
              height: 0,
              transform: GROUND_PROJECTION,
              transformOrigin: '0 0',
              pointerEvents: 'none',
              zIndex: 2
            }}
          >
            <Box
              component="span"
              title={badgeHint}
              data-rectangle-badge-hit={rectangle.id}
              data-rectangle-badge={level}
              onMouseEnter={() => setHoveredRectangleId(rectangle.id)}
              onMouseLeave={() => setHoveredRectangleId(null)}
              sx={{
                position: 'absolute',
                right: RECTANGLE_EDGE_LABEL_OFFSET.along,
                bottom: RECTANGLE_EDGE_LABEL_OFFSET.inset,
                display: 'inline-flex',
                alignItems: 'center',
                gap: `${RECTANGLE_EDGE_LABEL_SIZE.gap}px`,
                boxSizing: 'border-box',
                height: RECTANGLE_EDGE_LABEL_SIZE.height,
                px: `${RECTANGLE_EDGE_LABEL_SIZE.padX}px`,
                borderRadius: `${RECTANGLE_EDGE_LABEL_SIZE.radius}px`,
                fontSize: RECTANGLE_EDGE_LABEL_SIZE.fontSize,
                fontWeight: 700,
                lineHeight: 1,
                whiteSpace: 'nowrap',
                fontVariantNumeric: 'tabular-nums',
                boxShadow: '0 1px 4px rgba(15, 23, 42, 0.22)'
              }}
              style={{
                transform: scale < 1 ? `scale(${scale})` : undefined,
                transformOrigin: 'right bottom',
                backgroundColor: tone.bg,
                color: tone.fg,
                pointerEvents: 'auto',
                cursor: 'pointer',
                userSelect: 'none'
              }}
            >
              <AlertTriangle fill={tone.fg} mark={tone.bg} />
              {count}
            </Box>
          </Box>
        );
      })}
    </>
  );
};
