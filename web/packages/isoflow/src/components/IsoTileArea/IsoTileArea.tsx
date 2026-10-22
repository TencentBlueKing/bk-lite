import React, { useMemo } from 'react';
import { Coords } from 'src/types';
import { Svg } from 'src/components/Svg/Svg';
import { useIsoProjection } from 'src/hooks/useIsoProjection';
import { withAlpha } from 'src/diagramOverlay/colors';

interface Props {
  from: Coords;
  to: Coords;
  origin?: Coords;
  fill?: string;
  cornerRadius?: number;
  stroke?: {
    width: number;
    color: string;
    glow?: string;
  };
}

export const IsoTileArea = ({
  from,
  to,
  fill = 'none',
  cornerRadius = 0,
  stroke
}: Props) => {
  const { css, pxSize } = useIsoProjection({
    from,
    to
  });

  const strokeParams = useMemo(() => {
    if (!stroke) return {};

    return {
      stroke: stroke.color,
      strokeWidth: stroke.width
    };
  }, [stroke]);

  const painted = useMemo(() => {
    if (!stroke?.glow) return css;

    return {
      ...css,
      filter: `drop-shadow(0 0 8px ${withAlpha(stroke.glow, 0.45)})`
    };
  }, [css, stroke?.glow]);

  return (
    <Svg viewboxSize={pxSize} style={painted}>
      <rect
        width={pxSize.width}
        height={pxSize.height}
        fill={fill}
        rx={cornerRadius}
        {...strokeParams}
      />
    </Svg>
  );
};
