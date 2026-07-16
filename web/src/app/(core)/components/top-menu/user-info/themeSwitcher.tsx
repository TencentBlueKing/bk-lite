'use client';

import { useEffect, useState } from 'react';
import Icon from '@/components/icon';
import { useTheme } from '@/context/theme';
import { useTranslation } from '@/utils/i18n';

const ThemeSwitcher = () => {
  const { t } = useTranslation();
  const { setTheme } = useTheme();
  const [isDarkMode, setIsDarkMode] = useState(false);

  useEffect(() => {
    const savedTheme = localStorage.getItem('theme');
    setIsDarkMode(savedTheme === 'dark');
  }, []);

  const handleToggle = () => {
    const nextIsDark = !isDarkMode;
    const nextTheme = nextIsDark ? 'dark' : 'light';
    setIsDarkMode(nextIsDark);
    setTheme(nextIsDark);
    localStorage.setItem('theme', nextTheme);
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
