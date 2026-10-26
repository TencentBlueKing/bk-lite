import React, { useRef } from 'react';
import { Box, SxProps } from '@mui/material';

const CONNECTOR_WIDTH = 8;

const LABEL_CARD_SX = {
  bgcolor: 'var(--color-bg)',
  border: '1px solid var(--color-border-1)',
  borderRadius: '4px',
  py: '1px',
  px: '5px',
  boxShadow: 'none'
};

export interface Props {
  labelHeight?: number;
  maxWidth: number;
  maxHeight?: number;
  expandDirection?: 'CENTER' | 'BOTTOM';
  children: React.ReactNode;
  sx?: SxProps;
  // The connector is drawn separately when the card lives in another layer.
  hideConnector?: boolean;
  /** Attributes for the visible card, such as hit-test data. */
  cardProps?: Record<string, string | number | undefined>;
  /**
   * Drawn on the card's top-right corner, outside the card's clipping. Pass
   * null (not undefined) while there is no badge so the card keeps one DOM
   * tree as the badge comes and goes; undefined keeps the plain layout.
   */
  cornerBadge?: React.ReactNode;
}

export const LabelConnector = ({ labelHeight }: { labelHeight: number }) => {
  if (labelHeight <= 0) return null;

  return (
    <Box
      component="svg"
      viewBox={`0 0 ${CONNECTOR_WIDTH} ${labelHeight}`}
      width={CONNECTOR_WIDTH}
      height={labelHeight}
      sx={{
        position: 'absolute',
        top: -labelHeight,
        left: -CONNECTOR_WIDTH / 2,
        pointerEvents: 'none'
      }}
    >
      <line
        x1={CONNECTOR_WIDTH / 2}
        y1={0}
        x2={CONNECTOR_WIDTH / 2}
        y2={labelHeight}
        strokeDasharray="3 3"
        stroke="#7D93AB"
        strokeWidth={1.25}
      />
    </Box>
  );
};

export const Label = ({
  children,
  maxWidth,
  maxHeight,
  expandDirection = 'CENTER',
  labelHeight = 0,
  sx,
  hideConnector = false,
  cardProps,
  cornerBadge
}: Props) => {
  const contentRef = useRef<HTMLDivElement>(null);
  const cardTransform = `translate(-50%, ${
    expandDirection === 'BOTTOM' ? '-100%' : '-50%'
  })`;

  if (cornerBadge !== undefined) {
    // The card clips its content, so the badge sits beside it in a shared
    // anchor that carries the card's offset.
    return (
      <Box
        sx={{
          position: 'absolute',
          width: maxWidth
        }}
      >
        {!hideConnector && <LabelConnector labelHeight={labelHeight} />}

        <Box
          sx={{
            position: 'absolute',
            transformOrigin: 'bottom center',
            transform: cardTransform
          }}
          style={{ top: -labelHeight }}
        >
          <Box
            ref={contentRef}
            {...cardProps}
            sx={{
              position: 'relative',
              ...LABEL_CARD_SX,
              overflow: 'visible',
              width: 'max-content',
              maxWidth: 'none',
              ...sx
            }}
            style={{ maxHeight }}
          >
            {children}
          </Box>
          {cornerBadge ? (
            <Box
              sx={{
                position: 'absolute',
                top: 0,
                right: 0,
                transform: 'translate(calc(50% - 1px), calc(-50% + 1px))'
              }}
            >
              {cornerBadge}
            </Box>
          ) : null}
        </Box>
      </Box>
    );
  }

  return (
    <Box
      sx={{
        position: 'absolute',
        width: maxWidth
      }}
    >
      {!hideConnector && <LabelConnector labelHeight={labelHeight} />}

      <Box
        ref={contentRef}
        {...cardProps}
        sx={{
          position: 'absolute',
          display: 'inline-block',
          ...LABEL_CARD_SX,
          transformOrigin: 'bottom center',
          transform: cardTransform,
          overflow: 'hidden',
          ...sx
        }}
        style={{
          maxHeight,
          top: -labelHeight
        }}
      >
        {children}
      </Box>
    </Box>
  );
};
