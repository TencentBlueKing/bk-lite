import React from 'react';
import { Empty } from 'antd';

export interface ChartEmptyStateProps {
  title?: string;
  description?: string;
  variant?: 'plain' | 'decorated';
  compact?: boolean;
  className?: string;
  style?: React.CSSProperties;
}

const ChartEmptyState: React.FC<ChartEmptyStateProps> = ({
  title,
  description,
  variant = 'plain',
  compact = false,
  className = '',
  style,
}) => {
  const decorated = variant === 'decorated';

  return (
    <div
      className={`flex h-full items-center justify-center overflow-hidden ${
        decorated
          ? 'bg-[linear-gradient(180deg,rgba(244,248,255,0.98)_0%,rgba(255,255,255,1)_100%)]'
          : ''
      }`}
      style={
        decorated
          ? {
            ...style,
            backgroundImage:
              'linear-gradient(180deg, rgba(244, 248, 255, 0.98) 0%, rgba(255, 255, 255, 1) 100%)',
          }
          : style
      }
    >
      <div
        className={`${className} relative z-[1] flex flex-col items-center justify-center text-center ${
          compact ? 'px-[12px]' : 'gap-[6px] px-[20px] py-[16px]'
        } text-[#6b7f98] ${decorated ? 'rounded-[8px] border border-[rgba(47,107,255,0.08)] bg-white/72 shadow-[0_4px_12px_rgba(15,23,42,0.04)]' : ''}`}
      >
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
        {title ? (
          <div className="text-[12px] font-[600] leading-[1.4] text-[#4a617e]">
            {title}
          </div>
        ) : null}
        {description ? (
          <div className="text-[11px] leading-[1.4] text-[#8a9bb0]">
            {description}
          </div>
        ) : null}
      </div>
    </div>
  );
};

export default ChartEmptyState;
