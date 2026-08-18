'use client';

import React from 'react';
import { Tooltip } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';

interface FieldGuideTipProps {
  short?: string;
  title: string;
}

const FieldGuideTip: React.FC<FieldGuideTipProps> = ({ short, title }) => {
  if (!short) {
    return null;
  }

  return (
    <Tooltip
      placement="top"
      mouseEnterDelay={0.15}
      color="var(--color-bg)"
      overlayInnerStyle={{
        maxWidth: 420,
        padding: '10px 12px',
        color: 'var(--color-text-1)',
        border: '1px solid var(--color-border-1)',
        boxShadow: '0 6px 16px rgba(0, 0, 0, 0.08)',
        borderRadius: 8
      }}
      title={
        <div>
          <div className="mb-1 text-xs font-medium text-[var(--color-text-1)]">
            {title}
          </div>
          <div className="whitespace-pre-line text-xs leading-5 text-[var(--color-text-2)]">
            {short}
          </div>
        </div>
      }
    >
      <button
        type="button"
        aria-label={title}
        className="inline-flex items-center justify-center ml-[4px] align-middle w-[18px] h-[18px] rounded-full text-[var(--color-text-3)] hover:text-[var(--color-primary)] hover:bg-[var(--color-fill-2)] transition-colors duration-150 cursor-help border-0 bg-transparent p-0"
        onClick={(e) => e.preventDefault()}
      >
        <QuestionCircleOutlined className="text-[13px]" />
      </button>
    </Tooltip>
  );
};

export default FieldGuideTip;
