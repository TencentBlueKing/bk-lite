'use client';

import React from 'react';
import CompactEmptyState from '@/components/compact-empty-state';
import { useTranslation } from '@/utils/i18n';

export interface OpspilotProviderEmptyStateProps {
  variant?: 'vendor' | 'model' | 'generic';
  description?: React.ReactNode;
  className?: string;
}

const DEFAULT_CLASSNAME_MAP: Record<NonNullable<OpspilotProviderEmptyStateProps['variant']>, string> = {
  vendor: 'py-8',
  model: 'py-6',
  generic: 'py-6',
};

const OpspilotProviderEmptyState: React.FC<OpspilotProviderEmptyStateProps> = ({
  variant = 'generic',
  description,
  className,
}) => {
  const { t } = useTranslation();

  const resolvedDescription = description ?? (
    variant === 'vendor'
      ? t('provider.vendor.empty')
      : variant === 'model'
        ? t('provider.model.empty')
        : t('common.noData')
  );

  return (
    <CompactEmptyState
      description={resolvedDescription}
      className={className ?? DEFAULT_CLASSNAME_MAP[variant]}
    />
  );
};

export default OpspilotProviderEmptyState;
