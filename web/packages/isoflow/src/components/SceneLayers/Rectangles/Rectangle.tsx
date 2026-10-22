import React from 'react';
import { useScene } from 'src/hooks/useScene';
import { IsoTileArea } from 'src/components/IsoTileArea/IsoTileArea';
import { getColorVariant } from 'src/utils';
import { useColor } from 'src/hooks/useColor';
import { useDiagramVisual } from 'src/diagramOverlay/context';
import {
  RECTANGLE_BORDER_COLOR,
  RECTANGLE_STATUS_STROKE_HOVER_WIDTH,
  RECTANGLE_STATUS_STROKE_WIDTH
} from 'src/diagramOverlay/colors';
import { RECTANGLE_CORNER_RADIUS } from 'src/diagramOverlay/rectangleAnchor';

type Props = ReturnType<typeof useScene>['rectangles'][0];

export const Rectangle = ({ id, from, to, color: colorId }: Props) => {
  const color = useColor(colorId);
  const visual = useDiagramVisual();
  const borderLevel = visual.rectangleStatus?.[id]?.borderLevel;
  const hovered = visual.hoveredRectangleId === id;
  const strokeColor = borderLevel
    ? RECTANGLE_BORDER_COLOR[borderLevel]
    : getColorVariant(color.value, 'dark', { grade: 2 });

  return (
    <IsoTileArea
      from={from}
      to={to}
      fill={color.value}
      cornerRadius={RECTANGLE_CORNER_RADIUS}
      stroke={{
        color: strokeColor,
        width: borderLevel
          ? hovered
            ? RECTANGLE_STATUS_STROKE_HOVER_WIDTH
            : RECTANGLE_STATUS_STROKE_WIDTH
          : 1,
        glow: borderLevel ? strokeColor : undefined
      }}
    />
  );
};
