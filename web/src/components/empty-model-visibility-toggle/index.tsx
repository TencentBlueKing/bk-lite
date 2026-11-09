'use client';

import React, { useId } from 'react';
import { Switch } from 'antd';
import { useTranslation } from '@/utils/i18n';

interface EmptyModelVisibilityToggleProps {
  hideEmptyModels: boolean;
  onChange: (hideEmptyModels: boolean) => void;
}

const EmptyModelVisibilityToggle: React.FC<EmptyModelVisibilityToggleProps> = ({
  hideEmptyModels,
  onChange,
}) => {
  const { t } = useTranslation();
  const switchId = useId();
  const label = hideEmptyModels
    ? t('common.hideEmptyModel', '隐藏空模型')
    : t('common.showEmptyModel', '显示空模型');

  return (
    <div className="inline-flex min-w-0 items-center gap-1">
      <Switch
        id={switchId}
        size="small"
        checked={!hideEmptyModels}
        aria-label={label}
        onChange={(showEmptyModels) => onChange(!showEmptyModels)}
      />
      <label
        htmlFor={switchId}
        className={`cursor-pointer whitespace-nowrap text-xs ${
          hideEmptyModels ? 'text-[var(--color-primary)]' : 'text-[var(--color-text-2)]'
        }`}
      >
        {label}
      </label>
    </div>
  );
};

export default EmptyModelVisibilityToggle;
