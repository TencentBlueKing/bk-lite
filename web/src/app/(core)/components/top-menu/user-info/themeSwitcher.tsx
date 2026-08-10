'use client';

import Icon from '@/components/icon';
import { useThemeMode } from '@/theme';
import { useTranslation } from '@/utils/i18n';

const ThemeSwitcher = () => {
  const { t } = useTranslation();
  const { mode, toggleMode } = useThemeMode();
  const isDarkMode = mode === 'dark';

  const handleToggle = () => {
    toggleMode();
  };

  return (
    <div className="flex w-full items-center justify-between" onClick={handleToggle}>
      {t('common.theme')}
      <span className="text-base text-[var(--color-text-4)]">
        <div className="flex cursor-pointer items-center">
          {isDarkMode ? <Icon type="anse" /> : <Icon type="liangse" />}
        </div>
      </span>
    </div>
  );
};

export default ThemeSwitcher;
