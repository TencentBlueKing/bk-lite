'use client';

import React from 'react';
import { Tooltip } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';

interface FieldGuideTipProps {
  short?: string;
}

const FieldGuideTip: React.FC<FieldGuideTipProps> = ({ short }) => {
  const { t } = useTranslation();

  if (!short) {
    return null;
  }

  return (
    <Tooltip
      placement="top"
      mouseEnterDelay={0.15}
      color="var(--color-bg)"
      overlayInnerStyle={{
        maxWidth: 320,
        padding: '10px 12px',
        color: 'var(--color-text-1)',
        border: '1px solid var(--color-border-1)',
        boxShadow: '0 6px 16px rgba(0, 0, 0, 0.08)',
        borderRadius: 8
      }}
      title={
        <div>
          <div
            style={{
              fontSize: 12,
              fontWeight: 500,
              color: 'var(--color-text-1)',
              marginBottom: 4
            }}
          >
            {t('monitor.integrations.fieldGuideTip')}
          </div>
          <div
            style={{
              fontSize: 12,
              lineHeight: '20px',
              color: 'var(--color-text-2)'
            }}
          >
            {short}
          </div>
        </div>
      }
    >
      <button
        type="button"
        aria-label={t('monitor.integrations.fieldGuideTip')}
        className="inline-flex items-center justify-center ml-[4px] align-middle w-[18px] h-[18px] rounded-full text-[var(--color-text-3)] hover:text-[var(--color-primary)] hover:bg-[var(--color-fill-2)] transition-colors duration-150 cursor-help border-0 bg-transparent p-0"
        onClick={(e) => e.preventDefault()}
      >
        <QuestionCircleOutlined className="text-[13px]" />
      </button>
    </Tooltip>
  );
};

export default FieldGuideTip;
