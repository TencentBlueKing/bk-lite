import React, { useMemo } from 'react';
import { Coords, AnchorPosition } from 'src/types';
import { Svg } from 'src/components/Svg/Svg';
import { TRANSFORM_CONTROLS_COLOR } from 'src/config';
import { useIsoProjection } from 'src/hooks/useIsoProjection';
import {
  getBoundingBox,
  outermostCornerPositions,
  getTilePosition,
  convertBoundsToNamedAnchors
} from 'src/utils';
import { TransformAnchor } from './TransformAnchor';

interface Props {
  from: Coords;
  to: Coords;
  onAnchorMouseDown?: (anchorPosition: AnchorPosition) => void;
  // Extra pixels outside the tile, so a node frame sits around the icon.
  framePad?: number;
}

const strokeWidth = 2.5;

export const TransformControls = ({
  from,
  to,
  onAnchorMouseDown,
  framePad = 0
}: Props) => {
  const { css, pxSize } = useIsoProjection({
    from,
    to
  });

  const anchors = useMemo(() => {
    if (!onAnchorMouseDown) return [];

    const corners = getBoundingBox([from, to]);
    const namedCorners = convertBoundsToNamedAnchors(corners);
    const cornerPositions = Object.entries(namedCorners).map(
      ([key, value], i) => {
        const position = getTilePosition({
          tile: value,
          origin: outermostCornerPositions[i]
        });

        return {
          position,
          onMouseDown: () => {
            onAnchorMouseDown(key as AnchorPosition);
          }
        };
      }
    );

    return cornerPositions;
  }, [onAnchorMouseDown, from, to]);

  return (
    <>
      <Svg
        style={{
          ...css,
          overflow: 'visible',
          pointerEvents: 'none'
        }}
      >
        <g transform={`translate(${strokeWidth - framePad}, ${strokeWidth - framePad})`}>
          <rect
            width={pxSize.width - strokeWidth * 2 + framePad * 2}
            height={pxSize.height - strokeWidth * 2 + framePad * 2}
            fill="none"
            stroke={TRANSFORM_CONTROLS_COLOR}
            strokeWidth={strokeWidth}
            strokeLinejoin="round"
          />
        </g>
      </Svg>

      {anchors.map(({ position, onMouseDown }, index) => {
        return (
          <TransformAnchor
            key={index}
            position={position}
            onMouseDown={onMouseDown}
          />
        );
      })}
    </>
  );
};
