import React, { useRef } from 'react';
import { Box, SxProps } from '@mui/material';

const CONNECTOR_DOT_SIZE = 3;

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
      viewBox={`0 0 ${CONNECTOR_DOT_SIZE} ${labelHeight}`}
      width={CONNECTOR_DOT_SIZE}
      sx={{
        position: 'absolute',
        top: -labelHeight,
        left: -CONNECTOR_DOT_SIZE / 2,
        pointerEvents: 'none'
      }}
    >
      <line
        x1={CONNECTOR_DOT_SIZE / 2}
        y1={0}
        x2={CONNECTOR_DOT_SIZE / 2}
        y2={labelHeight}
        strokeDasharray={`0, ${CONNECTOR_DOT_SIZE * 2}`}
        stroke="black"
        strokeWidth={CONNECTOR_DOT_SIZE}
        strokeLinecap="round"
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
              bgcolor: 'common.white',
              border: '1px solid',
              borderColor: 'grey.400',
              borderRadius: 2,
              py: 1,
              px: 1.5,
              overflow: 'hidden',
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
                transform: 'translate(50%, -50%)'
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
          bgcolor: 'common.white',
          border: '1px solid',
          borderColor: 'grey.400',
          borderRadius: 2,
          py: 1,
          px: 1.5,
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
