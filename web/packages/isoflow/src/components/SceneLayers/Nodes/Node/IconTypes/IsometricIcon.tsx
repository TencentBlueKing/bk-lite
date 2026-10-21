import React, { useRef, useEffect } from 'react';
import { Box } from '@mui/material';
import { PROJECTED_TILE_SIZE } from 'src/config';
import { useResizeObserver } from 'src/hooks/useResizeObserver';

interface Props {
  url: string;
  onImageLoaded?: () => void;
  hitId?: string;
  hitOrder?: number;
}

export const IsometricIcon = ({ url, onImageLoaded, hitId, hitOrder }: Props) => {
  const ref = useRef<HTMLDivElement>(null);
  const { size, observe, disconnect } = useResizeObserver();

  useEffect(() => {
    if (!ref.current) return;

    if (ref.current) observe(ref.current);

    return disconnect;
  }, [observe, disconnect]);

  return (
    <Box
      ref={ref}
      component="img"
      onLoad={onImageLoaded}
      src={url}
      data-icon-hit={hitId}
      data-icon-order={hitOrder}
      sx={{
        position: 'absolute',
        width: PROJECTED_TILE_SIZE.width * 0.8,
        top: -size.height,
        left: -size.width / 2,
        pointerEvents: 'none'
      }}
    />
  );
};
