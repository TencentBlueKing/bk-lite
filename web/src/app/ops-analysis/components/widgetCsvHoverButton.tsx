'use client';

import React from 'react';
import { Tooltip } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';

interface WidgetCsvHoverButtonProps {
  label: string;
  onClick: () => void;
}

const WidgetCsvHoverButton: React.FC<WidgetCsvHoverButtonProps> = ({
  label,
  onClick,
}) => {
  const { t } = useTranslation();
  return (
    <Tooltip
      title={t('dashboard.exportCsv')}
      getPopupContainer={() => document.body}
    >
      <button
        type="button"
        aria-label={label}
        data-csv-export-hover="true"
        data-export-hidden="true"
        className="no-drag pointer-events-none inline-flex h-5 w-5 shrink-0 cursor-pointer items-center justify-center rounded-md border-0 bg-(--color-bg-1) p-0 text-(--color-text-2) opacity-0 shadow-none group-hover:pointer-events-auto group-hover:opacity-100 group-focus-within:pointer-events-auto group-focus-within:opacity-100"
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          onClick();
        }}
        onMouseDown={(event) => {
          event.stopPropagation();
        }}
        onPointerDown={(event) => {
          event.stopPropagation();
        }}
      >
        <DownloadOutlined />
      </button>
    </Tooltip>
  );
};

export default WidgetCsvHoverButton;
