import { ListItem } from '@/app/log/types';
import { useMemo } from 'react';
import { useTranslation } from '@/utils/i18n';

export const useConditionList = (): ListItem[] => {
  const { t } = useTranslation();
  return useMemo(
    () => [
      { id: '=', name: t('log.equalto') },
      { id: '!=', name: t('log.notequalTo') },
      { id: '>', name: t('log.moreThan') },
      { id: '<', name: t('log.lessThan') },
      { id: 'in', name: t('log.include') },
      { id: 'nin', name: t('log.exclude') },
    ],
    [t]
  );
};

export const useAlgorithmList = (): ListItem[] => {
  const { t } = useTranslation();
  return useMemo(
    () => [
      {
        value: 'keyword',
        icon: 'yuzhiguanli',
        title: t('log.event.keywordAlert'),
        content: t('log.event.keywordAlertDes'),
      },
      {
        value: 'aggregate',
        icon: 'yuzhiguanli',
        title: t('log.event.aggregationAlert'),
        content: t('log.event.aggregationAlertDes'),
      },
    ],
    [t]
  );
};

export const useScheduleList = (): ListItem[] => {
  const { t } = useTranslation();
  return useMemo(
    () => [
      { label: t('log.event.minutes'), value: 'min' },
      { label: t('log.event.hours'), value: 'hour' },
      { label: t('log.event.days'), value: 'day' },
    ],
    [t]
  );
};

export const useLevelList = (): ListItem[] => {
  const { t } = useTranslation();
  return useMemo(
    () => [
      { label: t('log.event.critical'), value: 'critical' },
      { label: t('log.event.error'), value: 'error' },
      { label: t('log.event.warning'), value: 'warning' },
    ],
    [t]
  );
};

export const useAlarmTabs = () => {
  const { t } = useTranslation();
  return [
    {
      label: t('log.event.activeAlarms'),
      key: 'activeAlarms',
    },
    {
      label: t('log.event.historicalAlarms'),
      key: 'historicalAlarms',
    },
  ];
};

export const useStateList = () => {
  const { t } = useTranslation();
  return [
    {
      label: t('log.event.new'),
      value: 'new',
    },
    {
      label: t('log.event.recovery'),
      value: 'recovered',
    },
    {
      label: t('log.event.closed'),
      value: 'closed',
    },
  ];
};

export const useStateMap = (): Record<string, string> => {
  const { t } = useTranslation();
  return useMemo(
    () => ({
      new: t('log.event.new'),
      recovered: t('log.event.recovery'),
      closed: t('log.event.closed'),
    }),
    [t]
  );
};

export const useAlertDetailTabs = () => {
  const { t } = useTranslation();
  return [
    {
      label: t('common.detail'),
      key: 'information',
    },
    {
      label: t('log.event.event'),
      key: 'event',
    },
  ];
};
