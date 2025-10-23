import { useMemo } from 'react';
import { ListItem } from '@/types';
import { StateMap } from '@/app/monitor/types';
import { useTranslation } from '@/utils/i18n';

const useLevelList = (): ListItem[] => {
  const { t } = useTranslation();
  return useMemo(
    () => [
      { label: t('monitor.events.critical'), value: 'critical' },
      { label: t('monitor.events.error'), value: 'error' },
      { label: t('monitor.events.warning'), value: 'warning' },
    ],
    [t]
  );
};

const useConditionList = (): ListItem[] => {
  const { t } = useTranslation();
  return useMemo(
    () => [
      { id: '=', name: '=' },
      { id: '!=', name: '!=' },
      { id: '=~', name: t('monitor.include') },
      { id: '!~', name: t('monitor.exclude') },
    ],
    [t]
  );
};

const useStateMap = (): StateMap => {
  const { t } = useTranslation();
  return useMemo(
    () => ({
      new: t('monitor.events.new'),
      recovered: t('monitor.events.recovery'),
      closed: t('monitor.events.closed'),
    }),
    [t]
  );
};

export { useLevelList, useConditionList, useStateMap };
