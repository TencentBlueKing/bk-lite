import React from 'react';
import { Tooltip } from 'antd';

export interface SingleValueFetchErrorTooltipState {
  message: string;
  x: number;
  y: number;
}

interface SingleValueFetchErrorTooltipProps {
  tooltip: SingleValueFetchErrorTooltipState | null;
}

const SingleValueFetchErrorTooltip: React.FC<SingleValueFetchErrorTooltipProps> = ({
  tooltip,
}) => {
  if (!tooltip) {
    return null;
  }

  return (
    <Tooltip open title={tooltip.message} getPopupContainer={() => document.body}>
      <div
        aria-hidden
        style={{
          position: 'fixed',
          left: tooltip.x,
          top: tooltip.y,
          width: 1,
          height: 1,
          pointerEvents: 'none',
        }}
      />
    </Tooltip>
  );
};

export default SingleValueFetchErrorTooltip;
