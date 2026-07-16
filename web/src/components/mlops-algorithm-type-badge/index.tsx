import React from 'react';
import StatusBadgeShell from '@/components/status-badge-shell';
import { useTranslation } from '@/utils/i18n';
import { MLOPS_ALGORITHM_TYPE_I18N_KEYS } from '@/components/mlops-shared';

export interface MlopsAlgorithmTypeBadgeProps {
  algorithmType?: string | null;
  label?: React.ReactNode;
  className?: string;
}

const MlopsAlgorithmTypeBadge: React.FC<MlopsAlgorithmTypeBadgeProps> = ({
  algorithmType,
  label,
  className = '',
}) => {
  const { t } = useTranslation();
  const resolvedLabel =
    label ||
    t(
      MLOPS_ALGORITHM_TYPE_I18N_KEYS[algorithmType || ''] || algorithmType || '--'
    );

  return (
    <StatusBadgeShell
      className={className}
      label={resolvedLabel}
      palette={{
        textColor: 'var(--color-primary)',
        backgroundColor:
          'color-mix(in srgb, var(--color-primary) 12%, transparent)',
      }}
    />
  );
};

export default MlopsAlgorithmTypeBadge;
