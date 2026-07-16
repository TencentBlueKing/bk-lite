import { useMemo } from 'react';
import type { ListItem } from '@/types';
import { useTranslation } from '@/utils/i18n';

export const useMonitorLevelOptions = (): ListItem[] => {
  const { t } = useTranslation();

  return useMemo(
    () => [
      { label: t('monitor.events.critical'), value: 'critical' },
      { label: t('monitor.events.error'), value: 'error' },
      { label: t('monitor.events.warning'), value: 'warning' },
    ],
    [t],
  );
};
