import React from 'react';
import { ReloadOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';

interface RefreshIconButtonProps {
  loading?: boolean;
  disabled?: boolean;
  onClick: () => void;
  className?: string;
  title?: string;
  variant?: 'text' | 'outlined' | 'borderless';
}

const RefreshIconButton: React.FC<RefreshIconButtonProps> = ({
  loading = false,
  disabled = false,
  onClick,
  className = '',
  title,
}) => {
  const { t } = useTranslation();
  const label = title ?? t('common.refresh');
  return (
    <button
      type="button"
      className={`inline-flex h-8 w-8 cursor-pointer items-center justify-center rounded-full border border-[var(--color-border-1)] bg-[var(--color-bg-1)] text-[13px] text-[var(--color-primary)] transition hover:border-[var(--color-primary)] hover:bg-[var(--color-fill-1)] disabled:cursor-not-allowed disabled:opacity-60 ${className}`}
      onClick={onClick}
      disabled={disabled || loading}
      aria-label={label}
      title={label}
    >
      <ReloadOutlined className={loading ? 'animate-spin' : ''} />
    </button>
  );
};

export default RefreshIconButton;
